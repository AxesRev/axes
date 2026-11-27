"""Peer analysis: how many of the requester's team peers already hold the requested access.

Peers are the other members of every Group the requester is a MEMBER_OF. Large teams are
sampled, then one indexed lookup per sampled peer checks whether they hold any grant-way
subject (profile, or group directly or through nested groups) or a direct HAS_PERMISSION on a
requested resource. Cost grows with the number of sampled peers, not peers x grant ways.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from examples.react_agent.graph_db import read_graph
from examples.react_agent.user_context_models import UserContextData

logger = logging.getLogger(__name__)

MAX_PEERS_PER_TEAM = 100
"""Teams larger than this are sampled down to this many peers."""

SMALL_TEAM_MAX_PEERS = 3
"""Teams with this many peers or fewer are kept only when every peer has the access."""

MIN_ACCESS_RATIO = 0.7
"""Teams where fewer than this share of peers have the access are dropped."""

_TEAM_PEERS_QUERY = """
MATCH (u:AppIdentity {external_id: $user_id})-[:MEMBER_OF]->(t:Group)<-[:MEMBER_OF]-(peer:AppIdentity)
WHERE u.app = $app AND peer.external_id <> u.external_id
RETURN t.external_id AS team_id, t.name AS team_name, collect(DISTINCT peer.external_id) AS peer_ids
"""

_PEERS_WITH_ACCESS_QUERY = """
UNWIND $peer_ids AS peer_id
MATCH (peer:AppIdentity {external_id: peer_id})
WHERE peer.app = $app
OPTIONAL MATCH (peer)-[:ASSIGNED_PROFILE]->(p:Profile)
WHERE p.external_id IN $subject_ids
OPTIONAL MATCH (peer)-[:MEMBER_OF*1..6]->(g:Group)
WHERE g.external_id IN $subject_ids
OPTIONAL MATCH (peer)-[d:HAS_PERMISSION]->(r:Resource)
WHERE r.external_id IN $resource_ids
  AND d.permission = $permission
  AND coalesce(d.effect, 'grant') <> 'mute'
WITH peer_id, count(p) + count(g) + count(d) AS hits
WHERE hits > 0
RETURN DISTINCT peer_id
"""


@dataclass(frozen=True, slots=True)
class TeamPeers:
    team_id: str
    team_name: str
    peer_ids: list[str]


def sample_peers(team_id: str, user_id: str, peer_ids: list[str], limit: int = MAX_PEERS_PER_TEAM) -> list[str]:
    """Deterministic sample: the same requester and team always check the same peers."""
    if len(peer_ids) <= limit:
        return sorted(peer_ids)

    def rank(peer_id: str) -> str:
        return hashlib.sha256(f"{user_id}:{team_id}:{peer_id}".encode()).hexdigest()

    return sorted(peer_ids, key=rank)[:limit]


def parse_team_rows(rows: list[dict[str, Any]], user_id: str) -> list[TeamPeers]:
    teams: list[TeamPeers] = []
    for row in rows:
        team_id = str(row.get("team_id") or "").strip()
        peer_ids = [str(pid).strip() for pid in row.get("peer_ids") or [] if str(pid or "").strip()]
        if not team_id or not peer_ids:
            continue
        teams.append(
            TeamPeers(
                team_id=team_id,
                team_name=str(row.get("team_name") or "").strip() or team_id,
                peer_ids=sample_peers(team_id, user_id, peer_ids),
            )
        )
    return teams


def team_passes(with_access: int, checked: int) -> bool:
    """Keep teams with a big enough sample and a high enough share of peers holding the access."""
    if checked <= 0:
        return False
    if checked <= SMALL_TEAM_MAX_PEERS:
        return with_access == checked
    return with_access / checked >= MIN_ACCESS_RATIO


def summarize_teams(teams: list[TeamPeers], peers_with_access: set[str]) -> dict[str, str]:
    """Team name -> "x/y" for teams that pass the thresholds."""
    stats: dict[str, str] = {}
    for team in teams:
        checked = len(team.peer_ids)
        with_access = sum(1 for pid in team.peer_ids if pid in peers_with_access)
        if not team_passes(with_access, checked):
            continue
        key = team.team_name if team.team_name not in stats else f"{team.team_name} ({team.team_id})"
        stats[key] = f"{with_access}/{checked}"
    return stats


async def _peer_analysis_for_user(
    *,
    tenant_id: str,
    user: UserContextData,
    subject_ids: list[str],
    resource_ids: list[str],
    permission: str,
) -> tuple[dict[str, str], int]:
    """Passing teams' stats, and how many of the requester's teams were checked."""
    rows = await read_graph(tenant_id, _TEAM_PEERS_QUERY, {"app": user.app, "user_id": user.user_id})
    teams = parse_team_rows(rows, user.user_id)
    if not teams:
        return {}, 0

    sampled = sorted({pid for team in teams for pid in team.peer_ids})
    access_rows = await read_graph(
        tenant_id,
        _PEERS_WITH_ACCESS_QUERY,
        {
            "app": user.app,
            "peer_ids": sampled,
            "subject_ids": subject_ids,
            "resource_ids": resource_ids,
            "permission": permission,
        },
    )
    peers_with_access = {str(row.get("peer_id") or "") for row in access_rows}
    stats = summarize_teams(teams, peers_with_access)
    logger.info(
        "peer_analysis: app=%s user=%s teams=%s sampled_peers=%s with_access=%s kept=%s",
        user.app,
        user.user_id,
        len(teams),
        len(sampled),
        len(peers_with_access),
        stats,
    )
    return stats, len(teams)


async def fetch_peer_analysis(
    *,
    tenant_id: str,
    user_contexts: list[UserContextData],
    subject_ids: list[str],
    resource_ids: list[str],
    permission: str | None,
) -> tuple[dict[str, str], int]:
    """Per-team peer coverage of the requested access (teams passing the thresholds), and teams checked."""
    if not tenant_id.strip() or not permission or not (subject_ids or resource_ids):
        return {}, 0
    stats: dict[str, str] = {}
    teams_checked = 0
    for user in user_contexts:
        user_stats, user_teams = await _peer_analysis_for_user(
            tenant_id=tenant_id,
            user=user,
            subject_ids=subject_ids,
            resource_ids=resource_ids,
            permission=permission,
        )
        teams_checked += user_teams
        for team, value in user_stats.items():
            stats.setdefault(team, value)
    return stats, teams_checked


def build_peer_analysis_block(stats: dict[str, str], teams_checked: int = 0) -> str:
    if not stats:
        if not teams_checked:
            return ""
        return (
            "Peer access: no significant number of the requesting user's team members have this access "
            f"(checked {teams_checked} team(s); none reached {int(MIN_ACCESS_RATIO * 100)}% of peers holding it). "
            "This is evidence that this access is not normal for the user's role. Weigh it against the stated need: "
            "grant only with a clear, specific reason this user needs access their teammates do not have.\n\n"
        )
    return (
        "Peer access (teams the requesting user belongs to; value is peers who already have this access / peers checked):\n"
        f"{json.dumps(stats, ensure_ascii=False)}\n"
        f"Only teams with a large enough sample and at least {int(MIN_ACCESS_RATIO * 100)}% of peers holding this access "
        "are listed. A listed team is evidence that this access is normal for the user's role; teams not listed are not "
        "evidence either way. Use it as guidance, not as a deterministic rule.\n\n"
    )

"""Chunked Jev Choice tournament (255 options per round)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from typesafe_sdk import AsyncTypeSafeClient, Choice

logger = logging.getLogger(__name__)

CHOICE_OPTION_LIMIT = 255
CHOICE_ADVANCE_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class TournamentOption[T]:
    """One Choice alternative. ``payload`` is the original catalog object."""

    option_id: str
    name: str
    description: str
    payload: T


@dataclass(frozen=True, slots=True)
class TournamentPick[T]:
    key: str
    option: TournamentOption[T]
    probability: float


def keyed_choice_criteria[T](
    options: list[TournamentOption[T]],
) -> tuple[dict[str, str], dict[str, TournamentOption[T]]]:
    name_counts: dict[str, int] = {}
    for option in options:
        name_counts[option.name] = name_counts.get(option.name, 0) + 1

    criteria: dict[str, str] = {}
    by_key: dict[str, TournamentOption[T]] = {}
    for option in options:
        key = option.name if name_counts.get(option.name, 0) == 1 else option.option_id
        if key in criteria:
            key = option.option_id
        criteria[key] = option.description
        by_key[key] = option
    return criteria, by_key


def _chunks[T](options: list[T], size: int) -> list[list[T]]:
    return [options[index : index + size] for index in range(0, len(options), size)]


async def choose_from_options[T](
    client: AsyncTypeSafeClient,
    *,
    state_text: str,
    options: list[TournamentOption[T]],
    instructions: str,
    question_id: str = "choice",
) -> TournamentPick[T] | None:
    if not options:
        return None
    criteria, by_key = keyed_choice_criteria(options)
    response = await client.system_one(
        state=state_text,
        questions={question_id: Choice(instructions=instructions, criteria=criteria)},
    )
    answer = response.choices[question_id]
    key = str(answer.choice)
    option = by_key.get(key)
    if option is None:
        logger.warning("jev_choice_unknown question=%s key=%s options=%s", question_id, key, list(by_key))
        return None
    probability = float((answer.probabilities or {}).get(key, 0.0))
    logger.info(
        "jev_chunk_choice question=%s key=%s probability=%.3f confidence=%s",
        question_id,
        key,
        probability,
        getattr(answer, "confidence", None),
    )
    return TournamentPick(key=key, option=option, probability=probability)


async def jev_choice_tournament[T](
    client: AsyncTypeSafeClient,
    *,
    state_text: str,
    options: list[TournamentOption[T]],
    instructions: str,
    question_id: str = "choice",
) -> TournamentPick[T] | None:
    """Pick one option with chunked Choice rounds.

    Chunks of ``CHOICE_OPTION_LIMIT`` are scored in parallel. A chunk winner
    advances only when its probability is greater than ``CHOICE_ADVANCE_THRESHOLD``.
    Finalists are scored the same way until one remains.
    """
    if not options:
        return None

    chunks = _chunks(options, CHOICE_OPTION_LIMIT)
    if len(chunks) == 1:
        return await choose_from_options(
            client,
            state_text=state_text,
            options=chunks[0],
            instructions=instructions,
            question_id=question_id,
        )

    picks = await asyncio.gather(
        *[
            choose_from_options(
                client,
                state_text=state_text,
                options=chunk,
                instructions=instructions,
                question_id=question_id,
            )
            for chunk in chunks
        ]
    )
    finalists = [pick for pick in picks if pick is not None and pick.probability > CHOICE_ADVANCE_THRESHOLD]
    logger.info(
        "jev_tournament question=%s chunks=%s advanced=%s",
        question_id,
        len(chunks),
        [pick.key for pick in finalists],
    )
    if not finalists:
        return None
    if len(finalists) == 1:
        return finalists[0]
    return await jev_choice_tournament(
        client,
        state_text=state_text,
        options=[pick.option for pick in finalists],
        instructions=instructions,
        question_id=question_id,
    )

"""Tests for Slack reply extraction from LangGraph updates."""

from slack_app.replies import slack_replies_from_updates


def test_slack_replies_from_permission_detection_update() -> None:
    data = {
        "permission_detection": {
            "permission": {"domain": "github_organization", "resource": "AxesRev", "permission": "admin"},
            "messages": [
                {
                    "type": "ai",
                    "content": '{"domain":"github_organization","resource":"AxesRev","permission":"admin"}',
                }
            ],
        }
    }

    assert slack_replies_from_updates(data) == [
        '{"domain":"github_organization","resource":"AxesRev","permission":"admin"}'
    ]


def test_slack_replies_from_evaluation_update_uses_latest_ai_message() -> None:
    data = {
        "access_request_evaluation": {
            "access_evaluation": {"should_grant": False, "justification": "Not a member."},
            "messages": [
                {"type": "ai", "content": "Checking membership in Neo4j..."},
                {"type": "ai", "content": '{"should_grant": false, "justification": "Not a member."}'},
            ],
        }
    }

    assert slack_replies_from_updates(data) == ['{"should_grant": false, "justification": "Not a member."}']


def test_slack_replies_ignore_unlisted_nodes() -> None:
    data = {
        "load_user_context": {
            "user_context": {"app": "github", "user_id": "1", "user_name": "alice", "groups": [], "permissions": []}
        },
        "permission_detection": {
            "messages": [
                {"type": "ai", "content": '{"domain":"github_repository","resource":null,"permission":"read"}'}
            ]
        },
    }

    assert slack_replies_from_updates(data) == ['{"domain":"github_repository","resource":null,"permission":"read"}']

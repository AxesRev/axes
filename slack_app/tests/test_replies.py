"""Tests for Slack reply extraction from LangGraph updates."""

from slack_app.replies import slack_replies_from_updates


def test_slack_replies_from_permission_detection_update() -> None:
    data = {
        "permission_detection": {
            "permission": {"resource": "AxesRev", "permission": "admin"},
            "messages": [
                {
                    "type": "ai",
                    "content": '{"resource":"AxesRev","permission":"admin"}',
                }
            ],
        }
    }

    assert slack_replies_from_updates(data) == ['{"resource":"AxesRev","permission":"admin"}']


def test_slack_replies_from_evaluation_update_posts_every_ai_message() -> None:
    data = {
        "access_request_evaluation": {
            "access_evaluation": {"should_grant": False, "justification": "Not a member."},
            "messages": [
                {"type": "ai", "content": "Checking membership in Neo4j..."},
                {"type": "ai", "content": '{"should_grant": false, "justification": "Not a member."}'},
            ],
        }
    }

    assert slack_replies_from_updates(data) == [
        "Checking membership in Neo4j...",
        '{"should_grant": false, "justification": "Not a member."}',
    ]


def test_slack_replies_ignore_unlisted_nodes() -> None:
    data = {
        "load_user_context": {
            "user_context": {"app": "github", "user_id": "1", "user_name": "alice", "groups": [], "permissions": []}
        },
        "permission_detection": {"messages": [{"type": "ai", "content": '{"resource":null,"permission":"read"}'}]},
    }

    assert slack_replies_from_updates(data) == ['{"resource":null,"permission":"read"}']


def test_slack_replies_from_grant_execution_posts_every_ai_turn() -> None:
    data = {
        "access_grant_execution": {
            "call_model": {
                "messages": [
                    {"type": "ai", "content": "Looking up the endpoint...", "tool_calls": [{"name": "json_explorer"}]},
                    {
                        "type": "ai",
                        "content": "Granted write access by adding the user as a repository collaborator.",
                    },
                ]
            }
        }
    }

    assert slack_replies_from_updates(data) == [
        "Looking up the endpoint...",
        "Granted write access by adding the user as a repository collaborator.",
    ]


def test_slack_replies_from_grant_execution_posts_tool_call_turn_with_text() -> None:
    data = {
        "access_grant_execution": {
            "call_model": {
                "messages": [
                    {"type": "ai", "content": "Calling GitHub...", "tool_calls": [{"name": "requests_put"}]},
                ]
            }
        }
    }

    assert slack_replies_from_updates(data) == ["Calling GitHub..."]

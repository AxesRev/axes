from typing import Any

from langgraph_sdk import Auth

auth = Auth()


@auth.authenticate
async def authenticate(headers: dict[str, str]) -> dict[str, Any]:
    """
    Authenticate users based on the X-Slack-User-ID header.
    In this trusted internal flow, we use the Slack user ID as the identity.
    """
    # LangGraph SDK and Aegra normalize headers to lowercase
    slack_user_id = headers.get("x-slack-user-id")

    if not slack_user_id:
        return {"identity": "anonymous", "is_authenticated": True, "display_name": "Anonymous User"}

    return {
        "identity": slack_user_id,
        "is_authenticated": True,
        "display_name": f"Slack User {slack_user_id}",
        "permissions": ["threads", "runs", "assistants"],
    }

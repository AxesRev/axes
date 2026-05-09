import logging
from datetime import UTC, datetime
from typing import cast

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.nodes.tools import _get_all_tools
from examples.react_agent.prompts import GITHUB_USER_CONTEXT
from examples.react_agent.state import State
from examples.react_agent.utils import load_chat_model

logger = logging.getLogger(__name__)


async def call_model(state: State, runtime: Runtime[Context]) -> dict[str, list[AIMessage]]:
    """Call the LLM powering our "agent"."""
    logger.info("Node call_model: starting (messages in state: %d)", len(state.messages))
    tools = await _get_all_tools(runtime)
    logger.info("Node call_model: %d tool(s) available: %s", len(tools), [t.name for t in tools])
    model = load_chat_model(
        runtime.context.model,
        thinking_budget_tokens=runtime.context.thinking_budget_tokens,
        reasoning_effort=runtime.context.reasoning_effort,
    ).bind_tools(tools)

    system_message = runtime.context.system_prompt.format(
        system_time=datetime.now(tz=UTC).isoformat(),
        github_user_context=(
            GITHUB_USER_CONTEXT.format(
                github_username=runtime.context.github_username,
                github_user_id=runtime.context.github_user_id,
                github_repos=", ".join(state.github_repos) if state.github_repos else "none",
                github_orgs=", ".join(state.github_orgs) if state.github_orgs else "none",
            )
            if runtime.context.github_username
            else ""
        ),
    )

    response = cast(
        "AIMessage",
        await model.ainvoke([{"role": "system", "content": system_message}, *state.messages]),
    )

    if state.is_last_step and response.tool_calls:
        logger.warning("Node call_model: reached last step with pending tool calls — aborting")
        return {
            "messages": [
                AIMessage(
                    id=response.id,
                    content="Sorry, I could not find an answer to your question in the specified number of steps.",
                )
            ]
        }

    if response.tool_calls:
        logger.info(
            "Node call_model: done — LLM requested %d tool call(s): %s",
            len(response.tool_calls),
            [tc["name"] for tc in response.tool_calls],
        )
    else:
        logger.info("Node call_model: done — LLM produced final response")
    return {"messages": [response]}

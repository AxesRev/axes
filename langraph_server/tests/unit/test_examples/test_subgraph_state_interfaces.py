"""Parent-owned channels persist; subgraph transcripts stay off the parent thread."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime

from examples.react_agent.context import Context
from examples.react_agent.state import AccessRequestEvaluation, Permission, State
from examples.react_agent.subgraphs.access_grant_execution import (
    access_grant_execution_graph,
    run_access_grant_execution,
)
from examples.react_agent.subgraphs.access_request_evaluation import (
    AccessEvaluationInput,
    AccessEvaluationOutput,
    access_request_evaluation_graph,
    run_access_request_evaluation,
)
from examples.react_agent.subgraphs.permission_detection import (
    PermissionDetectionInput,
    PermissionDetectionOutput,
    make_permission_detection_graph,
    make_permission_detection_node,
)
from examples.react_agent.user_context_models import UserContextData, UserContextGroup, UserContextPermission


def _sample_user_context() -> UserContextData:
    return UserContextData(
        app="salesforce",
        user_id="005gL00000JQRHlQAP",
        user_name="Kirill RandD",
        groups=[UserContextGroup(external_id="org-1", name="AxesRev", description="Main org")],
        permissions=[
            UserContextPermission(
                permission="read",
                target_kind="resource",
                target_name="GenAiPromptTemplate",
                target_external_id="tpl-1",
            )
        ],
    )


def _schema_properties(schema: dict[str, object]) -> dict[str, object]:
    properties = schema.get("properties")
    if isinstance(properties, dict):
        return properties
    return {}


def test_user_contexts_persist_and_parent_messages_stay_isolated() -> None:
    user_context = _sample_user_context()
    original = HumanMessage(content="I need Prompt Builder access")

    def detect(state: State) -> dict[str, object]:
        assert state.user_contexts == [user_context]
        assert state.user_request == original.content
        assert state.doc_corpus_context == "Campaign object docs"
        return {"permission": Permission(resource="GenAiPromptTemplate", permission="edit")}

    def evaluate(state: State) -> dict[str, object]:
        assert state.user_contexts == [user_context]
        assert state.doc_corpus_context == "Campaign object docs"
        return {
            "access_evaluation": AccessRequestEvaluation(
                should_grant=True,
                justification="Requester is identified and eligible.",
            )
        }

    def grant(state: State) -> dict[str, object]:
        assert state.user_contexts == [user_context]
        assert state.selected_apps == ["salesforce"]
        assert state.doc_corpus_context == "Campaign object docs"
        return {"messages": [AIMessage(content="Granted Prompt Builder access.")]}

    detection = StateGraph(
        State,
        input_schema=PermissionDetectionInput,
        output_schema=PermissionDetectionOutput,
    )
    detection.add_node("detect", detect)
    detection.add_edge("__start__", "detect")

    evaluation = StateGraph(
        State,
        input_schema=AccessEvaluationInput,
        output_schema=AccessEvaluationOutput,
    )
    evaluation.add_node("evaluate", evaluate)
    evaluation.add_edge("__start__", "evaluate")

    parent = StateGraph(State)

    def load_context(state: State) -> dict[str, object]:
        return {
            "user_contexts": [user_context],
            "selected_apps": ["salesforce"],
            "user_request": original.content,
            "doc_corpus_context": "Campaign object docs",
        }

    parent.add_node("load_user_context", load_context)
    parent.add_node("permission_detection", detection.compile())
    parent.add_node("access_request_evaluation", evaluation.compile())
    parent.add_node("access_grant_execution", grant)
    parent.add_edge("__start__", "load_user_context")
    parent.add_edge("load_user_context", "permission_detection")
    parent.add_edge("permission_detection", "access_request_evaluation")
    parent.add_edge("access_request_evaluation", "access_grant_execution")

    result = parent.compile().invoke({"messages": [original]})

    assert result["user_contexts"] == [user_context]
    assert result["selected_apps"] == ["salesforce"]
    assert result["permission"].permission == "edit"
    assert result["access_evaluation"].should_grant is True
    ai_contents = [message.content for message in result["messages"] if isinstance(message, AIMessage)]
    assert ai_contents == ["Granted Prompt Builder access."]


async def test_permission_detection_graph_reads_user_request_not_parent_messages() -> None:
    with patch(
        "examples.react_agent.subgraphs.permission_detection._get_all_tools",
        new=AsyncMock(return_value=[]),
    ):
        compiled = await make_permission_detection_graph()

    _assert_private_transcript_interface(compiled, expect_output_messages=True)
    assert "permission" in _schema_properties(compiled.get_output_jsonschema())
    assert "user_request" in _schema_properties(compiled.get_input_jsonschema())


def test_evaluation_and_grant_graphs_use_private_transcripts() -> None:
    _assert_private_transcript_interface(access_request_evaluation_graph, expect_output_messages=False)
    _assert_private_transcript_interface(access_grant_execution_graph, expect_output_messages=True)


async def test_run_access_request_evaluation_posts_result_json() -> None:
    evaluation = AccessRequestEvaluation(should_grant=True, justification="Requester is on the owning team.")
    with patch.object(
        access_request_evaluation_graph,
        "ainvoke",
        new=AsyncMock(return_value={"access_evaluation": evaluation}),
    ):
        result = await run_access_request_evaluation(State(), Runtime(context=Context()))

    assert result["access_evaluation"] == evaluation
    assert result["messages"][0].content == evaluation.model_dump_json()


async def test_run_permission_detection_posts_result_json() -> None:
    permission = Permission(resource="AxesRev", permission="admin")
    compiled = AsyncMock()
    compiled.ainvoke = AsyncMock(return_value={"permission": permission})
    run_permission_detection = make_permission_detection_node(compiled)

    result = await run_permission_detection(State(), Runtime(context=Context()))

    assert result["permission"] == permission
    assert result["messages"][0].content == permission.model_dump_json()


async def test_run_permission_detection_posts_failure_reply() -> None:
    failure = AIMessage(content="Could not determine a permission.")
    compiled = AsyncMock()
    compiled.ainvoke = AsyncMock(return_value={"permission": None, "messages": [failure]})
    run_permission_detection = make_permission_detection_node(compiled)

    result = await run_permission_detection(State(), Runtime(context=Context()))

    assert "permission" not in result
    assert result["messages"][0].content == failure.content


async def test_run_access_grant_execution_copies_only_final_reply() -> None:
    with patch.object(
        access_grant_execution_graph,
        "ainvoke",
        new=AsyncMock(
            return_value={
                "messages": [
                    HumanMessage(content="seed"),
                    AIMessage(content="Access granted to Kirill RandD."),
                ]
            }
        ),
    ):
        result = await run_access_grant_execution(State(), Runtime(context=Context()))

    assert [message.content for message in result["messages"]] == ["Access granted to Kirill RandD."]


def _assert_private_transcript_interface(compiled: object, *, expect_output_messages: bool) -> None:
    input_properties = _schema_properties(compiled.get_input_jsonschema())  # type: ignore[union-attr]
    output_properties = _schema_properties(compiled.get_output_jsonschema())  # type: ignore[union-attr]
    assert "user_contexts" in input_properties
    assert "selected_apps" in input_properties
    assert "user_request" in input_properties
    assert "doc_corpus_context" in input_properties
    assert "messages" not in input_properties
    assert "user_contexts" not in output_properties
    assert "selected_apps" not in output_properties
    if expect_output_messages:
        assert "messages" in output_properties
    else:
        assert "messages" not in output_properties

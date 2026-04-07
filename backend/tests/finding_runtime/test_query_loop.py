from __future__ import annotations

import asyncio

from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.audit_session import AuditSkillInvocationStatus, AuditToolCallStatus
from app.services.finding_runtime.models import (
    RuntimeMessageRole,
    RuntimeStopReason,
    ToolExecutionPayload,
    TranscriptItem,
)
from app.services.finding_runtime.query_loop import QueryLoop
from app.services.finding_runtime.runner import FindingRuntimeRunner
from app.services.finding_runtime.session_store import AuditSessionStore
from app.services.finding_runtime.skills import RuntimeSkillTool
from app.services.finding_runtime.tooling import RuntimeTool, ToolExecutionContext, ToolOrchestrator, ToolRegistry


class FakeModelClient:
    def __init__(self, responses: list[dict] | None = None, content: str = "assistant reply"):
        self._responses = list(responses or [])
        self.content = content
        self.calls = []

    async def complete(self, *, system_prompt, recon_payload, transcript, model_name, tool_definitions):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "recon_payload": recon_payload,
                "transcript": transcript,
                "model_name": model_name,
                "tool_definitions": tool_definitions,
            }
        )
        if self._responses:
            return self._responses.pop(0)
        return {
            "content": self.content,
            "stop_reason": RuntimeStopReason.ASSISTANT_TURN_COMPLETE.value,
        }


class EchoInput(BaseModel):
    text: str


class EchoTool(RuntimeTool):
    name = "echo"
    description = "Echo text"
    input_model = EchoInput

    def is_concurrency_safe(self, parsed_input: EchoInput) -> bool:
        return True

    async def execute(self, parsed_input: EchoInput, context: ToolExecutionContext) -> ToolExecutionPayload:
        return ToolExecutionPayload(
            content=f"echo:{parsed_input.text}",
            output_payload={"echo": parsed_input.text},
        )


class FakeSkillService:
    @staticmethod
    async def get_skill_body(user_id, skill_ref, agent_type=None):
        return {"skill": skill_ref, "content": "body"}

    @staticmethod
    async def list_skill_resources(user_id, skill_ref, resource_name="", agent_type=None):
        return {"skill": skill_ref, "mode": "list", "resource_name": resource_name, "items": []}

    @staticmethod
    async def get_skill_resource(user_id, skill_ref, resource_name, agent_type=None):
        return {"skill": skill_ref, "resource": resource_name, "content": "resource body"}


def build_store() -> AuditSessionStore:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return AuditSessionStore(session_factory=session_factory)


def test_query_loop_run_turn_persists_assistant_reply_and_turn():
    store = build_store()
    session_id = store.create_session(
        project_id="project-1",
        runtime_stack="runtime",
        system_prompt="system prompt",
        recon_payload={"repo": "demo"},
    )
    store.append_message(
        session_id,
        TranscriptItem(role=RuntimeMessageRole.USER, content="inspect the repo"),
    )
    client = FakeModelClient()
    loop = QueryLoop(session_store=store, model_client=client, tool_registry=ToolRegistry(), tool_orchestrator=None)

    result = asyncio.run(loop.run_turn(session_id=session_id, model_name="gpt-test"))
    snapshot = store.load_session_snapshot(session_id)

    assert result.stop_reason is RuntimeStopReason.ASSISTANT_TURN_COMPLETE
    assert len(snapshot.turns) == 1
    assert snapshot.turns[0].model_name == "gpt-test"
    assert snapshot.turns[0].status == "completed"
    assert snapshot.messages[-1].role == RuntimeMessageRole.ASSISTANT.value
    assert snapshot.messages[-1].content == "assistant reply"
    assert snapshot.checkpoints[-1].state_payload["stop_reason"] == RuntimeStopReason.ASSISTANT_TURN_COMPLETE.value

    assert client.calls[0]["system_prompt"] == "system prompt"
    assert client.calls[0]["recon_payload"] == {"repo": "demo"}
    assert [item.content for item in client.calls[0]["transcript"]] == ["inspect the repo"]


def test_runner_executes_tool_calls_and_loops_until_final_answer():
    store = build_store()
    session_id = store.create_session(project_id="project-1", system_prompt="system")
    store.append_message(session_id, TranscriptItem(role=RuntimeMessageRole.USER, content="inspect code"))
    client = FakeModelClient(
        responses=[
            {
                "content": "Need a tool",
                "tool_calls": [{"id": "tool-1", "name": "echo", "input": {"text": "repo summary"}}],
            },
            {
                "content": "Final answer",
                "stop_reason": RuntimeStopReason.ASSISTANT_TURN_COMPLETE.value,
            },
        ]
    )
    registry = ToolRegistry([EchoTool()])
    orchestrator = ToolOrchestrator(session_store=store, tool_registry=registry)
    runner = FindingRuntimeRunner(
        session_store=store,
        model_client=client,
        tool_registry=registry,
        tool_orchestrator=orchestrator,
    )

    result = asyncio.run(runner.run_once(session_id=session_id, model_name="gpt-test"))
    snapshot = store.load_session_snapshot(session_id)

    assert result.stop_reason is RuntimeStopReason.ASSISTANT_TURN_COMPLETE
    assert snapshot.session.state == "completed"
    assert [message.role for message in snapshot.messages] == [
        RuntimeMessageRole.USER.value,
        RuntimeMessageRole.ASSISTANT.value,
        RuntimeMessageRole.TOOL_USE.value,
        RuntimeMessageRole.TOOL_RESULT.value,
        RuntimeMessageRole.ASSISTANT.value,
    ]
    assert snapshot.messages[2].payload["tool_name"] == "echo"
    assert snapshot.messages[3].payload["output"] == {"echo": "repo summary"}
    assert len(snapshot.tool_calls) == 1
    assert snapshot.tool_calls[0].status == AuditToolCallStatus.COMPLETED.value
    assert client.calls[0]["tool_definitions"][0]["name"] == "echo"


def test_runner_executes_skill_tool_and_persists_skill_invocation():
    store = build_store()
    session_id = store.create_session(project_id="project-1", system_prompt="system")
    store.replace_skills(
        session_id,
        [{"slug": "code-audit-finding", "name": "Code Audit Finding", "description": "primary skill", "source_type": "bundled"}],
        matched_skill_refs={"code-audit-finding"},
    )
    store.append_message(session_id, TranscriptItem(role=RuntimeMessageRole.USER, content="bootstrap skill"))
    client = FakeModelClient(
        responses=[
            {
                "content": "Load the audit skill",
                "tool_calls": [{"id": "tool-1", "name": "Skill", "input": {"skill_ref": "code-audit-finding", "action": "body"}}],
            },
            {
                "content": "Final answer",
                "stop_reason": RuntimeStopReason.ASSISTANT_TURN_COMPLETE.value,
            },
        ]
    )
    registry = ToolRegistry([RuntimeSkillTool(session_store=store, skill_service=FakeSkillService())])
    orchestrator = ToolOrchestrator(session_store=store, tool_registry=registry)
    runner = FindingRuntimeRunner(
        session_store=store,
        model_client=client,
        tool_registry=registry,
        tool_orchestrator=orchestrator,
    )

    result = asyncio.run(runner.run_once(session_id=session_id, model_name="gpt-test"))
    snapshot = store.load_session_snapshot(session_id)

    assert result.stop_reason is RuntimeStopReason.ASSISTANT_TURN_COMPLETE
    assert len(snapshot.skill_invocations) == 1
    assert snapshot.skill_invocations[0].skill_ref == "code-audit-finding"
    assert snapshot.skill_invocations[0].status == AuditSkillInvocationStatus.COMPLETED.value
    assert snapshot.messages[2].payload["tool_name"] == "Skill"
    assert snapshot.messages[3].payload["output"] == {"skill": "code-audit-finding", "content": "body"}


def test_query_loop_defaults_stop_reason_when_model_omits_it():
    store = build_store()
    session_id = store.create_session(project_id="project-1", system_prompt="system prompt")
    loop = QueryLoop(session_store=store, model_client=FakeModelClient(responses=[{"content": "done"}]), tool_registry=ToolRegistry(), tool_orchestrator=None)

    result = asyncio.run(loop.run_turn(session_id=session_id, model_name="gpt-test"))

    assert result.stop_reason is RuntimeStopReason.ASSISTANT_TURN_COMPLETE


def test_query_loop_executes_textual_tool_call_fallback():
    store = build_store()
    session_id = store.create_session(project_id="project-1", system_prompt="system")
    store.append_message(session_id, TranscriptItem(role=RuntimeMessageRole.USER, content="inspect code"))
    client = FakeModelClient(
        responses=[
            {
                "content": "Thought: inspect a file first.\nTool Call: echo\n{\"text\": \"repo summary\"}",
                "stop_reason": RuntimeStopReason.ASSISTANT_TURN_COMPLETE.value,
                "tool_calls": [],
            },
            {
                "content": "Final answer",
                "stop_reason": RuntimeStopReason.ASSISTANT_TURN_COMPLETE.value,
                "tool_calls": [],
            },
        ]
    )
    registry = ToolRegistry([EchoTool()])
    orchestrator = ToolOrchestrator(session_store=store, tool_registry=registry)
    runner = FindingRuntimeRunner(
        session_store=store,
        model_client=client,
        tool_registry=registry,
        tool_orchestrator=orchestrator,
    )

    result = asyncio.run(runner.run_once(session_id=session_id, model_name="gpt-test"))
    snapshot = store.load_session_snapshot(session_id)

    assert result.stop_reason is RuntimeStopReason.ASSISTANT_TURN_COMPLETE
    assert snapshot.messages[2].role == RuntimeMessageRole.TOOL_USE.value
    assert snapshot.messages[2].payload["tool_name"] == "echo"
    assert snapshot.messages[3].payload["output"] == {"echo": "repo summary"}


def test_query_loop_ignores_textual_tool_calls_without_orchestrator_when_no_tools_are_exposed():
    store = build_store()
    session_id = store.create_session(project_id="project-1", system_prompt="system")
    store.append_message(session_id, TranscriptItem(role=RuntimeMessageRole.USER, content="finalize"))
    client = FakeModelClient(
        responses=[
            {
                "content": "Tool Call: Read\n{\"file_path\": \"README.md\"}",
                "stop_reason": RuntimeStopReason.ASSISTANT_TURN_COMPLETE.value,
                "tool_calls": [],
            }
        ]
    )
    loop = QueryLoop(session_store=store, model_client=client, tool_registry=ToolRegistry([]), tool_orchestrator=None)

    result = asyncio.run(loop.run_turn(session_id=session_id, model_name="gpt-test"))
    snapshot = store.load_session_snapshot(session_id)

    assert result.stop_reason is RuntimeStopReason.ASSISTANT_TURN_COMPLETE
    assert snapshot.turns[-1].status == "completed"
    assert [message.role for message in snapshot.messages] == [
        RuntimeMessageRole.USER.value,
        RuntimeMessageRole.ASSISTANT.value,
    ]
    assert snapshot.checkpoints[-1].state_payload["tool_call_ids"] == []
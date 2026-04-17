from __future__ import annotations

import asyncio

from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.audit_session import AuditCheckpointType, AuditToolCallStatus
from app.services.finding_runtime.models import ToolCallRequest, ToolExecutionPayload
from app.services.agent.tools.todo_runtime_tool import TodoWriteRuntimeTool
from app.services.finding_runtime.session_store import AuditSessionStore
from app.services.runtime_core.tool_runtime import (
    RuntimeTool,
    ToolExecutionContext,
    ToolOrchestrator,
    ToolRegistry,
)


class EchoInput(BaseModel):
    text: str


class ReadTool(RuntimeTool):
    name = "Read"
    description = "Read text"
    input_model = EchoInput

    def is_concurrency_safe(self, parsed_input: EchoInput) -> bool:
        return True

    async def execute(self, parsed_input: EchoInput, context: ToolExecutionContext) -> ToolExecutionPayload:
        return ToolExecutionPayload(
            content=f"read:{parsed_input.text}",
            output_payload={"echo": parsed_input.text, "agent": context.agent_type},
        )


class WriteTool(RuntimeTool):
    name = "Write"
    description = "Write text"
    input_model = EchoInput

    async def execute(self, parsed_input: EchoInput, context: ToolExecutionContext) -> ToolExecutionPayload:
        return ToolExecutionPayload(
            content=f"write:{parsed_input.text}",
            output_payload={"echo": parsed_input.text},
        )


class SkillTool(RuntimeTool):
    name = "Skill"
    description = "Skill tool"
    input_model = EchoInput

    async def execute(self, parsed_input: EchoInput, context: ToolExecutionContext) -> ToolExecutionPayload:
        return ToolExecutionPayload(
            content="skill invoked",
            output_payload={"skill": parsed_input.text},
        )


def build_store() -> AuditSessionStore:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return AuditSessionStore(session_factory=session_factory)


def seed_skill_runtime_state(store: AuditSessionStore, session_id: str) -> None:
    runtime_state = store.load_runtime_state(session_id)
    runtime_state.record_skill_contract(
        agent_type="finding",
        skill_ref="code-audit-finding",
        contract={
            "allowed_tools": ["Read"],
            "hooks": {
                "PreToolUse": [{"matcher": "*", "hooks": ["log-pre"]}],
                "PostToolUse": [{"matcher": "*", "hooks": ["log-post"]}],
                "PermissionDenied": [{"matcher": "*", "hooks": ["deny-log"]}],
            },
        },
    )
    store.replace_runtime_state(session_id, runtime_state)


def test_shared_tool_runtime_enforces_allowed_tools_and_records_denial_hooks():
    store = build_store()
    session_id = store.create_session(project_id="project-1")
    turn_id = store.open_turn(session_id, model_name="gpt-test")
    seed_skill_runtime_state(store, session_id)
    registry = ToolRegistry([WriteTool()])
    orchestrator = ToolOrchestrator(session_store=store, tool_registry=registry, agent_type="finding")

    records = asyncio.run(
        orchestrator.execute_tool_calls(
            session_id=session_id,
            turn_id=turn_id,
            tool_calls=[ToolCallRequest(id="tool-1", name="Write", input={"text": "secret"})],
        )
    )

    snapshot = store.load_session_snapshot(session_id)

    assert records[0].status == AuditToolCallStatus.DENIED.value
    assert "allowed_tools" in (records[0].error_message or "")
    assert snapshot.tool_calls[0].status == AuditToolCallStatus.DENIED.value
    assert snapshot.checkpoints[0].checkpoint_type == AuditCheckpointType.AUTO.value
    assert snapshot.checkpoints[0].state_payload["event"] == "PermissionDenied"
    assert snapshot.checkpoints[0].state_payload["tool_name"] == "Write"


def test_shared_tool_runtime_emits_pre_and_post_hooks_for_allowed_tool():
    store = build_store()
    session_id = store.create_session(project_id="project-1")
    turn_id = store.open_turn(session_id, model_name="gpt-test")
    seed_skill_runtime_state(store, session_id)
    registry = ToolRegistry([ReadTool()])
    orchestrator = ToolOrchestrator(session_store=store, tool_registry=registry, agent_type="finding")

    records = asyncio.run(
        orchestrator.execute_tool_calls(
            session_id=session_id,
            turn_id=turn_id,
            tool_calls=[ToolCallRequest(id="tool-1", name="Read", input={"text": "alpha"})],
        )
    )

    snapshot = store.load_session_snapshot(session_id)

    assert records[0].status == AuditToolCallStatus.COMPLETED.value
    assert records[0].result.output_payload == {"echo": "alpha", "agent": "finding"}
    assert [checkpoint.state_payload["event"] for checkpoint in snapshot.checkpoints] == ["PreToolUse", "PostToolUse"]


class ScopedReadInput(BaseModel):
    text: str
    scope: str


class ScopedConcurrentTool(RuntimeTool):
    name = "ScopedRead"
    description = "Scoped concurrent tool"
    input_model = ScopedReadInput

    def __init__(self, events: list[tuple[str, str]]):
        self._events = events

    def is_concurrency_safe(self, parsed_input: ScopedReadInput) -> bool:
        return True

    def concurrency_key(self, parsed_input: ScopedReadInput) -> str | None:
        return parsed_input.scope

    async def execute(self, parsed_input: ScopedReadInput, context: ToolExecutionContext) -> ToolExecutionPayload:
        self._events.append(("start", f"{parsed_input.scope}:{parsed_input.text}"))
        await asyncio.sleep(0.01)
        self._events.append(("end", f"{parsed_input.scope}:{parsed_input.text}"))
        return ToolExecutionPayload(
            content=f"scoped:{parsed_input.text}",
            output_payload={"scope": parsed_input.scope, "echo": parsed_input.text},
        )


def test_shared_tool_runtime_serializes_conflicting_concurrency_keys():
    store = build_store()
    session_id = store.create_session(project_id="project-1")
    turn_id = store.open_turn(session_id, model_name="gpt-test")
    events: list[tuple[str, str]] = []
    registry = ToolRegistry([ScopedConcurrentTool(events)])
    orchestrator = ToolOrchestrator(session_store=store, tool_registry=registry, agent_type="finding")

    records = asyncio.run(
        orchestrator.execute_tool_calls(
            session_id=session_id,
            turn_id=turn_id,
            tool_calls=[
                ToolCallRequest(id="tool-1", name="ScopedRead", input={"text": "alpha", "scope": "fs"}),
                ToolCallRequest(id="tool-2", name="ScopedRead", input={"text": "beta", "scope": "fs"}),
                ToolCallRequest(id="tool-3", name="ScopedRead", input={"text": "gamma", "scope": "net"}),
            ],
        )
    )

    assert [record.status for record in records] == [AuditToolCallStatus.COMPLETED.value] * 3
    assert events[0] == ("start", "fs:alpha")
    assert events[1] == ("end", "fs:alpha")
    assert events[2] == ("start", "fs:beta")
    assert events[3] == ("start", "net:gamma")


def test_shared_tool_runtime_converts_ask_permission_rules_into_denied_tool_records():
    store = build_store()
    session_id = store.create_session(project_id="project-1")
    turn_id = store.open_turn(session_id, model_name="gpt-test")
    runtime_state = store.load_runtime_state(session_id)
    runtime_state.metadata["permission_rules"] = {
        "finding": {
            "Write": {"mode": "ask", "reason": "Need human approval before write actions."}
        }
    }
    store.replace_runtime_state(session_id, runtime_state)
    registry = ToolRegistry([WriteTool()])
    orchestrator = ToolOrchestrator(session_store=store, tool_registry=registry, agent_type="finding")

    records = asyncio.run(
        orchestrator.execute_tool_calls(
            session_id=session_id,
            turn_id=turn_id,
            tool_calls=[ToolCallRequest(id="tool-1", name="Write", input={"text": "secret"})],
        )
    )

    snapshot = store.load_session_snapshot(session_id)

    assert records[0].status == AuditToolCallStatus.DENIED.value
    assert "approval" in (records[0].error_message or "").lower()
    assert snapshot.tool_calls[0].status == AuditToolCallStatus.DENIED.value
    assert snapshot.checkpoints[0].state_payload["event"] == "PermissionDenied"
    assert snapshot.checkpoints[0].state_payload["source"] == "permission_rule"


def test_shared_tool_runtime_keeps_system_interaction_tools_available_under_skill_permissions():
    store = build_store()
    session_id = store.create_session(project_id="project-1")
    turn_id = store.open_turn(session_id, model_name="gpt-test")
    seed_skill_runtime_state(store, session_id)
    registry = ToolRegistry([TodoWriteRuntimeTool(store)])
    orchestrator = ToolOrchestrator(session_store=store, tool_registry=registry, agent_type="finding")

    records = asyncio.run(
        orchestrator.execute_tool_calls(
            session_id=session_id,
            turn_id=turn_id,
            tool_calls=[
                ToolCallRequest(
                    id="tool-1",
                    name="TodoWrite",
                    input={"title": "Capture exploit chain", "details": "Confirm auth bypass path"},
                )
            ],
        )
    )

    runtime_state = store.load_runtime_state(session_id)
    agent_state = runtime_state.agent_states["finding"]

    assert records[0].status == AuditToolCallStatus.COMPLETED.value
    assert agent_state.pending_todos[0]["title"] == "Capture exploit chain"
    assert agent_state.pending_todos[0]["details"] == "Confirm auth bypass path"


def test_shared_tool_runtime_keeps_skill_tool_available_under_skill_permissions():
    store = build_store()
    session_id = store.create_session(project_id="project-1")
    turn_id = store.open_turn(session_id, model_name="gpt-test")
    seed_skill_runtime_state(store, session_id)
    registry = ToolRegistry([SkillTool()])
    orchestrator = ToolOrchestrator(session_store=store, tool_registry=registry, agent_type="finding")

    records = asyncio.run(
        orchestrator.execute_tool_calls(
            session_id=session_id,
            turn_id=turn_id,
            tool_calls=[ToolCallRequest(id="tool-1", name="Skill", input={"text": "code-audit-finding"})],
        )
    )

    assert records[0].status == AuditToolCallStatus.COMPLETED.value
    assert records[0].result.output_payload == {"skill": "code-audit-finding"}
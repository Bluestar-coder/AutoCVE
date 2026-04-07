from __future__ import annotations

import asyncio

from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.audit_session import AuditToolCallStatus
from app.services.finding_runtime.models import ToolCallRequest, ToolExecutionPayload
from app.services.finding_runtime.session_store import AuditSessionStore
from app.services.finding_runtime.tooling import (
    RuntimeTool,
    ToolExecutionContext,
    ToolOrchestrator,
    ToolPermissionDecision,
    ToolRegistry,
)


class EchoInput(BaseModel):
    text: str


class ConcurrentEchoTool(RuntimeTool):
    name = "echo"
    description = "Echo text"
    input_model = EchoInput

    def __init__(self, events: list[tuple[str, str]]):
        self._events = events

    def is_concurrency_safe(self, parsed_input: EchoInput) -> bool:
        return True

    async def execute(self, parsed_input: EchoInput, context: ToolExecutionContext) -> ToolExecutionPayload:
        self._events.append(("start", parsed_input.text))
        await asyncio.sleep(0.01)
        self._events.append(("end", parsed_input.text))
        return ToolExecutionPayload(
            content=f"echo:{parsed_input.text}",
            output_payload={"echo": parsed_input.text},
        )


class DeniedWriteTool(RuntimeTool):
    name = "write_file"
    description = "Denied write"
    input_model = EchoInput

    async def check_permission(self, parsed_input: EchoInput, context: ToolExecutionContext) -> ToolPermissionDecision:
        return ToolPermissionDecision(allowed=False, reason="write access denied")

    async def execute(self, parsed_input: EchoInput, context: ToolExecutionContext) -> ToolExecutionPayload:
        raise AssertionError("execute should not run when permission is denied")


def build_store() -> AuditSessionStore:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return AuditSessionStore(session_factory=session_factory)


def test_tool_orchestrator_batches_concurrency_safe_tools_and_persists_results():
    store = build_store()
    session_id = store.create_session(project_id="project-1")
    turn_id = store.open_turn(session_id, model_name="gpt-test")
    events: list[tuple[str, str]] = []
    registry = ToolRegistry([ConcurrentEchoTool(events)])
    orchestrator = ToolOrchestrator(session_store=store, tool_registry=registry)

    records = asyncio.run(
        orchestrator.execute_tool_calls(
            session_id=session_id,
            turn_id=turn_id,
            tool_calls=[
                ToolCallRequest(id="tool-1", name="echo", input={"text": "alpha"}),
                ToolCallRequest(id="tool-2", name="echo", input={"text": "beta"}),
            ],
        )
    )

    assert [record.status for record in records] == [AuditToolCallStatus.COMPLETED.value, AuditToolCallStatus.COMPLETED.value]
    assert events[:2] == [("start", "alpha"), ("start", "beta")]
    snapshot = store.load_session_snapshot(session_id)
    assert len(snapshot.tool_calls) == 2
    assert snapshot.tool_calls[0].is_concurrency_safe is True
    assert snapshot.tool_calls[1].output_payload == {"echo": "beta"}


def test_tool_orchestrator_records_permission_denials_without_running_tool():
    store = build_store()
    session_id = store.create_session(project_id="project-1")
    turn_id = store.open_turn(session_id, model_name="gpt-test")
    registry = ToolRegistry([DeniedWriteTool()])
    orchestrator = ToolOrchestrator(session_store=store, tool_registry=registry)

    records = asyncio.run(
        orchestrator.execute_tool_calls(
            session_id=session_id,
            turn_id=turn_id,
            tool_calls=[ToolCallRequest(id="tool-1", name="write_file", input={"text": "secret"})],
        )
    )

    assert records[0].status == AuditToolCallStatus.DENIED.value
    assert records[0].error_message == "write access denied"
    snapshot = store.load_session_snapshot(session_id)
    assert snapshot.tool_calls[0].status == AuditToolCallStatus.DENIED.value
    assert snapshot.tool_calls[0].error_message == "write access denied"

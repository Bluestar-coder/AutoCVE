from __future__ import annotations

import re

from app.models.audit_session import AuditCheckpointType
from app.services.agent.json_parser import AgentJsonParser
from app.services.finding_runtime.models import (
    RuntimeMessageRole,
    RuntimeStopReason,
    ToolCallRequest,
    TranscriptItem,
    TurnExecutionResult,
)


class QueryLoop:
    def __init__(self, *, session_store, model_client, tool_registry=None, tool_orchestrator=None):
        self._session_store = session_store
        self._model_client = model_client
        self._tool_registry = tool_registry
        self._tool_orchestrator = tool_orchestrator

    async def run_turn(self, *, session_id: str, model_name: str) -> TurnExecutionResult:
        snapshot = self._session_store.load_session_snapshot(session_id)
        turn_id = self._session_store.open_turn(session_id, model_name=model_name)
        tool_definitions = self._tool_registry.describe_tools() if self._tool_registry is not None else []
        transcript = [
            TranscriptItem(
                role=RuntimeMessageRole(message.role),
                content=message.content,
                name=message.name,
                metadata=dict(message.message_metadata or {}),
                payload=dict(message.payload or {}),
            )
            for message in snapshot.messages
        ]
        response = await self._model_client.complete(
            system_prompt=snapshot.session.system_prompt,
            recon_payload=snapshot.session.recon_payload or {},
            transcript=transcript,
            model_name=model_name,
            tool_definitions=tool_definitions,
        )

        assistant_message_id = None
        if response.get("content"):
            assistant_message_id = self._session_store.append_message(
                session_id,
                TranscriptItem(
                    role=RuntimeMessageRole.ASSISTANT,
                    content=response.get("content", ""),
                ),
            )

        raw_tool_calls = list(response.get("tool_calls") or [])
        if not raw_tool_calls and response.get("content") and tool_definitions and self._tool_orchestrator is not None:
            raw_tool_calls = self._extract_text_tool_calls(response.get("content", ""))

        tool_requests = [
            ToolCallRequest(
                id=item.get("id") or f"tool-use-{index + 1}",
                name=item["name"],
                input=dict(item.get("input") or {}),
            )
            for index, item in enumerate(raw_tool_calls)
        ]
        tool_result_message_ids: list[str] = []
        tool_call_ids: list[str] = []

        if tool_requests:
            for request in tool_requests:
                self._session_store.append_message(
                    session_id,
                    TranscriptItem(
                        role=RuntimeMessageRole.TOOL_USE,
                        content=request.name,
                        name=request.name,
                        payload={
                            "tool_use_id": request.id,
                            "tool_name": request.name,
                            "input": request.input,
                        },
                    ),
                )

            if self._tool_orchestrator is None:
                if tool_definitions:
                    raise RuntimeError("Tool calls were returned but no tool orchestrator is configured")
                self._session_store.close_turn(turn_id, status="tool_calls_ignored")
                stop_reason = RuntimeStopReason.ASSISTANT_TURN_COMPLETE
                self._session_store.create_checkpoint(
                    session_id=session_id,
                    turn_id=turn_id,
                    checkpoint_type=AuditCheckpointType.AUTO,
                    state_payload={
                        "stop_reason": stop_reason.value,
                        "assistant_message_id": assistant_message_id,
                        "tool_call_ids": [],
                        "ignored_tool_calls": [request.name for request in tool_requests],
                    },
                )
                return TurnExecutionResult(
                    turn_id=turn_id,
                    stop_reason=stop_reason,
                    assistant_message_id=assistant_message_id,
                    tool_call_ids=[],
                    tool_result_message_ids=[],
                )

            records = await self._tool_orchestrator.execute_tool_calls(
                session_id=session_id,
                turn_id=turn_id,
                tool_calls=tool_requests,
                session=snapshot.session,
                recon_payload=snapshot.session.recon_payload or {},
            )
            for record in records:
                tool_call_ids.append(record.tool_call_id)
                tool_result_message_ids.append(
                    self._session_store.append_message(
                        session_id,
                        TranscriptItem(
                            role=RuntimeMessageRole.TOOL_RESULT,
                            content=record.result.content,
                            name=record.request.name,
                            metadata={
                                "status": record.status,
                                "is_error": record.result.is_error,
                                "duration_ms": record.duration_ms,
                            },
                            payload={
                                "tool_use_id": record.request.id,
                                "tool_call_id": record.tool_call_id,
                                "tool_name": record.request.name,
                                "input": record.request.input,
                                "output": record.result.output_payload,
                                "error_message": record.error_message,
                            },
                        ),
                    )
                )
            stop_reason = RuntimeStopReason.TOOL_EXECUTION_CONTINUE
            self._session_store.close_turn(turn_id, status="tool_results_ready")
        else:
            stop_reason = self._coerce_stop_reason(response.get("stop_reason"))
            self._session_store.close_turn(turn_id, status="completed")

        self._session_store.create_checkpoint(
            session_id=session_id,
            turn_id=turn_id,
            checkpoint_type=AuditCheckpointType.AUTO,
            state_payload={
                "stop_reason": stop_reason.value,
                "assistant_message_id": assistant_message_id,
                "tool_call_ids": tool_call_ids,
            },
        )
        return TurnExecutionResult(
            turn_id=turn_id,
            stop_reason=stop_reason,
            assistant_message_id=assistant_message_id,
            tool_call_ids=tool_call_ids,
            tool_result_message_ids=tool_result_message_ids,
        )

    @staticmethod
    def _coerce_stop_reason(value: str | None) -> RuntimeStopReason:
        if not value:
            return RuntimeStopReason.ASSISTANT_TURN_COMPLETE
        try:
            return RuntimeStopReason(value)
        except ValueError:
            return RuntimeStopReason.ASSISTANT_TURN_COMPLETE

    @staticmethod
    def _extract_text_tool_calls(content: str) -> list[dict[str, object]]:
        text = (content or '').strip()
        if not text:
            return []

        tool_call_match = re.search(r'Tool Call:\s*([A-Za-z_][A-Za-z0-9_]*)\s*(.*)$', text, re.DOTALL)
        if tool_call_match:
            tool_name = tool_call_match.group(1).strip()
            payload_text = tool_call_match.group(2).strip()
            parsed_payload = AgentJsonParser.parse_any(payload_text, default={})
            if isinstance(parsed_payload, dict) and isinstance(parsed_payload.get('input'), dict):
                tool_input = dict(parsed_payload.get('input') or {})
            elif isinstance(parsed_payload, dict):
                tool_input = parsed_payload
            else:
                tool_input = {}
            return [{'id': 'text-tool-call-1', 'name': tool_name, 'input': tool_input}]

        action_match = re.search(r'Action:\s*([A-Za-z_][A-Za-z0-9_]*)\s*Action Input:\s*(.*)$', text, re.DOTALL)
        if action_match:
            tool_name = action_match.group(1).strip()
            parsed_payload = AgentJsonParser.parse_any(action_match.group(2).strip(), default={})
            if isinstance(parsed_payload, dict):
                return [{'id': 'text-tool-call-1', 'name': tool_name, 'input': dict(parsed_payload)}]
        return []

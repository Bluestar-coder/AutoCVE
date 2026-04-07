from __future__ import annotations

from app.services.finding_runtime.models import RuntimeSessionState, RuntimeStopReason, TurnExecutionResult
from app.services.finding_runtime.query_loop import QueryLoop


class FindingRuntimeRunner:
    def __init__(self, *, session_store, model_client, tool_registry=None, tool_orchestrator=None, max_turns: int = 8):
        self._session_store = session_store
        self._max_turns = max_turns
        self._query_loop = QueryLoop(
            session_store=session_store,
            model_client=model_client,
            tool_registry=tool_registry,
            tool_orchestrator=tool_orchestrator,
        )

    async def run_once(self, *, session_id: str, model_name: str) -> TurnExecutionResult:
        self._session_store.update_session_state(session_id, RuntimeSessionState.RUNNING)
        last_result: TurnExecutionResult | None = None
        try:
            for _ in range(self._max_turns):
                last_result = await self._query_loop.run_turn(session_id=session_id, model_name=model_name)
                if last_result.stop_reason is not RuntimeStopReason.TOOL_EXECUTION_CONTINUE:
                    self._session_store.update_session_state(session_id, RuntimeSessionState.COMPLETED)
                    return last_result
            self._session_store.update_session_state(session_id, RuntimeSessionState.FAILED)
            return TurnExecutionResult(
                turn_id=last_result.turn_id if last_result is not None else "",
                stop_reason=RuntimeStopReason.MAX_TURNS_EXCEEDED,
                assistant_message_id=last_result.assistant_message_id if last_result is not None else None,
                tool_call_ids=list(last_result.tool_call_ids) if last_result is not None else [],
                tool_result_message_ids=list(last_result.tool_result_message_ids) if last_result is not None else [],
            )
        except Exception:
            self._session_store.update_session_state(session_id, RuntimeSessionState.FAILED)
            raise

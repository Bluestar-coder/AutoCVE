from __future__ import annotations

from typing import Any, Callable

from app.db.session import get_sync_session_factory
from app.services.audit_chat_runtime.adapter import AuditChatRuntimeAdapter
from app.services.audit_chat_runtime.prompts import AUDIT_CHAT_NATIVE_TOOL_REMINDER
from app.services.finding_runtime.bridge import RuntimeLLMModelClient
from app.services.finding_runtime.runner import FindingRuntimeRunner
from app.services.finding_runtime.session_store import AuditSessionStore
from app.services.finding_runtime.tooling import ToolOrchestrator, ToolRegistry
from app.services.runtime_core import build_runtime_tool_registry
from app.services.runtime_core.tool_message_codec import (
    ToolMessageFormat,
    build_runtime_model_messages,
)


class AuditChatRuntimeModelClient(RuntimeLLMModelClient):
    def __init__(self, *, llm_service):
        super().__init__(llm_service=llm_service, agent_type="audit_chat")

    @staticmethod
    def _build_messages(
        *,
        system_prompt: str | None,
        recon_payload: dict[str, Any],
        transcript: list[Any],
        tool_definitions: list[dict[str, Any]] | None = None,
        tool_message_format: ToolMessageFormat | str = ToolMessageFormat.OPENAI_TOOLS,
    ) -> list[dict[str, Any]]:
        del recon_payload
        effective_system_prompt = (system_prompt or "").strip()
        if tool_definitions:
            effective_system_prompt = (
                f"{effective_system_prompt}\n\n{AUDIT_CHAT_NATIVE_TOOL_REMINDER}".strip()
                if effective_system_prompt
                else AUDIT_CHAT_NATIVE_TOOL_REMINDER
            )
        return build_runtime_model_messages(
            system_prompt=effective_system_prompt,
            recon_payload={},
            transcript=transcript,
            tool_definitions=tool_definitions,
            tool_message_format=tool_message_format,
        )


class AuditChatRuntimeBridge:
    def __init__(self, *, llm_service, tools: dict[str, Any], user_id: str | None = None):
        self._llm_service = llm_service
        self._tools = tools
        self._user_id = user_id
        self._session_store = AuditSessionStore(session_factory=get_sync_session_factory())

    async def continue_chat_session(
        self,
        *,
        session_id: str,
        model_name: str = "audit-chat-runtime",
        max_turns: int | None = None,
        event_sink: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        model_client = AuditChatRuntimeModelClient(llm_service=self._llm_service)
        tool_registry = self._build_tool_registry()
        tool_orchestrator = ToolOrchestrator(session_store=self._session_store, tool_registry=tool_registry)
        runner = FindingRuntimeRunner(
            session_store=self._session_store,
            model_client=model_client,
            tool_registry=tool_registry,
            tool_orchestrator=tool_orchestrator,
            max_turns=max_turns,
            event_sink=event_sink,
            require_terminal_action=False,
        )
        adapter = AuditChatRuntimeAdapter(
            session_store=self._session_store,
            runner=runner,
        )
        runner_result = await adapter.run_once(session_id=session_id, model_name=model_name)
        return {
            "session_id": session_id,
            "runner_result": runner_result,
        }

    def _build_tool_registry(self) -> ToolRegistry:
        full_registry = build_runtime_tool_registry(
            session_store=self._session_store,
            agent_tools=self._tools,
            agent_type="audit_chat",
            user_id=self._user_id,
            include_finding_finalizer=False,
            include_report_finalizer=False,
        )
        blocked = {"FinalizeFinding", "FinalizeVulnerabilityReports", "FinalizeTriage", "FinalizeTriageBatch"}
        return ToolRegistry([tool for tool in full_registry.all_tools() if tool.name not in blocked])

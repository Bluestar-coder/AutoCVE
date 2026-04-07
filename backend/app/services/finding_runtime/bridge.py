from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from app.db.session import get_sync_session_factory
from app.services.agent.json_parser import AgentJsonParser
from app.services.agent.tools.base import AgentTool
from app.services.finding_runtime.adapters.finding import FindingRuntimeAdapter
from app.services.finding_runtime.models import RuntimeMessageRole, TranscriptItem
from app.services.finding_runtime.memory import RuntimeMemoryManager
from app.services.finding_runtime.runner import FindingRuntimeRunner
from app.services.finding_runtime.session_store import AuditSessionStore
from app.services.finding_runtime.skills import RuntimeSkillCatalog, RuntimeSkillTool
from app.services.finding_runtime.tooling import RuntimeTool, ToolExecutionContext, ToolExecutionPayload, ToolOrchestrator, ToolRegistry


READ_SAFE_RUNTIME_TOOLS = {"Read", "Glob", "Grep", "Skill"}
INTERNAL_TOOL_NAMES = {"think", "reflect", "load_skill_body", "skill_resource_lookup"}
RUNTIME_FINALIZATION_PROMPT = (
    "Stop auditing now and return the final report as JSON only. "
    "Do not call more tools unless absolutely required for the final answer. "
    "Return an object with keys: findings (array) and summary (string). "
    "If no CVE-grade issue is supported, return findings=[] and explain the reviewed attack surfaces in summary."
)


class ReadToolInput(BaseModel):
    file_path: str | None = Field(default=None, description="Path to a file relative to the project root.")
    file_paths: list[str] = Field(default_factory=list, description="Optional batch of related files to read together.")
    start_line: int | None = Field(default=None, description="Optional 1-based start line.")
    end_line: int | None = Field(default=None, description="Optional inclusive end line.")
    max_lines: int = Field(default=400, description="Maximum lines to return per file.")
    max_files: int = Field(default=6, description="Maximum files when batch reading.")


class GlobToolInput(BaseModel):
    path: str = Field(default=".", description="Directory relative to the project root.")
    pattern: str | None = Field(default=None, description="Optional glob pattern, for example **/*.java or *.xml.")
    recursive: bool = Field(default=True, description="Whether to walk child directories.")
    max_results: int = Field(default=120, description="Maximum files to return.")


class GrepToolInput(BaseModel):
    pattern: str = Field(description="Keyword or regular expression to search for.")
    path: str | None = Field(default=None, description="Optional directory relative to the project root.")
    glob: str | None = Field(default=None, description="Optional glob such as *.py or **/*.java.")
    case_sensitive: bool = Field(default=False, description="Whether the search is case sensitive.")
    max_results: int = Field(default=80, description="Maximum number of matches to return.")
    is_regex: bool = Field(default=False, description="Whether pattern should be treated as regex.")


def _result_to_payload(result: Any) -> ToolExecutionPayload:
    output_payload = result.to_dict()
    return ToolExecutionPayload(
        content=result.to_string(),
        output_payload=output_payload,
        metadata={"success": result.success, **(result.metadata or {})},
        is_error=not result.success,
    )


class CanonicalReadTool(RuntimeTool):
    name = "Read"
    description = (
        "Read one file or a small batch of closely related files from the project. "
        "Prefer this for controllers, services, config, SQL, XML, and skill reference files."
    )
    input_model = ReadToolInput

    def __init__(self, *, read_tool: AgentTool | None, read_many_tool: AgentTool | None = None):
        self._read_tool = read_tool
        self._read_many_tool = read_many_tool

    def validate_input(self, raw_input: dict[str, Any]) -> ReadToolInput:
        payload = dict(raw_input or {})
        normalized = {
            "file_path": payload.get("file_path") or payload.get("path") or payload.get("file"),
            "file_paths": list(payload.get("file_paths") or payload.get("paths") or []),
            "start_line": payload.get("start_line") or payload.get("from_line"),
            "end_line": payload.get("end_line") or payload.get("to_line"),
            "max_lines": payload.get("max_lines") or payload.get("limit") or 400,
            "max_files": payload.get("max_files") or 6,
        }
        if not normalized["file_path"] and normalized["file_paths"]:
            normalized["file_path"] = normalized["file_paths"][0]
        return ReadToolInput.model_validate(normalized)

    def is_concurrency_safe(self, parsed_input: Any) -> bool:
        return True

    async def execute(self, parsed_input: ReadToolInput, context: ToolExecutionContext) -> ToolExecutionPayload:
        del context
        file_paths = [item for item in parsed_input.file_paths if str(item or "").strip()]
        if len(file_paths) > 1:
            if self._read_many_tool is None:
                raise ValueError("Batch file reading is not available in this runtime.")
            result = await self._read_many_tool.execute(
                file_paths=file_paths,
                start_line=parsed_input.start_line,
                end_line=parsed_input.end_line,
                max_lines=parsed_input.max_lines,
                max_files=parsed_input.max_files,
            )
            return _result_to_payload(result)

        if self._read_tool is None or not parsed_input.file_path:
            raise ValueError("Read requires file_path or file_paths.")
        result = await self._read_tool.execute(
            file_path=parsed_input.file_path,
            start_line=parsed_input.start_line,
            end_line=parsed_input.end_line,
            max_lines=parsed_input.max_lines,
        )
        return _result_to_payload(result)


class CanonicalGlobTool(RuntimeTool):
    name = "Glob"
    description = "List files under the project root with an optional glob filter."
    input_model = GlobToolInput

    def __init__(self, *, list_tool: AgentTool):
        self._list_tool = list_tool

    def validate_input(self, raw_input: dict[str, Any]) -> GlobToolInput:
        payload = dict(raw_input or {})
        normalized = {
            "path": payload.get("path") or payload.get("directory") or ".",
            "pattern": payload.get("pattern") or payload.get("glob"),
            "recursive": payload.get("recursive", True),
            "max_results": payload.get("max_results") or payload.get("max_files") or 120,
        }
        return GlobToolInput.model_validate(normalized)

    def is_concurrency_safe(self, parsed_input: Any) -> bool:
        return True

    async def execute(self, parsed_input: GlobToolInput, context: ToolExecutionContext) -> ToolExecutionPayload:
        del context
        result = await self._list_tool.execute(
            directory=parsed_input.path,
            pattern=parsed_input.pattern,
            recursive=parsed_input.recursive,
            max_files=parsed_input.max_results,
        )
        return _result_to_payload(result)


class CanonicalGrepTool(RuntimeTool):
    name = "Grep"
    description = "Search code or config text across the repository with regex or keyword matching."
    input_model = GrepToolInput

    def __init__(self, *, search_tool: AgentTool):
        self._search_tool = search_tool

    def validate_input(self, raw_input: dict[str, Any]) -> GrepToolInput:
        payload = dict(raw_input or {})
        normalized = {
            "pattern": payload.get("pattern") or payload.get("query") or payload.get("keyword"),
            "path": payload.get("path") or payload.get("directory"),
            "glob": payload.get("glob") or payload.get("file_pattern"),
            "case_sensitive": payload.get("case_sensitive", False),
            "max_results": payload.get("max_results") or payload.get("limit") or 80,
            "is_regex": payload.get("is_regex", False),
        }
        return GrepToolInput.model_validate(normalized)

    def is_concurrency_safe(self, parsed_input: Any) -> bool:
        return True

    async def execute(self, parsed_input: GrepToolInput, context: ToolExecutionContext) -> ToolExecutionPayload:
        del context
        result = await self._search_tool.execute(
            keyword=parsed_input.pattern,
            file_pattern=parsed_input.glob,
            directory=parsed_input.path,
            case_sensitive=parsed_input.case_sensitive,
            max_results=parsed_input.max_results,
            is_regex=parsed_input.is_regex,
        )
        return _result_to_payload(result)


class RuntimeLLMModelClient:
    def __init__(self, *, llm_service, agent_type: str = "finding"):
        self._llm_service = llm_service
        self._agent_type = agent_type

    async def complete(
        self,
        *,
        system_prompt: str | None,
        recon_payload: dict[str, Any],
        transcript: list[Any],
        model_name: str,
        tool_definitions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        del model_name
        messages: list[dict[str, str]] = []
        effective_system_prompt = (system_prompt or "").strip()
        if recon_payload:
            recon_text = "Runtime recon payload:\n" + json.dumps(recon_payload, ensure_ascii=False, indent=2)
            effective_system_prompt = f"{effective_system_prompt}\n\n{recon_text}".strip() if effective_system_prompt else recon_text
        if effective_system_prompt:
            messages.append({"role": "system", "content": effective_system_prompt})
        messages.extend(mapped for item in transcript if (mapped := self._map_transcript_item(item)) is not None)
        response = await self._llm_service.chat_completion(
            messages=messages,
            agent_type=self._agent_type,
            tools=[self._to_llm_tool_schema(item) for item in tool_definitions],
            parallel_tool_calls=True,
        )
        return {
            "content": response.get("content", "") or "",
            "tool_calls": [self._normalize_tool_call(item) for item in response.get("tool_calls") or []],
            "stop_reason": response.get("finish_reason") or "stop",
        }

    @staticmethod
    def _to_llm_tool_schema(definition: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": definition.get("name", ""),
                "description": definition.get("description", ""),
                "parameters": definition.get("input_schema", {"type": "object"}),
            },
        }

    @staticmethod
    def _map_transcript_item(item: Any) -> dict[str, str] | None:
        role = str(getattr(item, "role", "user"))
        content = str(getattr(item, "content", "") or "")
        payload = getattr(item, "payload", {}) or {}
        if role == "system":
            return None
        if role == "assistant":
            return {"role": "assistant", "content": content}
        if role == "tool_use":
            tool_name = payload.get("tool_name") or getattr(item, "name", "tool")
            return {"role": "assistant", "content": f"Tool Call: {tool_name}\n{json.dumps(payload, ensure_ascii=False)}"}
        if role == "tool_result":
            return {"role": "user", "content": f"Tool Result:\n{content}"}
        if role == "handoff":
            target = payload.get("target") or "verification"
            return {"role": "user", "content": f"Handoff ({target}):\n{content}"}
        return {"role": "user", "content": content}

    @staticmethod
    def _normalize_tool_call(raw_tool_call: dict[str, Any]) -> dict[str, Any]:
        function_payload = raw_tool_call.get("function") if isinstance(raw_tool_call, dict) else None
        if not isinstance(function_payload, dict):
            function_payload = raw_tool_call
        raw_arguments = function_payload.get("arguments") if isinstance(function_payload, dict) else None
        parsed_arguments = AgentJsonParser.parse_any(raw_arguments, default={}) if isinstance(raw_arguments, str) else raw_arguments
        if not isinstance(parsed_arguments, dict):
            parsed_arguments = {"raw_input": parsed_arguments}
        return {
            "id": raw_tool_call.get("id") or function_payload.get("id") or "tool-call",
            "name": function_payload.get("name") or raw_tool_call.get("name") or "",
            "input": parsed_arguments,
        }


class FindingRuntimeBridge:
    def __init__(
        self,
        *,
        llm_service,
        tools: dict[str, AgentTool],
        user_id: str | None = None,
        session_factory=None,
    ):
        self._llm_service = llm_service
        self._tools = tools
        self._user_id = user_id
        self._session_store = AuditSessionStore(session_factory=session_factory or get_sync_session_factory())

    async def run(
        self,
        *,
        project_id: str,
        task_id: str | None,
        system_prompt: str,
        recon_payload: dict[str, Any],
        user_message: str,
        model_name: str = "finding-runtime",
        max_turns: int = 8,
    ) -> dict[str, Any]:
        model_client = RuntimeLLMModelClient(llm_service=self._llm_service, agent_type="finding")
        tool_registry = self._build_tool_registry()
        tool_orchestrator = ToolOrchestrator(session_store=self._session_store, tool_registry=tool_registry)
        runner = FindingRuntimeRunner(
            session_store=self._session_store,
            model_client=model_client,
            tool_registry=tool_registry,
            tool_orchestrator=tool_orchestrator,
            max_turns=max_turns,
        )
        adapter = FindingRuntimeAdapter(
            session_store=self._session_store,
            runner=runner,
            skill_catalog=RuntimeSkillCatalog(),
            memory_manager=RuntimeMemoryManager(session_factory=self._session_store._session_factory),
        )
        result = await adapter.run(
            project_id=project_id,
            task_id=task_id,
            system_prompt=system_prompt,
            recon_payload=recon_payload,
            user_message=user_message,
            model_name=model_name,
        )
        snapshot, final_payload = await self._ensure_final_payload(
            session_id=result["session_id"],
            model_name=model_name,
            max_turns=max_turns,
            model_client=model_client,
            tool_registry=tool_registry,
            tool_orchestrator=tool_orchestrator,
        )
        return {
            **result,
            "final_payload": final_payload,
            "turn_count": len(snapshot.turns),
            "tool_call_count": len(snapshot.tool_calls),
        }

    async def continue_session(
        self,
        *,
        session_id: str,
        model_name: str = "finding-runtime",
        max_turns: int = 8,
    ) -> dict[str, Any]:
        model_client = RuntimeLLMModelClient(llm_service=self._llm_service, agent_type="finding")
        tool_registry = self._build_tool_registry()
        tool_orchestrator = ToolOrchestrator(session_store=self._session_store, tool_registry=tool_registry)
        runner = FindingRuntimeRunner(
            session_store=self._session_store,
            model_client=model_client,
            tool_registry=tool_registry,
            tool_orchestrator=tool_orchestrator,
            max_turns=max_turns,
        )
        runner_result = await runner.run_once(session_id=session_id, model_name=model_name)
        snapshot, final_payload = await self._ensure_final_payload(
            session_id=session_id,
            model_name=model_name,
            max_turns=max_turns,
            model_client=model_client,
            tool_registry=tool_registry,
            tool_orchestrator=tool_orchestrator,
        )
        return {
            "session_id": session_id,
            "runner_result": runner_result,
            "final_payload": final_payload,
            "turn_count": len(snapshot.turns),
            "tool_call_count": len(snapshot.tool_calls),
        }

    def record_handoff(self, session_id: str, handoff_payload: dict[str, Any], *, status: str = "pending") -> str:
        return self._session_store.create_handoff(
            session_id=session_id,
            target=str(handoff_payload.get("to_agent") or "verification"),
            status=status,
            payload=handoff_payload,
        )

    async def _ensure_final_payload(
        self,
        *,
        session_id: str,
        model_name: str,
        max_turns: int,
        model_client: RuntimeLLMModelClient,
        tool_registry: ToolRegistry,
        tool_orchestrator: ToolOrchestrator,
    ) -> tuple[Any, dict[str, Any] | None]:
        del tool_registry, tool_orchestrator
        snapshot = self._session_store.load_session_snapshot(session_id)
        final_payload = self.extract_final_payload(snapshot)
        if final_payload is not None:
            return snapshot, final_payload

        finalizer_prompts = [
            RUNTIME_FINALIZATION_PROMPT,
            (
                'Return the final report now as strict JSON only. '
                'Do not request any more tools. '
                'The response must be a single JSON object with keys findings and summary.'
            ),
        ]

        finalizer_registry = ToolRegistry([])
        for index, prompt in enumerate(finalizer_prompts, start=1):
            self._session_store.append_message(
                session_id,
                TranscriptItem(
                    role=RuntimeMessageRole.USER,
                    name='runtime_finalizer' if index == 1 else f'runtime_finalizer_retry_{index}',
                    content=prompt,
                    metadata={'kind': 'finalization_prompt', 'attempt': index},
                ),
            )
            runner = FindingRuntimeRunner(
                session_store=self._session_store,
                model_client=model_client,
                tool_registry=finalizer_registry,
                tool_orchestrator=None,
                max_turns=max(1, min(2, max_turns)),
            )
            await runner.run_once(session_id=session_id, model_name=model_name)
            snapshot = self._session_store.load_session_snapshot(session_id)
            final_payload = self.extract_final_payload(snapshot)
            if final_payload is not None:
                return snapshot, final_payload

        final_payload = {
            'findings': [],
            'summary': self._fallback_summary(snapshot),
        }
        return snapshot, final_payload

    def _build_tool_registry(self) -> ToolRegistry:
        tools: list[RuntimeTool] = []

        read_tool = self._tools.get("read_file")
        if isinstance(read_tool, AgentTool):
            read_many_tool = self._tools.get("read_many_files")
            tools.append(
                CanonicalReadTool(
                    read_tool=read_tool,
                    read_many_tool=read_many_tool if isinstance(read_many_tool, AgentTool) else None,
                )
            )

        list_tool = self._tools.get("list_files")
        if isinstance(list_tool, AgentTool):
            tools.append(CanonicalGlobTool(list_tool=list_tool))

        search_tool = self._tools.get("search_code")
        if isinstance(search_tool, AgentTool):
            tools.append(CanonicalGrepTool(search_tool=search_tool))

        tools.append(
            RuntimeSkillTool(
                session_store=self._session_store,
                agent_type="finding",
                user_id=self._user_id,
            )
        )
        return ToolRegistry(tools)

    @staticmethod
    def extract_final_payload(snapshot: Any) -> dict[str, Any] | None:
        for message in reversed(getattr(snapshot, "messages", []) or []):
            if getattr(message, "role", "") != "assistant":
                continue
            payload = FindingRuntimeBridge._parse_payload(getattr(message, "content", "") or "")
            if payload is not None:
                return payload
        return None

    @staticmethod
    def _fallback_summary(snapshot: Any) -> str:
        assistant_messages = [
            (getattr(message, "content", "") or "").strip()
            for message in getattr(snapshot, "messages", []) or []
            if getattr(message, "role", "") == "assistant" and (getattr(message, "content", "") or "").strip()
        ]
        if assistant_messages:
            last_message = assistant_messages[-1]
            if len(last_message) > 500:
                last_message = last_message[:500] + "..."
            return (
                "Runtime finding session ended without a machine-parseable final JSON payload. "
                f"Last assistant message: {last_message}"
            )
        return "Runtime finding session ended without a machine-parseable final JSON payload."

    @staticmethod
    def _parse_payload(content: str) -> dict[str, Any] | None:
        text = (content or '').strip()
        if not text:
            return None

        candidates: list[str] = [text]
        marker_index = text.lower().rfind('final answer:')
        if marker_index != -1:
            candidates.append(text[marker_index + len('final answer:'):].strip())

        fenced_matches = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', text, flags=re.IGNORECASE)
        candidates.extend(item.strip() for item in fenced_matches if item.strip())
        candidates.extend(FindingRuntimeBridge._extract_json_objects(text))

        seen: set[str] = set()
        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            cleaned = re.sub(r'^Final Answer:\s*', '', candidate, flags=re.IGNORECASE)
            parsed = AgentJsonParser.parse_any(cleaned, default=None)
            if isinstance(parsed, dict) and ('findings' in parsed or 'summary' in parsed):
                findings = parsed.get('findings')
                if not isinstance(findings, list):
                    parsed['findings'] = []
                parsed['summary'] = str(parsed.get('summary') or '').strip()
                return parsed
        return None

    @staticmethod
    def _extract_json_objects(text: str) -> list[str]:
        objects: list[str] = []
        for start_index in [match.start() for match in re.finditer(r'\{', text)]:
            brace_count = 0
            in_string = False
            escape_next = False
            end_index = None
            for index in range(start_index, len(text)):
                char = text[index]
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\':
                    escape_next = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_index = index + 1
                        break
            if end_index is not None:
                objects.append(text[start_index:end_index].strip())
        return objects

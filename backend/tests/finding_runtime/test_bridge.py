from __future__ import annotations

import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.services.finding_runtime.bridge import FindingRuntimeBridge
from app.services.finding_runtime.models import RuntimeMemoryBundle, RuntimeMessageRole, TranscriptItem
from app.services.agent.tools.base import AgentTool, ToolResult


class FakeAgentTool(AgentTool):
    def __init__(self, name: str):
        super().__init__()
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Tool {self._name}"

    async def _execute(self, **kwargs):
        return ToolResult(success=True, data=kwargs)


class FakeLLMService:
    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.calls = []

    async def chat_completion(self, *, messages, agent_type, tools, parallel_tool_calls):
        assert agent_type == "finding"
        assert parallel_tool_calls is True
        assert tools is not None
        self.calls.append({"messages": messages, "tools": tools})
        if not self.responses:
            return {"content": "{}", "finish_reason": "stop"}
        return self.responses.pop(0)


def build_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_bridge_finalizes_non_json_assistant_reply(monkeypatch):
    async def fake_adapter_run(self, *, project_id, task_id, system_prompt, recon_payload, user_message, model_name):
        session_id = self._session_store.create_session(
            project_id=project_id,
            task_id=task_id,
            runtime_stack="runtime",
            system_prompt=system_prompt,
            recon_payload=recon_payload,
        )
        self._session_store.append_message(
            session_id, TranscriptItem(role=RuntimeMessageRole.USER, content=user_message)
        )
        self._session_store.append_message(
            session_id, TranscriptItem(role=RuntimeMessageRole.ASSISTANT, content="??????????")
        )
        return {
            "session_id": session_id,
            "runner_result": None,
            "skill_route": {},
            "memory_counts": {"instruction": 0, "recall": 0},
        }

    async def fake_skill_preload(self, *, user_id, agent_type, context):
        class Snapshot:
            available_skills = []
            matched_skills = []
            prompt = ""
            route_message = ""
            route_plan = {}

        return Snapshot()

    async def fake_memory_preload(self, *, agent_type, system_prompt, recon_payload, user_message, skill_context=None):
        return RuntimeMemoryBundle()

    monkeypatch.setattr(
        "app.services.finding_runtime.adapters.finding.FindingRuntimeAdapter.run",
        fake_adapter_run,
    )
    monkeypatch.setattr(
        "app.services.finding_runtime.skills.RuntimeSkillCatalog.preload",
        fake_skill_preload,
    )
    monkeypatch.setattr(
        "app.services.finding_runtime.memory.RuntimeMemoryManager.preload",
        fake_memory_preload,
    )

    llm = FakeLLMService(
        responses=[
            {
                "content": '{"findings": [], "summary": "???????"}',
                "finish_reason": "stop",
                "tool_calls": [],
            }
        ]
    )
    bridge = FindingRuntimeBridge(
        llm_service=llm,
        tools={},
        session_factory=build_session_factory(),
    )

    result = asyncio.run(
        bridge.run(
            project_id="project-1",
            task_id="task-1",
            system_prompt="system",
            recon_payload={"repo": "demo"},
            user_message="inspect",
        )
    )

    assert result["final_payload"] == {"findings": [], "summary": "???????"}
    assert result["turn_count"] >= 1
    assert llm.calls[-1]["messages"][-1]["role"] == "user"
    assert "Stop auditing now" in llm.calls[-1]["messages"][-1]["content"]
    assert llm.calls[-1]["tools"] == []


def test_bridge_fallback_summary_uses_last_assistant_message():
    session_factory = build_session_factory()
    bridge = FindingRuntimeBridge(llm_service=FakeLLMService([]), tools={}, session_factory=session_factory)
    store = bridge._session_store
    session_id = store.create_session(project_id="project-1", system_prompt="system")
    store.append_message(session_id, TranscriptItem(role=RuntimeMessageRole.USER, content="inspect"))
    store.append_message(session_id, TranscriptItem(role=RuntimeMessageRole.ASSISTANT, content="???? OpenApiController ? GLUE ?????"))
    snapshot = store.load_session_snapshot(session_id)

    summary = bridge._fallback_summary(snapshot)

    assert "machine-parseable final JSON payload" in summary
    assert "OpenApiController" in summary


def test_bridge_exposes_restored_style_runtime_tools():
    bridge = FindingRuntimeBridge(
        llm_service=FakeLLMService([]),
        tools={
            "read_file": FakeAgentTool("read_file"),
            "read_many_files": FakeAgentTool("read_many_files"),
            "list_files": FakeAgentTool("list_files"),
            "search_code": FakeAgentTool("search_code"),
            "think": FakeAgentTool("think"),
        },
        session_factory=build_session_factory(),
    )

    tool_names = [item["name"] for item in bridge._build_tool_registry().describe_tools()]

    assert tool_names == ["Read", "Glob", "Grep", "Skill"]
    assert "read_many_files" not in tool_names


def test_bridge_skips_system_transcript_messages_when_building_model_payload():
    llm = FakeLLMService([{"content": "{}", "finish_reason": "stop", "tool_calls": []}])
    client = FindingRuntimeBridge(llm_service=llm, tools={}, session_factory=build_session_factory())
    model_client = client._llm_service
    del model_client
    runtime_client = client.__class__.__dict__  # keep bridge imported

    llm_client = __import__("app.services.finding_runtime.bridge", fromlist=["RuntimeLLMModelClient"]).RuntimeLLMModelClient(
        llm_service=llm,
        agent_type="finding",
    )
    asyncio.run(
        llm_client.complete(
            system_prompt="base prompt",
            recon_payload={"repo": "demo"},
            transcript=[
                TranscriptItem(role=RuntimeMessageRole.SYSTEM, content="should be skipped"),
                TranscriptItem(role=RuntimeMessageRole.USER, content="inspect"),
            ],
            model_name="finding",
            tool_definitions=[],
        )
    )

    assert len(llm.calls[-1]["messages"]) == 2
    assert llm.calls[-1]["messages"][0]["role"] == "system"
    assert "Runtime recon payload" in llm.calls[-1]["messages"][0]["content"]
    assert llm.calls[-1]["messages"][1] == {"role": "user", "content": "inspect"}


def test_bridge_extracts_json_from_mixed_final_answer():
    payload = FindingRuntimeBridge._parse_payload(
        "Thought: enough evidence collected.\nFinal Answer: {\"findings\": [{\"title\": \"auth bypass\"}], \"summary\": \"done\"}"
    )

    assert payload == {"findings": [{"title": "auth bypass"}], "summary": "done"}

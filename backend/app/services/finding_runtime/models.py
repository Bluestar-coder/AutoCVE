from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RuntimeSessionState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RuntimeMessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    HANDOFF = "handoff"


class RuntimeStopReason(StrEnum):
    ASSISTANT_TURN_COMPLETE = "assistant_turn_complete"
    USER_FOLLOW_UP_REQUIRED = "user_follow_up_required"
    MODEL_STOP = "model_stop"
    TOOL_EXECUTION_CONTINUE = "tool_execution_continue"
    MAX_TURNS_EXCEEDED = "max_turns_exceeded"


@dataclass(slots=True)
class TranscriptItem:
    role: RuntimeMessageRole
    content: str
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolCallRequest:
    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolExecutionPayload:
    content: str
    output_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_error: bool = False


@dataclass(slots=True)
class ToolExecutionRecord:
    tool_call_id: str
    request: ToolCallRequest
    status: str
    is_concurrency_safe: bool
    result: ToolExecutionPayload
    error_message: str | None = None
    duration_ms: int | None = None


@dataclass(slots=True)
class RuntimeSkillCatalogSnapshot:
    available_skills: list[dict[str, Any]] = field(default_factory=list)
    matched_skills: list[dict[str, Any]] = field(default_factory=list)
    prompt: str = ""
    route_message: str = ""
    route_plan: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeMemoryRecord:
    memory_kind: str
    title: str
    source_type: str
    source_ref: str
    content: str
    relevance_score: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuntimeMemoryBundle:
    instructions: list[RuntimeMemoryRecord] = field(default_factory=list)
    recalls: list[RuntimeMemoryRecord] = field(default_factory=list)

    @property
    def all_memories(self) -> list[RuntimeMemoryRecord]:
        return [*self.instructions, *self.recalls]


@dataclass(slots=True)
class RuntimeSessionSnapshot:
    session: Any
    messages: list[Any] = field(default_factory=list)
    turns: list[Any] = field(default_factory=list)
    checkpoints: list[Any] = field(default_factory=list)
    tool_calls: list[Any] = field(default_factory=list)
    skills: list[Any] = field(default_factory=list)
    skill_invocations: list[Any] = field(default_factory=list)
    memories: list[Any] = field(default_factory=list)
    handoffs: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class TurnExecutionResult:
    turn_id: str
    stop_reason: RuntimeStopReason
    assistant_message_id: str | None = None
    tool_call_ids: list[str] = field(default_factory=list)
    tool_result_message_ids: list[str] = field(default_factory=list)

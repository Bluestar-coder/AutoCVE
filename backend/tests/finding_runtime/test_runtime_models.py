from app.services.finding_runtime.config import FindingRuntimeStack, coerce_finding_runtime_stack
from app.services.finding_runtime.models import (
    RuntimeMessageRole,
    RuntimeSessionState,
    RuntimeStopReason,
    ToolCallRequest,
    TranscriptItem,
)


def test_runtime_stack_defaults_to_legacy_for_unknown_values():
    assert coerce_finding_runtime_stack(None) is FindingRuntimeStack.LEGACY
    assert coerce_finding_runtime_stack("") is FindingRuntimeStack.LEGACY
    assert coerce_finding_runtime_stack("something-else") is FindingRuntimeStack.LEGACY


def test_runtime_stack_accepts_phase_one_runtime_flag_values():
    assert coerce_finding_runtime_stack("runtime") is FindingRuntimeStack.RUNTIME
    assert coerce_finding_runtime_stack("new") is FindingRuntimeStack.RUNTIME
    assert coerce_finding_runtime_stack("legacy") is FindingRuntimeStack.LEGACY


def test_runtime_enums_expose_runtime_states_and_stop_reasons():
    assert RuntimeSessionState.PENDING.value == "pending"
    assert RuntimeSessionState.RUNNING.value == "running"
    assert RuntimeSessionState.COMPLETED.value == "completed"

    assert RuntimeStopReason.ASSISTANT_TURN_COMPLETE.value == "assistant_turn_complete"
    assert RuntimeStopReason.USER_FOLLOW_UP_REQUIRED.value == "user_follow_up_required"
    assert RuntimeStopReason.TOOL_EXECUTION_CONTINUE.value == "tool_execution_continue"
    assert RuntimeStopReason.MAX_TURNS_EXCEEDED.value == "max_turns_exceeded"


def test_transcript_item_normalizes_optional_metadata_and_payloads():
    item = TranscriptItem(
        role=RuntimeMessageRole.ASSISTANT,
        content="hello world",
    )

    assert item.role is RuntimeMessageRole.ASSISTANT
    assert item.content == "hello world"
    assert item.name is None
    assert item.metadata == {}
    assert item.payload == {}


def test_tool_call_request_defaults_input_payload_to_empty_mapping():
    call = ToolCallRequest(id="tool-1", name="echo")

    assert call.id == "tool-1"
    assert call.name == "echo"
    assert call.input == {}

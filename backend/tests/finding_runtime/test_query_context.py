from __future__ import annotations

from app.services.finding_runtime.models import RuntimeMessageRole, TranscriptItem
from app.services.finding_runtime.query_context import (
    apply_context_collapse_if_needed,
    apply_history_snip,
    apply_microcompact,
    apply_tool_result_budget,
    evaluate_blocking_limit,
    get_messages_after_compact_boundary,
    project_context_collapse,
    run_reactive_compact,
    run_proactive_autocompact,
)
from app.services.finding_runtime.query_state import QueryLoopState


def test_get_messages_after_compact_boundary_returns_tail_after_last_boundary():
    messages = [
        TranscriptItem(role=RuntimeMessageRole.USER, content="old-1"),
        TranscriptItem(role=RuntimeMessageRole.USER, content="old-2"),
        TranscriptItem(
            role=RuntimeMessageRole.USER,
            content="boundary",
            name="auto_compact_boundary",
            metadata={"kind": "compact_boundary"},
        ),
        TranscriptItem(role=RuntimeMessageRole.USER, content="recent-1"),
        TranscriptItem(role=RuntimeMessageRole.ASSISTANT, content="recent-2"),
    ]

    result = get_messages_after_compact_boundary(messages, QueryLoopState())

    assert [item.content for item in result] == ["recent-1", "recent-2"]


def test_apply_tool_result_budget_truncates_old_tool_results_when_over_budget():
    state = QueryLoopState(
        tool_use_context={
            "tool_result_budget": {"max_total_chars": 35, "trim_to_chars": 10},
        }
    )
    messages = [
        TranscriptItem(role=RuntimeMessageRole.USER, content="inspect"),
        TranscriptItem(role=RuntimeMessageRole.TOOL_RESULT, content="A" * 20, name="read_file"),
        TranscriptItem(role=RuntimeMessageRole.TOOL_RESULT, content="B" * 20, name="grep"),
    ]

    result = apply_tool_result_budget(messages, state)

    assert result[1].content.endswith("...[truncated]")
    assert result[1].metadata["content_replaced"] is True
    assert result[2].content == "B" * 20


def test_apply_history_snip_keeps_recent_messages_and_inserts_marker():
    state = QueryLoopState(tool_use_context={"history_snip": {"keep_last_messages": 2}})
    messages = [
        TranscriptItem(role=RuntimeMessageRole.USER, content="m1"),
        TranscriptItem(role=RuntimeMessageRole.ASSISTANT, content="m2"),
        TranscriptItem(role=RuntimeMessageRole.USER, content="m3"),
        TranscriptItem(role=RuntimeMessageRole.ASSISTANT, content="m4"),
    ]

    result = apply_history_snip(messages, state)

    assert result[0].name == "history_snip_boundary"
    assert result[1].content == "m3"
    assert result[2].content == "m4"


def test_apply_microcompact_truncates_large_tool_result_payloads():
    state = QueryLoopState(tool_use_context={"microcompact": {"tool_result_max_chars": 8}})
    messages = [
        TranscriptItem(role=RuntimeMessageRole.USER, content="inspect"),
        TranscriptItem(role=RuntimeMessageRole.TOOL_RESULT, content="1234567890abcdef", name="grep"),
    ]

    result = apply_microcompact(messages, state)

    assert result[1].content == "12345678...[microcompact]"
    assert result[1].metadata["microcompacted"] is True


def test_project_context_collapse_replaces_prefix_with_summary_message():
    state = QueryLoopState(auto_compact_tracking={
        "projected_summary": "Earlier turns covered controller routing and auth entrypoints.",
        "projected_drop_count": 2,
    })
    messages = [
        TranscriptItem(role=RuntimeMessageRole.USER, content="m1"),
        TranscriptItem(role=RuntimeMessageRole.ASSISTANT, content="m2"),
        TranscriptItem(role=RuntimeMessageRole.USER, content="m3"),
    ]

    result = project_context_collapse(messages, state)

    assert result[0].name == "context_collapse_summary"
    assert result[0].content == "Earlier turns covered controller routing and auth entrypoints."
    assert [item.content for item in result[1:]] == ["m3"]


def test_apply_context_collapse_if_needed_stages_and_projects_summary_view():
    state = QueryLoopState(
        tool_use_context={
            "context_collapse": {"max_chars": 30, "preserve_tail_messages": 1},
        }
    )
    messages = [
        TranscriptItem(role=RuntimeMessageRole.USER, content="A" * 20),
        TranscriptItem(role=RuntimeMessageRole.ASSISTANT, content="B" * 20),
        TranscriptItem(role=RuntimeMessageRole.USER, content="tail"),
    ]

    projected_messages, next_state = apply_context_collapse_if_needed(messages, state)

    assert projected_messages[0].name == "context_collapse_summary"
    assert projected_messages[-1].content == "tail"
    assert next_state.auto_compact_tracking["pending_collapse"] is True
    assert len(next_state.context_collapse_state["snapshot"]["staged"]) == 1
    assert next_state.context_collapse_state["commits"] == []


def test_apply_context_collapse_if_needed_replays_persisted_commit_view():
    messages = [
        TranscriptItem(role=RuntimeMessageRole.USER, content="m1", metadata={"collapse_uuid": "u1"}),
        TranscriptItem(role=RuntimeMessageRole.ASSISTANT, content="m2", metadata={"collapse_uuid": "u2"}),
        TranscriptItem(role=RuntimeMessageRole.USER, content="tail", metadata={"collapse_uuid": "u3"}),
    ]
    state = QueryLoopState(
        tool_use_context={"context_collapse": {"max_chars": 999, "preserve_tail_messages": 1}},
        context_collapse_state={
            "commits": [
                {
                    "collapse_id": "0000000000000001",
                    "summary_uuid": "summary-1",
                    "summary_content": "Collapsed earlier context.",
                    "summary": "Collapsed earlier context.",
                    "first_archived_uuid": "u1",
                    "last_archived_uuid": "u2",
                }
            ],
            "snapshot": {"staged": [], "armed": False, "last_spawn_tokens": 0},
        },
    )

    projected_messages, next_state = apply_context_collapse_if_needed(messages, state)

    assert projected_messages[0].name == "context_collapse_summary"
    assert projected_messages[0].metadata["collapse_id"] == "0000000000000001"
    assert projected_messages[-1].content == "tail"
    assert next_state.context_collapse_state["commits"][0]["summary_uuid"] == "summary-1"


def test_run_proactive_autocompact_compacts_large_transcript_and_updates_tracking():
    state = QueryLoopState(tool_use_context={"autocompact": {"max_chars": 30, "preserve_tail_messages": 1}})
    messages = [
        TranscriptItem(role=RuntimeMessageRole.USER, content="A" * 20),
        TranscriptItem(role=RuntimeMessageRole.ASSISTANT, content="B" * 20),
        TranscriptItem(role=RuntimeMessageRole.USER, content="tail"),
    ]

    compacted_messages, next_state = run_proactive_autocompact(messages, state)

    assert compacted_messages[0].name == "auto_compact_summary"
    assert compacted_messages[-1].content == "tail"
    assert next_state.auto_compact_tracking["compacted"] is True
    assert next_state.auto_compact_tracking["summary_message_name"] == "auto_compact_summary"


def test_run_reactive_compact_builds_restored_style_post_compact_messages():
    state = QueryLoopState(tool_use_context={"reactive_compact": {"preserve_tail_messages": 1}})
    messages = [
        TranscriptItem(role=RuntimeMessageRole.USER, content="controller mapping"),
        TranscriptItem(role=RuntimeMessageRole.ASSISTANT, content="auth sink reasoning"),
        TranscriptItem(role=RuntimeMessageRole.USER, content="tail"),
    ]

    compacted_messages, next_state = run_reactive_compact(
        messages,
        state,
        recoverable_error_kind="prompt_too_long",
    )

    assert compacted_messages[0].name == "reactive_compact_boundary"
    assert compacted_messages[1].name == "reactive_compact_summary"
    assert compacted_messages[-1].content == "tail"
    assert next_state.auto_compact_tracking["summary_message_name"] == "reactive_compact_summary"


def test_run_reactive_compact_strips_media_blocks_for_media_recovery():
    state = QueryLoopState(tool_use_context={"reactive_compact": {"preserve_tail_messages": 1}})
    messages = [
        TranscriptItem(
            role=RuntimeMessageRole.USER,
            content="see screenshot evidence",
            payload={
                "content_blocks": [
                    {"type": "image", "source": "img-1"},
                    {"type": "text", "text": "see screenshot evidence"},
                ]
            },
        ),
        TranscriptItem(role=RuntimeMessageRole.ASSISTANT, content="tail"),
    ]

    compacted_messages, next_state = run_reactive_compact(
        messages,
        state,
        recoverable_error_kind="media_size",
    )

    assert compacted_messages[0].name == "reactive_compact_boundary"
    assert "[image]" in compacted_messages[1].content
    assert next_state.auto_compact_tracking["media_stripped_count"] == 1


def test_run_proactive_autocompact_uses_restored_style_threshold_controller_when_present():
    state = QueryLoopState(
        tool_use_context={
            "autocompact": {"preserve_tail_messages": 1},
            "autocompact_controller": {"context_window": 20000, "max_output_tokens": 40},
        }
    )
    messages = [
        TranscriptItem(role=RuntimeMessageRole.USER, content="A" * 7000),
        TranscriptItem(role=RuntimeMessageRole.ASSISTANT, content="B" * 30),
        TranscriptItem(role=RuntimeMessageRole.USER, content="tail"),
    ]

    compacted_messages, next_state = run_proactive_autocompact(messages, state)

    assert compacted_messages[0].name == "auto_compact_summary"
    assert compacted_messages[-1].content == "tail"
    assert next_state.auto_compact_tracking["auto_compact_threshold"] == 6960
    assert next_state.auto_compact_tracking["effective_context_window"] == 19960



def test_evaluate_blocking_limit_uses_restored_style_controller_when_present():
    state = QueryLoopState(
        tool_use_context={
            "autocompact_controller": {"context_window": 20000, "max_output_tokens": 40}
        }
    )
    messages = [TranscriptItem(role=RuntimeMessageRole.USER, content="A" * 17000)]

    result = evaluate_blocking_limit(messages, state)

    assert result["blocked"] is True
    assert result["blocking_limit"] == 16960
    assert result["token_usage"] == 17000




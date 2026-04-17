from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from app.services.finding_runtime.compaction.auto_compact import (
    calculate_token_warning_state,
    get_auto_compact_threshold,
    get_effective_context_window_size,
)
from app.services.finding_runtime.models import RuntimeMessageRole, TranscriptItem
from app.services.finding_runtime.query_state import QueryLoopState
DEFAULT_COMPACT_BOUNDARY_NAMES = {
    "auto_compact_boundary",
    "microcompact_boundary",
    "context_collapse_summary",
    "auto_compact_summary",
    "reactive_compact_boundary",
}
DEFAULT_COMPACT_BOUNDARY_KINDS = {
    "compact_boundary",
    "microcompact_boundary",
    "context_collapse_summary",
    "auto_compact_summary",
    "reactive_compact_summary",
}


def get_messages_after_compact_boundary(messages: list[TranscriptItem], state: QueryLoopState) -> list[TranscriptItem]:
    config = _pipeline_config(state)
    boundary_names = set(config.get("boundary_names") or DEFAULT_COMPACT_BOUNDARY_NAMES)
    boundary_kinds = set(config.get("boundary_kinds") or DEFAULT_COMPACT_BOUNDARY_KINDS)
    last_boundary_index = -1
    for index, item in enumerate(messages):
        if (item.name or "") in boundary_names or str(item.metadata.get("kind") or "") in boundary_kinds:
            last_boundary_index = index
    if last_boundary_index < 0:
        return list(messages)
    return list(messages[last_boundary_index + 1 :])


def apply_tool_result_budget(messages: list[TranscriptItem], state: QueryLoopState) -> list[TranscriptItem]:
    config = _pipeline_config(state).get("tool_result_budget") or {}
    max_total_chars = int(config.get("max_total_chars") or 0)
    trim_to_chars = max(0, int(config.get("trim_to_chars") or 0))
    if max_total_chars <= 0:
        return list(messages)

    result = [deepcopy(item) for item in messages]
    tool_result_indexes = [index for index, item in enumerate(result) if item.role is RuntimeMessageRole.TOOL_RESULT]
    total_chars = sum(len(result[index].content or "") for index in tool_result_indexes)
    for index in tool_result_indexes:
        if total_chars <= max_total_chars:
            break
        item = result[index]
        original_content = item.content or ""
        if len(original_content) <= trim_to_chars:
            continue
        suffix = "...[truncated]"
        prefix_budget = max(0, trim_to_chars - len(suffix))
        trimmed_content = f"{original_content[:prefix_budget]}{suffix}" if prefix_budget else suffix
        total_chars -= len(original_content) - len(trimmed_content)
        item.content = trimmed_content
        item.metadata["content_replaced"] = True
        item.metadata["original_content_chars"] = len(original_content)
    return result


def apply_history_snip(messages: list[TranscriptItem], state: QueryLoopState) -> list[TranscriptItem]:
    config = _pipeline_config(state).get("history_snip") or {}
    keep_last_messages = int(config.get("keep_last_messages") or 0)
    if keep_last_messages <= 0 or len(messages) <= keep_last_messages:
        return list(messages)
    tail = [deepcopy(item) for item in messages[-keep_last_messages:]]
    snipped_count = len(messages) - keep_last_messages
    boundary = TranscriptItem(
        role=RuntimeMessageRole.USER,
        content=f"History snip removed {snipped_count} earlier messages.",
        name="history_snip_boundary",
        metadata={"synthetic": True, "kind": "history_snip_boundary", "snipped_count": snipped_count},
    )
    return [boundary, *tail]


def apply_microcompact(messages: list[TranscriptItem], state: QueryLoopState) -> list[TranscriptItem]:
    config = _pipeline_config(state).get("microcompact") or {}
    tool_result_max_chars = int(config.get("tool_result_max_chars") or 0)
    if tool_result_max_chars <= 0:
        return list(messages)
    result = [deepcopy(item) for item in messages]
    for item in result:
        if item.role is not RuntimeMessageRole.TOOL_RESULT:
            continue
        if len(item.content or "") <= tool_result_max_chars:
            continue
        item.content = f"{(item.content or '')[:tool_result_max_chars]}...[microcompact]"
        item.metadata["microcompacted"] = True
    return result


def project_context_collapse(messages: list[TranscriptItem], state: QueryLoopState) -> list[TranscriptItem]:
    tracking = dict(state.auto_compact_tracking or {})
    summary = str(tracking.get("projected_summary") or "").strip()
    drop_count = int(tracking.get("projected_drop_count") or 0)
    if not summary or drop_count <= 0 or drop_count >= len(messages) + 1:
        return list(messages)
    collapsed_summary = TranscriptItem(
        role=RuntimeMessageRole.USER,
        content=summary,
        name="context_collapse_summary",
        metadata={"synthetic": True, "kind": "context_collapse_summary", "dropped_messages": drop_count},
    )
    return [collapsed_summary, *[deepcopy(item) for item in messages[drop_count:]]]


def apply_context_collapse_if_needed(messages: list[TranscriptItem], state: QueryLoopState) -> tuple[list[TranscriptItem], QueryLoopState]:
    prepared_messages = _ensure_collapse_uuids(messages)
    collapse_state = _normalize_context_collapse_state(state.context_collapse_state)
    config = dict(_pipeline_config(state).get("context_collapse") or {})

    if _should_stage_context_collapse(prepared_messages, config, collapse_state):
        staged_entry = _create_staged_collapse(prepared_messages, config)
        if staged_entry is not None:
            collapse_state["snapshot"]["staged"] = [staged_entry]
            collapse_state["snapshot"]["armed"] = True
            collapse_state["snapshot"]["last_spawn_tokens"] = sum(len(item.content or "") for item in prepared_messages)

    projected_messages = _project_context_collapse_entries(prepared_messages, collapse_state)
    next_tracking = _collapse_tracking_payload(collapse_state, projected_messages)
    next_state = _copy_state(
        state,
        context_collapse_state=collapse_state,
        auto_compact_tracking={**dict(state.auto_compact_tracking or {}), **next_tracking},
    )
    return projected_messages, next_state


def recover_context_collapse_from_overflow(messages: list[TranscriptItem], state: QueryLoopState) -> tuple[list[TranscriptItem], QueryLoopState, int]:
    prepared_messages = _ensure_collapse_uuids(messages)
    collapse_state = _normalize_context_collapse_state(state.context_collapse_state)
    staged_entries = list(collapse_state["snapshot"].get("staged") or [])

    if not staged_entries:
        fallback_tracking = dict(state.auto_compact_tracking or {})
        staged_summary = str(fallback_tracking.get("staged_summary") or "").strip()
        staged_drop_count = int(fallback_tracking.get("staged_drop_count") or 0)
        if staged_summary and staged_drop_count > 0:
            staged_entries = [_create_fallback_staged_entry(prepared_messages, staged_summary, staged_drop_count)]
        elif bool(fallback_tracking.get("pending_collapse")) and len(prepared_messages) >= 1:
            staged_entries = [_create_fallback_staged_entry(prepared_messages, _build_collapse_summary(prepared_messages[:-1] or prepared_messages), max(1, len(prepared_messages) - 1))]

    if not staged_entries:
        return list(prepared_messages), state, 0

    committed_count = 0
    next_commits = list(collapse_state["commits"])
    for entry in staged_entries:
        commit = _commit_staged_entry(entry, next_commits)
        if commit is None:
            continue
        next_commits.append(commit)
        committed_count += 1

    collapse_state["commits"] = next_commits
    collapse_state["snapshot"] = {
        "staged": [],
        "armed": False,
        "last_spawn_tokens": int(collapse_state.get("snapshot", {}).get("last_spawn_tokens") or 0),
    }
    projected_messages = _project_context_collapse_entries(prepared_messages, collapse_state)
    next_tracking = {
        **dict(state.auto_compact_tracking or {}),
        "pending_collapse": False,
        "last_recovery_strategy": "collapse_drain",
        "last_recovery_status": "deferred",
    }
    next_tracking.pop("projected_summary", None)
    next_tracking.pop("projected_drop_count", None)
    next_state = _copy_state(
        state,
        messages=projected_messages,
        context_collapse_state=collapse_state,
        auto_compact_tracking=next_tracking,
    )
    return projected_messages, next_state, committed_count


def run_proactive_autocompact(messages: list[TranscriptItem], state: QueryLoopState) -> tuple[list[TranscriptItem], QueryLoopState]:
    config = _pipeline_config(state).get("autocompact") or {}
    preserve_tail_messages = max(0, int(config.get("preserve_tail_messages") or 0))
    total_chars = sum(len(item.content or "") for item in messages)
    controller = dict(_pipeline_config(state).get("autocompact_controller") or state.tool_use_context.get("autocompact_controller") or {})
    threshold = 0
    effective_context_window = 0
    if controller:
        context_window = int(controller.get("context_window") or 0)
        max_output_tokens = int(controller.get("max_output_tokens") or 0)
        if context_window > 0 and max_output_tokens > 0:
            threshold = get_auto_compact_threshold(
                model=str(controller.get("model") or "claude-sonnet-4-5"),
                context_window=context_window,
                max_output_tokens=max_output_tokens,
            )
            effective_context_window = get_effective_context_window_size(
                model=str(controller.get("model") or "claude-sonnet-4-5"),
                context_window=context_window,
                max_output_tokens=max_output_tokens,
            )
    max_chars = int(config.get("max_chars") or 0)
    should_compact = False
    if threshold > 0:
        should_compact = total_chars >= threshold and len(messages) > preserve_tail_messages
    elif max_chars > 0:
        should_compact = total_chars > max_chars and len(messages) > preserve_tail_messages
    if not should_compact:
        return list(messages), state

    tail = [deepcopy(item) for item in messages[-preserve_tail_messages:]] if preserve_tail_messages else []
    compacted_prefix = list(messages[:-preserve_tail_messages]) if preserve_tail_messages else list(messages)
    summary = _build_autocompact_summary(compacted_prefix)
    tracking = {
        **dict(state.auto_compact_tracking or {}),
        "compacted": True,
        "summary_message_name": "auto_compact_summary",
        "compacted_messages": len(compacted_prefix),
    }
    if threshold > 0:
        tracking["auto_compact_threshold"] = threshold
        tracking["effective_context_window"] = effective_context_window
    summary_message = TranscriptItem(
        role=RuntimeMessageRole.USER,
        content=summary,
        name="auto_compact_summary",
        metadata={"synthetic": True, "kind": "auto_compact_summary", "compacted_messages": len(compacted_prefix)},
    )
    next_state = _copy_state(
        state,
        messages=[summary_message, *tail],
        auto_compact_tracking=tracking,
    )
    return list(next_state.messages), next_state


def run_reactive_compact(
    messages: list[TranscriptItem],
    state: QueryLoopState,
    *,
    recoverable_error_kind: str,
) -> tuple[list[TranscriptItem], QueryLoopState]:
    pipeline = _pipeline_config(state)
    reactive_config = dict(pipeline.get("reactive_compact") or {})
    autocompact_config = dict(pipeline.get("autocompact") or {})
    default_tail = int(autocompact_config.get("preserve_tail_messages") or 2)
    preserve_tail_messages = max(0, int(reactive_config.get("preserve_tail_messages") or default_tail))
    max_summary_messages = max(1, int(reactive_config.get("max_summary_messages") or 6))

    prepared_messages, media_stats = _strip_media_from_messages(
        messages,
        enabled=recoverable_error_kind in {"media_size", "image_error"},
    )
    tail_count = _resolve_reactive_tail_count(len(prepared_messages), preserve_tail_messages)
    if tail_count > 0:
        compacted_prefix = prepared_messages[:-tail_count]
        preserved_tail = [deepcopy(item) for item in prepared_messages[-tail_count:]]
    else:
        compacted_prefix = prepared_messages
        preserved_tail = []

    boundary_message = TranscriptItem(
        role=RuntimeMessageRole.SYSTEM,
        content="Reactive compact boundary.",
        name="reactive_compact_boundary",
        metadata={
            "synthetic": True,
            "kind": "compact_boundary",
            "strategy": "reactive_compact",
            "recoverable_error_kind": recoverable_error_kind,
            "preserved_tail_messages": len(preserved_tail),
        },
    )
    summary_message = TranscriptItem(
        role=RuntimeMessageRole.USER,
        content=_build_reactive_compact_summary(
            compacted_prefix,
            media_stripped_count=media_stats["media_stripped_count"],
            max_summary_messages=max_summary_messages,
        ),
        name="reactive_compact_summary",
        metadata={
            "synthetic": True,
            "kind": "reactive_compact_summary",
            "strategy": "reactive_compact",
            "compacted_messages": len(compacted_prefix),
            "media_stripped_count": media_stats["media_stripped_count"],
        },
    )

    next_messages = [boundary_message, summary_message, *preserved_tail]
    next_tracking = {
        **dict(state.auto_compact_tracking or {}),
        "compacted": True,
        "summary_message_name": "reactive_compact_summary",
        "boundary_name": "reactive_compact_boundary",
        "compacted_messages": len(compacted_prefix),
        "preserved_tail_messages": len(preserved_tail),
        "media_stripped_count": media_stats["media_stripped_count"],
    }
    next_state = _copy_state(
        state,
        messages=next_messages,
        auto_compact_tracking=next_tracking,
    )
    return list(next_state.messages), next_state


def append_system_context(system_prompt: str | None, runtime_state: Any) -> str:
    query_context = dict(getattr(runtime_state, "metadata", {}).get("query_context") or {})
    sections = [str(system_prompt or "").strip()]
    for section in query_context.get("system_sections") or []:
        normalized = str(section or "").strip()
        if normalized:
            sections.append(normalized)
    return "\n\n".join(section for section in sections if section)


def prepend_user_context(messages: list[TranscriptItem], runtime_state: Any) -> list[TranscriptItem]:
    query_context = dict(getattr(runtime_state, "metadata", {}).get("query_context") or {})
    prefix = str(query_context.get("user_context_prefix") or "").strip()
    if not prefix:
        return list(messages)
    synthetic_user_context = TranscriptItem(
        role=RuntimeMessageRole.USER,
        content=prefix,
        name="runtime_user_context",
        metadata={"synthetic": True, "kind": "user_context"},
    )
    return [synthetic_user_context, *list(messages)]


def _pipeline_config(state: QueryLoopState) -> dict[str, Any]:
    tool_context = dict(state.tool_use_context or {})
    pipeline = dict(tool_context.get("query_context_pipeline") or {})
    merged = {key: value for key, value in tool_context.items() if key != "query_context_pipeline"}
    merged.update(pipeline)
    return merged


def _copy_state(
    state: QueryLoopState,
    *,
    messages: list[TranscriptItem] | None = None,
    auto_compact_tracking: dict[str, Any] | None = None,
    context_collapse_state: dict[str, Any] | None = None,
) -> QueryLoopState:
    return QueryLoopState(
        messages=list(messages if messages is not None else state.messages),
        tool_use_context=deepcopy(state.tool_use_context),
        auto_compact_tracking=deepcopy(auto_compact_tracking if auto_compact_tracking is not None else state.auto_compact_tracking),
        context_collapse_state=deepcopy(context_collapse_state if context_collapse_state is not None else state.context_collapse_state),
        max_output_tokens_recovery_count=state.max_output_tokens_recovery_count,
        has_attempted_reactive_compact=state.has_attempted_reactive_compact,
        max_output_tokens_override=state.max_output_tokens_override,
        pending_tool_use_summary=deepcopy(state.pending_tool_use_summary),
        stop_hook_active=state.stop_hook_active,
        turn_count=state.turn_count,
        transition=state.transition,
    )


def _ensure_collapse_uuids(messages: list[TranscriptItem]) -> list[TranscriptItem]:
    result: list[TranscriptItem] = []
    for item in messages:
        clone = deepcopy(item)
        clone.metadata.setdefault("collapse_uuid", str(uuid4()))
        result.append(clone)
    return result


def _normalize_context_collapse_state(raw: dict[str, Any] | None) -> dict[str, Any]:
    state = dict(raw or {})
    commits = [dict(entry) for entry in state.get("commits") or [] if isinstance(entry, dict)]
    snapshot = dict(state.get("snapshot") or {})
    staged = [dict(entry) for entry in snapshot.get("staged") or [] if isinstance(entry, dict)]
    return {
        "commits": commits,
        "snapshot": {
            "staged": staged,
            "armed": bool(snapshot.get("armed") or False),
            "last_spawn_tokens": int(snapshot.get("last_spawn_tokens") or 0),
        },
    }


def _should_stage_context_collapse(
    messages: list[TranscriptItem],
    config: dict[str, Any],
    collapse_state: dict[str, Any],
) -> bool:
    if not config:
        return False
    if collapse_state["snapshot"].get("staged"):
        return False
    max_chars = int(config.get("max_chars") or 0)
    preserve_tail_messages = max(0, int(config.get("preserve_tail_messages") or 0))
    if max_chars <= 0 or len(messages) <= max(1, preserve_tail_messages):
        return False
    total_chars = sum(len(item.content or "") for item in messages)
    return total_chars > max_chars


def _create_staged_collapse(messages: list[TranscriptItem], config: dict[str, Any]) -> dict[str, Any] | None:
    preserve_tail_messages = max(0, int(config.get("preserve_tail_messages") or 1))
    tail_count = min(preserve_tail_messages, len(messages) - 1)
    if tail_count <= 0:
        end_index = len(messages) - 1
    else:
        end_index = len(messages) - tail_count - 1
    if end_index < 0:
        return None
    span = messages[: end_index + 1]
    if not span:
        return None
    return {
        "start_uuid": span[0].metadata["collapse_uuid"],
        "end_uuid": span[-1].metadata["collapse_uuid"],
        "summary": _build_collapse_summary(span),
        "risk": int(config.get("risk") or 5),
        "staged_at": int(config.get("staged_at") or 1),
    }


def _create_fallback_staged_entry(messages: list[TranscriptItem], summary: str, drop_count: int) -> dict[str, Any]:
    clamped_drop_count = max(1, min(drop_count, len(messages)))
    span = messages[:clamped_drop_count]
    return {
        "start_uuid": span[0].metadata["collapse_uuid"],
        "end_uuid": span[-1].metadata["collapse_uuid"],
        "summary": summary,
        "risk": 5,
        "staged_at": 1,
    }


def _commit_staged_entry(entry: dict[str, Any], existing_commits: list[dict[str, Any]]) -> dict[str, Any] | None:
    start_uuid = str(entry.get("start_uuid") or "").strip()
    end_uuid = str(entry.get("end_uuid") or "").strip()
    summary = str(entry.get("summary") or "").strip()
    if not start_uuid or not end_uuid or not summary:
        return None
    collapse_id = f"{len(existing_commits) + 1:016d}"
    summary_uuid = f"context-collapse-summary-{collapse_id}"
    return {
        "collapse_id": collapse_id,
        "summary_uuid": summary_uuid,
        "summary_content": f'<collapsed id="{collapse_id}">{summary}</collapsed>',
        "summary": summary,
        "first_archived_uuid": start_uuid,
        "last_archived_uuid": end_uuid,
    }


def _project_context_collapse_entries(messages: list[TranscriptItem], collapse_state: dict[str, Any]) -> list[TranscriptItem]:
    projected_entries = [
        {
            "collapse_id": str(entry.get("collapse_id") or entry.get("summary_uuid") or f"staged-{index}"),
            "summary_uuid": str(entry.get("summary_uuid") or f"staged-summary-{index}"),
            "summary": str(entry.get("summary") or "").strip(),
            "first_archived_uuid": str(entry.get("first_archived_uuid") or entry.get("start_uuid") or "").strip(),
            "last_archived_uuid": str(entry.get("last_archived_uuid") or entry.get("end_uuid") or "").strip(),
        }
        for index, entry in enumerate([*collapse_state.get("commits", []), *collapse_state.get("snapshot", {}).get("staged", [])], start=1)
        if str(entry.get("summary") or "").strip()
    ]
    if not projected_entries:
        return list(messages)

    index_by_uuid = {
        str(item.metadata.get("collapse_uuid") or ""): index
        for index, item in enumerate(messages)
    }
    ranges: list[tuple[int, int, dict[str, Any]]] = []
    for entry in projected_entries:
        start_index = index_by_uuid.get(entry["first_archived_uuid"])
        end_index = index_by_uuid.get(entry["last_archived_uuid"])
        if start_index is None or end_index is None or start_index > end_index:
            continue
        ranges.append((start_index, end_index, entry))
    if not ranges:
        return list(messages)
    ranges.sort(key=lambda item: item[0])

    result: list[TranscriptItem] = []
    cursor = 0
    for start_index, end_index, entry in ranges:
        if start_index < cursor:
            continue
        result.extend(deepcopy(item) for item in messages[cursor:start_index])
        result.append(
            TranscriptItem(
                role=RuntimeMessageRole.USER,
                content=entry["summary"],
                name="context_collapse_summary",
                metadata={
                    "synthetic": True,
                    "kind": "context_collapse_summary",
                    "collapse_id": entry["collapse_id"],
                    "summary_uuid": entry["summary_uuid"],
                    "dropped_messages": end_index - start_index + 1,
                },
            )
        )
        cursor = end_index + 1
    result.extend(deepcopy(item) for item in messages[cursor:])
    return result


def _collapse_tracking_payload(collapse_state: dict[str, Any], projected_messages: list[TranscriptItem]) -> dict[str, Any]:
    snapshot = dict(collapse_state.get("snapshot") or {})
    staged = list(snapshot.get("staged") or [])
    tracking: dict[str, Any] = {
        "pending_collapse": bool(staged),
    }
    if staged:
        first_summary = str(staged[0].get("summary") or "").strip()
        if first_summary:
            tracking["projected_summary"] = first_summary
        if projected_messages and projected_messages[0].name == "context_collapse_summary":
            tracking["projected_drop_count"] = int(projected_messages[0].metadata.get("dropped_messages") or 0)
    return tracking


def _build_autocompact_summary(messages: list[TranscriptItem]) -> str:
    parts: list[str] = []
    for item in messages[:6]:
        role = item.role.value
        excerpt = (item.content or "").strip().replace("\n", " ")[:80]
        parts.append(f"[{role}] {excerpt}")
    joined = " | ".join(part for part in parts if part)
    return f"Auto-compact summary of earlier context: {joined}" if joined else "Auto-compact summary of earlier context."


def _build_collapse_summary(messages: list[TranscriptItem]) -> str:
    parts: list[str] = []
    for item in messages[:4]:
        role = item.role.value
        excerpt = (item.content or "").strip().replace("\n", " ")[:70]
        if excerpt:
            parts.append(f"[{role}] {excerpt}")
    joined = " | ".join(parts)
    return f"Collapsed earlier context: {joined}" if joined else "Collapsed earlier context."


def _build_reactive_compact_summary(
    messages: list[TranscriptItem],
    *,
    media_stripped_count: int,
    max_summary_messages: int,
) -> str:
    parts: list[str] = []
    for item in messages[:max_summary_messages]:
        role = item.role.value
        excerpt = (item.content or "").strip().replace("\n", " ")[:80]
        if excerpt:
            parts.append(f"[{role}] {excerpt}")
    prefix = f"Reactive compact summary of {len(messages)} earlier messages."
    if media_stripped_count > 0:
        prefix += f" Media stripped: {media_stripped_count}."
    joined = " | ".join(parts)
    return f"{prefix} {joined}".strip() if joined else prefix


def _resolve_reactive_tail_count(message_count: int, preserve_tail_messages: int) -> int:
    if message_count <= 1:
        return 0
    return min(max(0, preserve_tail_messages), message_count - 1)


def _strip_media_from_messages(
    messages: list[TranscriptItem],
    *,
    enabled: bool,
) -> tuple[list[TranscriptItem], dict[str, int]]:
    if not enabled:
        return [deepcopy(item) for item in messages], {"media_stripped_count": 0}

    total_stripped = 0
    result: list[TranscriptItem] = []
    for item in messages:
        clone = deepcopy(item)
        markers: list[str] = []
        payload = dict(clone.payload or {})
        content_blocks = payload.get("content_blocks")
        if isinstance(content_blocks, list):
            new_blocks = []
            for block in content_blocks:
                if not isinstance(block, dict):
                    new_blocks.append(block)
                    continue
                block_type = str(block.get("type") or "").lower()
                if block_type == "image":
                    total_stripped += 1
                    markers.append("[image]")
                    new_blocks.append({"type": "text", "text": "[image]"})
                    continue
                if block_type == "document":
                    total_stripped += 1
                    markers.append("[document]")
                    new_blocks.append({"type": "text", "text": "[document]"})
                    continue
                if block_type == "tool_result" and isinstance(block.get("content"), list):
                    nested_content = []
                    nested_changed = False
                    for nested in block.get("content") or []:
                        if not isinstance(nested, dict):
                            nested_content.append(nested)
                            continue
                        nested_type = str(nested.get("type") or "").lower()
                        if nested_type == "image":
                            total_stripped += 1
                            markers.append("[image]")
                            nested_content.append({"type": "text", "text": "[image]"})
                            nested_changed = True
                            continue
                        if nested_type == "document":
                            total_stripped += 1
                            markers.append("[document]")
                            nested_content.append({"type": "text", "text": "[document]"})
                            nested_changed = True
                            continue
                        nested_content.append(nested)
                    if nested_changed:
                        new_blocks.append({**block, "content": nested_content})
                        continue
                new_blocks.append(block)
            payload["content_blocks"] = new_blocks
        media_entries = payload.get("media")
        if isinstance(media_entries, list) and media_entries:
            for entry in media_entries:
                marker = "[document]" if isinstance(entry, dict) and str(entry.get("type") or "").lower() == "document" else "[image]"
                markers.append(marker)
                total_stripped += 1
            payload["media"] = []
        if markers:
            clone.payload = payload
            clone.metadata["media_stripped"] = True
            marker_prefix = " ".join(dict.fromkeys(markers))
            content = str(clone.content or "").strip()
            clone.content = f"{marker_prefix} {content}".strip() if content else marker_prefix
        result.append(clone)
    return result, {"media_stripped_count": total_stripped}


def evaluate_blocking_limit(messages: list[TranscriptItem], state: QueryLoopState) -> dict[str, int | bool]:
    current_chars = sum(len(item.content or "") for item in messages)
    controller = dict(_pipeline_config(state).get("autocompact_controller") or state.tool_use_context.get("autocompact_controller") or {})
    if controller:
        context_window = int(controller.get("context_window") or 0)
        max_output_tokens = int(controller.get("max_output_tokens") or 0)
        if context_window > 0 and max_output_tokens > 0:
            warning_state = calculate_token_warning_state(
                token_usage=current_chars,
                model=str(controller.get("model") or "claude-sonnet-4-5"),
                context_window=context_window,
                max_output_tokens=max_output_tokens,
            )
            blocking_limit = get_effective_context_window_size(
                model=str(controller.get("model") or "claude-sonnet-4-5"),
                context_window=context_window,
                max_output_tokens=max_output_tokens,
            ) - 3000
            return {
                "blocked": bool(warning_state["is_at_blocking_limit"]),
                "blocking_limit": blocking_limit,
                "token_usage": current_chars,
                "percent_left": int(warning_state["percent_left"]),
            }
    config = _pipeline_config(state).get("blocking_limit") or {}
    max_chars = int(config.get("max_chars") or 0)
    return {
        "blocked": bool(max_chars > 0 and current_chars > max_chars),
        "max_chars": max_chars,
        "current_chars": current_chars,
    }






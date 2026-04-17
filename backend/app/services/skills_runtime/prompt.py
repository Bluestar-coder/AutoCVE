from __future__ import annotations

from .models import SkillEntry, SkillPromptState, SkillRoutePlan


def _append_text_tag(lines: list[str], tag: str, value: str | None) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text:
        lines.append(f"<{tag}>{text}</{tag}>")


def _append_list_tag(lines: list[str], tag: str, values: list[str]) -> None:
    normalized = [str(value).strip() for value in values if str(value).strip()]
    if normalized:
        lines.append(f"<{tag}>{', '.join(normalized)}</{tag}>")


def build_skill_prompt_state(
    entries: list[SkillEntry],
    matched: list[SkillEntry] | None = None,
    route_plan: SkillRoutePlan | None = None,
) -> SkillPromptState:
    available_entries = list(entries)
    ordered_entries = sorted(available_entries, key=lambda entry: entry.name.lower())
    matched = matched or []
    resolved_route_plan = route_plan or SkillRoutePlan()
    if not available_entries:
        return SkillPromptState(entries=[], matched=matched, prompt="", route_plan=resolved_route_plan)

    lines = ["<available_skills>"]
    for entry in ordered_entries:
        lines.append("<skill>")
        lines.append(f"<name>{entry.name}</name>")
        lines.append(f"<description>{entry.description}</description>")
        _append_text_tag(lines, "when_to_use", entry.when_to_use)
        _append_list_tag(lines, "allowed_tools", entry.allowed_tools)
        _append_text_tag(lines, "argument_hint", entry.argument_hint)
        _append_list_tag(lines, "argument_names", entry.argument_names)
        _append_text_tag(lines, "model", entry.model)
        _append_text_tag(lines, "execution_context", entry.execution_context)
        _append_text_tag(lines, "agent", entry.agent)
        _append_text_tag(lines, "effort", entry.effort)
        _append_list_tag(lines, "paths", entry.paths)
        lines.append(f"<skill_root>{entry.folder_path}</skill_root>")
        lines.append(f"<skill_file_path>{entry.skill_file}</skill_file_path>")
        lines.append(f"<references_root>{entry.folder_path}/references</references_root>")
        lines.append(f"<examples_root>{entry.folder_path}/examples</examples_root>")
        lines.append(f"<scripts_root>{entry.folder_path}/scripts</scripts_root>")
        lines.append("</skill>")
    lines.append("</available_skills>")

    if (
        resolved_route_plan.primary_skill
        or resolved_route_plan.secondary_skills
        or resolved_route_plan.startup_reads
        or resolved_route_plan.deferred_skills
        or resolved_route_plan.deferred_skill_reads
        or resolved_route_plan.selection_reason
    ):
        lines.append("<progressive_loading>")
        _append_text_tag(lines, "primary_skill", resolved_route_plan.primary_skill)
        _append_list_tag(lines, "startup_reads", resolved_route_plan.startup_reads)
        _append_list_tag(lines, "secondary_skills", resolved_route_plan.secondary_skills)
        _append_list_tag(lines, "deferred_skills", resolved_route_plan.deferred_skills)
        _append_list_tag(lines, "deferred_skill_reads", resolved_route_plan.deferred_skill_reads)
        _append_list_tag(lines, "selection_reason", resolved_route_plan.selection_reason)
        lines.append("</progressive_loading>")

    return SkillPromptState(
        entries=available_entries,
        matched=matched,
        prompt="\n".join(lines),
        route_plan=resolved_route_plan,
    )

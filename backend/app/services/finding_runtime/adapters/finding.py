from __future__ import annotations

from app.services.agent.skill_service import SkillService
from app.services.finding_runtime.memory import RuntimeMemoryManager, build_memory_message
from app.services.finding_runtime.models import RuntimeMessageRole, TranscriptItem
from app.services.finding_runtime.skills import RuntimeSkillCatalog


class FindingRuntimeAdapter:
    DEFAULT_USER_MESSAGE = "Continue the audit with the current Finding objective."

    def __init__(
        self,
        *,
        session_store,
        runner,
        skill_catalog: RuntimeSkillCatalog | None = None,
        memory_manager: RuntimeMemoryManager | None = None,
    ):
        self._session_store = session_store
        self._runner = runner
        self._skill_catalog = skill_catalog or RuntimeSkillCatalog()
        self._memory_manager = memory_manager or RuntimeMemoryManager(
            session_factory=getattr(session_store, "_session_factory", None)
        )

    async def run(
        self,
        *,
        project_id: str,
        task_id: str | None,
        system_prompt: str,
        recon_payload: dict,
        user_message: str | None = None,
        model_name: str = "finding-runtime",
    ) -> dict:
        session_id = self._session_store.create_session(
            project_id=project_id,
            task_id=task_id,
            runtime_stack="runtime",
            system_prompt=system_prompt,
            recon_payload=recon_payload,
        )
        effective_user_message = user_message or self.DEFAULT_USER_MESSAGE
        skill_context = await self._skill_catalog.preload(
            user_id=None,
            agent_type="finding",
            context={
                "recon_data": recon_payload,
                "project_info": recon_payload.get("project_info", {}),
                "task": effective_user_message,
                "config": {},
            },
        )
        self._session_store.replace_skills(
            session_id,
            skill_context.available_skills,
            matched_skill_refs={str(item.get("slug") or item.get("id") or item.get("name") or "") for item in skill_context.matched_skills},
        )

        primary_skill = str(skill_context.route_plan.get("primary_skill") or "").strip()
        skill_bootstrap_text = ""
        if primary_skill:
            try:
                skill_body = await SkillService.get_skill_body(None, primary_skill, agent_type="finding")
            except Exception:
                skill_body = None
            if isinstance(skill_body, dict):
                skill_text = str(
                    skill_body.get("content")
                    or skill_body.get("body")
                    or skill_body.get("markdown")
                    or ""
                ).strip()
                if not skill_text:
                    skill_text = str(skill_body)
                skill_bootstrap_text = f"Primary skill bootstrap: {primary_skill}\n\n{skill_text[:6000]}"

        memory_bundle = await self._memory_manager.preload(
            agent_type="finding",
            system_prompt=system_prompt,
            recon_payload=recon_payload,
            user_message=effective_user_message,
            skill_context={
                "prompt": skill_context.prompt,
                "route_plan": skill_context.route_plan,
            },
        )
        self._session_store.replace_memories(session_id, memory_bundle.all_memories)

        prompt_sections = [system_prompt.strip()]
        if skill_context.prompt.strip():
            prompt_sections.append(skill_context.prompt.strip())
        if skill_context.route_message.strip():
            prompt_sections.append(skill_context.route_message.strip())
        if skill_bootstrap_text.strip():
            prompt_sections.append(skill_bootstrap_text.strip())
        for memory in memory_bundle.all_memories:
            prompt_sections.append(build_memory_message(memory))
        enriched_system_prompt = "\n\n".join(section for section in prompt_sections if section)
        self._session_store.update_system_prompt(session_id, enriched_system_prompt)

        self._session_store.append_message(
            session_id,
            TranscriptItem(
                role=RuntimeMessageRole.USER,
                content=effective_user_message,
            ),
        )
        runner_result = await self._runner.run_once(session_id=session_id, model_name=model_name)
        return {
            "session_id": session_id,
            "runner_result": runner_result,
            "skill_route": skill_context.route_plan,
            "memory_counts": {
                "instruction": len(memory_bundle.instructions),
                "recall": len(memory_bundle.recalls),
            },
        }

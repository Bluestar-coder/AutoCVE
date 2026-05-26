import json

import pytest

from app.services.init_agent_assets import init_skill_bindings
from app.services.skill_file_service import SkillFileService


def test_skill_file_service_write_and_read_stay_on_canonical_skill_root(tmp_path, monkeypatch):
    monkeypatch.setattr(SkillFileService, "project_root", classmethod(lambda cls: tmp_path))

    skill = SkillFileService.write_skill(
        slug="alpha",
        name="alpha",
        description="Alpha skill",
        content="# Alpha",
        tags=["finding"],
    )

    installed_index = json.loads(
        (tmp_path / "skill_library" / ".runtime" / "installed_skills.json").read_text(encoding="utf-8")
    )

    assert skill["slug"] == "alpha"
    assert (tmp_path / "skill_library" / "alpha" / "SKILL.md").exists()
    assert not (tmp_path / "skill_library" / "agents" / "finding" / "alpha").exists()
    assert installed_index["skills"][0]["slug"] == "alpha"
    assert installed_index["skills"][0]["source_type"] == "manual"
    assert installed_index["skills"][0]["bound_agents"] == []
    assert installed_index["skills"][0]["skill_file"].replace("\\", "/").endswith("skill_library/alpha/SKILL.md")


def test_skill_file_service_binding_refresh_no_longer_creates_agent_skill_mirror(tmp_path, monkeypatch):
    monkeypatch.setattr(SkillFileService, "project_root", classmethod(lambda cls: tmp_path))

    SkillFileService.write_skill(
        slug="alpha",
        name="alpha",
        description="Alpha skill",
        content="# Alpha",
        tags=["finding"],
    )

    binding = SkillFileService.upsert_binding(
        "finding",
        "alpha",
        enabled=True,
        always_include=True,
        sort_order=1,
        match_keywords=["auth"],
    )

    aggregated = json.loads((tmp_path / "skill_library" / "alpha" / "bindings.json").read_text(encoding="utf-8"))
    installed_index = json.loads(
        (tmp_path / "skill_library" / ".runtime" / "installed_skills.json").read_text(encoding="utf-8")
    )

    assert binding["skill_id"] == "alpha"
    assert aggregated["skills"][0]["skill_id"] == "alpha"
    assert aggregated["skills"][0]["skill_file"].replace("\\", "/").endswith("skill_library/alpha/SKILL.md")
    assert aggregated["skills"][0]["workspace_relative_path"] == "skill_library/alpha"
    assert not (tmp_path / "skill_library" / "agents" / "finding" / "alpha").exists()
    assert installed_index["skills"][0]["bound_agents"] == ["finding"]
    assert installed_index["skills"][0]["bindings"][0]["id"] == "finding:alpha"


@pytest.mark.asyncio
async def test_audit_chat_agent_bindings_default_to_all_local_skills(tmp_path, monkeypatch):
    monkeypatch.setattr(SkillFileService, "project_root", classmethod(lambda cls: tmp_path))

    SkillFileService.write_skill(
        slug="alpha",
        name="alpha",
        description="Alpha skill",
        content="# Alpha",
        tags=[],
    )
    SkillFileService.write_skill(
        slug="beta",
        name="beta",
        description="Beta skill",
        content="# Beta",
        tags=[],
    )

    await init_skill_bindings()

    payload = SkillFileService.get_agent_bindings("audit_chat")
    assert payload["agent_type"] == "audit_chat"
    assert [item["slug"] for item in payload["skills"]] == ["alpha", "beta"]
    assert all(item["enabled"] for item in payload["skills"])

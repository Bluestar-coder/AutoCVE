# Runtime Core Alignment Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shared Runtime Core that fully upgrades AuditAI from prompt-assisted skill selection to a restored-style unified runtime for skills, tools, hooks, permissions, session memory, and generic interaction primitives across all agents.

**Architecture:** Reuse `backend/app/services/finding_runtime/` as the seed and extract a new shared runtime layer consumed by finding, orchestrator, recon, and verification. Move Skill invocation, tool execution, permission decisions, hook lifecycle, session memory, and interaction primitives behind shared registries/orchestrators so agent code becomes a consumer of runtime state instead of implementing sidecar logic.

**Tech Stack:** Python 3.12, FastAPI backend, SQLAlchemy models/session store, existing agent tool abstractions, runtime session persistence, Docker Compose, pytest.

---

## Scope Decision

This work spans multiple subsystems, but they are all part of one shared runtime program. We should not keep implementing them independently per agent. The execution order below treats them as one Runtime Core migration with explicit integration checkpoints.

## File Structure

### Shared runtime core to create or expand
- Create: `backend/app/services/runtime_core/__init__.py`
- Create: `backend/app/services/runtime_core/models.py`
- Create: `backend/app/services/runtime_core/session_state.py`
- Create: `backend/app/services/runtime_core/session_registry.py`
- Create: `backend/app/services/runtime_core/skill_registry.py`
- Create: `backend/app/services/runtime_core/skill_invocation.py`
- Create: `backend/app/services/runtime_core/tool_runtime.py`
- Create: `backend/app/services/runtime_core/tool_registry.py`
- Create: `backend/app/services/runtime_core/tool_orchestrator.py`
- Create: `backend/app/services/runtime_core/hook_runtime.py`
- Create: `backend/app/services/runtime_core/permission_runtime.py`
- Create: `backend/app/services/runtime_core/memory_runtime.py`
- Create: `backend/app/services/runtime_core/interaction_runtime.py`

### Existing runtime and agent files to migrate
- Modify: `backend/app/services/agent/skill_service.py`
- Modify: `backend/app/services/skill_file_service.py`
- Modify: `backend/app/services/skills_runtime/catalog.py`
- Modify: `backend/app/services/skills_runtime/discovery.py`
- Modify: `backend/app/services/skills_runtime/filters.py`
- Modify: `backend/app/services/skills_runtime/models.py`
- Modify: `backend/app/services/skills_runtime/prompt.py`
- Modify: `backend/app/services/skills_runtime/route_plan.py`
- Modify: `backend/app/services/finding_runtime/tooling.py`
- Modify: `backend/app/services/finding_runtime/skills.py`
- Modify: `backend/app/services/finding_runtime/memory.py`
- Modify: `backend/app/services/finding_runtime/session_store.py`
- Modify: `backend/app/services/finding_runtime/adapters/finding.py`
- Modify: `backend/app/services/agent/agents/finding.py`
- Modify: `backend/app/services/agent/agents/finding_skill_preloader.py`
- Modify: `backend/app/services/agent/agents/finding_skill_router.py`
- Modify: `backend/app/services/init_agent_assets.py`

### Generic interaction and tool integration files to add later in the same program
- Create: `backend/app/services/agent/tools/runtime_skill_tool.py`
- Create: `backend/app/services/agent/tools/todo_runtime_tool.py`
- Create: `backend/app/services/agent/tools/ask_user_runtime_tool.py`
- Create: `backend/app/services/agent/tools/plan_mode_runtime_tool.py`
- Modify: `backend/app/services/agent/tools/base.py`
- Modify: `backend/app/services/agent/streaming/tool_stream.py`
- Modify: `backend/app/services/agent/config.py`

### Persistence and tests
- Modify: `backend/app/models/audit_session.py`
- Create: `backend/tests/runtime_core/test_session_state.py`
- Create: `backend/tests/runtime_core/test_skill_registry.py`
- Create: `backend/tests/runtime_core/test_skill_invocation.py`
- Create: `backend/tests/runtime_core/test_tool_runtime.py`
- Create: `backend/tests/runtime_core/test_hook_runtime.py`
- Create: `backend/tests/runtime_core/test_permission_runtime.py`
- Create: `backend/tests/runtime_core/test_memory_runtime.py`
- Create: `backend/tests/runtime_core/test_interaction_runtime.py`
- Modify: `backend/tests/skills_runtime/test_compat_skill_service.py`
- Modify: `backend/tests/skills_runtime/test_skill_tools.py`
- Modify: `backend/tests/finding_runtime/test_skills.py`
- Modify: `backend/tests/finding_runtime/test_bridge.py`
- Modify: `backend/tests/agent/test_finding_v2.py`
- Modify: `backend/tests/agent/test_agent_contracts.py`

## Chunk 1: Shared Runtime Core Skeleton

### Task 1: Introduce shared runtime-core models and session state

**Files:**
- Create: `backend/app/services/runtime_core/models.py`
- Create: `backend/app/services/runtime_core/session_state.py`
- Test: `backend/tests/runtime_core/test_session_state.py`

- [ ] **Step 1: Write the failing tests for session-scoped runtime state**

Cover:
- session-level invoked skills
- per-agent invoked skill state
- progressive loading phase per skill (`catalog`, `body`, `references`, `scripts`)
- touched paths cache
- permission mode
- pending interaction state

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/runtime_core/test_session_state.py -q`
Expected: FAIL because the shared runtime state module does not exist yet.

- [ ] **Step 3: Write minimal runtime state models**

Implement:
- session runtime state dataclasses/pydantic models
- `InvokedSkillState`
- `AgentRuntimeState`
- `SessionRuntimeState`
- helper methods for marking a skill as invoked and promoting load stage

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend; $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/runtime_core/test_session_state.py -q`
Expected: PASS

### Task 2: Add a shared runtime session registry on top of the existing session store

**Files:**
- Create: `backend/app/services/runtime_core/session_registry.py`
- Modify: `backend/app/services/finding_runtime/session_store.py`
- Modify: `backend/app/models/audit_session.py`
- Test: `backend/tests/runtime_core/test_session_state.py`

- [ ] **Step 1: Write the failing persistence tests for invoked skill/session state**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Extend persistence models and session store with runtime-state read/write helpers**
- [ ] **Step 4: Run test to verify it passes**

## Chunk 2: Skill Registry and True Skill Invocation Runtime

### Task 3: Unify installed skills, sources, revisions, and per-agent bindings in one registry

**Files:**
- Modify: `backend/app/services/skill_file_service.py`
- Create: `backend/app/services/runtime_core/skill_registry.py`
- Modify: `backend/app/services/skills_runtime/models.py`
- Test: `backend/tests/runtime_core/test_skill_registry.py`
- Test: `backend/tests/skills_runtime/test_compat_skill_file_service.py`

- [ ] **Step 1: Write failing tests for registry fields**

Cover:
- source kind (`bundled`, `local`, `github`, future `mcp` placeholder)
- installed source/revision/version
- installed_by / installed_at
- enabled / disabled state
- per-agent bindings included in registry view

- [ ] **Step 2: Run the new registry tests and verify they fail**
- [ ] **Step 3: Expand the installed skill index and registry adapter**
- [ ] **Step 4: Run the registry and compat tests and verify they pass**

### Task 4: Build a general SkillTool runtime primitive

**Files:**
- Create: `backend/app/services/runtime_core/skill_invocation.py`
- Modify: `backend/app/services/finding_runtime/skills.py`
- Create: `backend/app/services/agent/tools/runtime_skill_tool.py`
- Test: `backend/tests/runtime_core/test_skill_invocation.py`
- Test: `backend/tests/skills_runtime/test_skill_tools.py`

- [ ] **Step 1: Write failing tests for explicit skill invocation**

Cover:
- invoking a skill body through runtime
- listing references/examples/scripts through runtime
- recording invocation metadata to session state and persistence
- different agents invoking different skills without leaking state

- [ ] **Step 2: Run the invocation tests and verify they fail**
- [ ] **Step 3: Implement the shared SkillTool runtime and adapt the existing finding runtime skill tool to call it**
- [ ] **Step 4: Run tests to verify they pass**

### Task 5: Implement true progressive loading semantics

**Files:**
- Modify: `backend/app/services/runtime_core/skill_invocation.py`
- Modify: `backend/app/services/skills_runtime/catalog.py`
- Modify: `backend/app/services/skills_runtime/filters.py`
- Modify: `backend/app/services/skills_runtime/route_plan.py`
- Test: `backend/tests/runtime_core/test_skill_invocation.py`
- Test: `backend/tests/skills_runtime/test_compat_skill_service.py`

- [ ] **Step 1: Write failing tests for multi-stage loading**

Cover:
- first invoke returns `SKILL.md` body only
- later invoke can expand to references/scripts
- path-triggered activation from touched files
- session state suppresses repeated full bootstrap

- [ ] **Step 2: Run the tests and verify they fail**
- [ ] **Step 3: Implement stage-aware loading and touched-path activation**
- [ ] **Step 4: Run tests to verify they pass**

### Task 6: Execute frontmatter semantics instead of only parsing them

**Files:**
- Modify: `backend/app/services/runtime_core/skill_invocation.py`
- Modify: `backend/app/services/runtime_core/skill_registry.py`
- Modify: `backend/app/services/skills_runtime/discovery.py`
- Modify: `backend/app/services/skills_runtime/models.py`
- Test: `backend/tests/runtime_core/test_skill_invocation.py`

- [ ] **Step 1: Write failing tests for frontmatter enforcement**

Cover:
- `allowed-tools`
- `context`
- `agent`
- `model`
- `effort`
- `hooks`
- `paths`
- `disable-model-invocation`
- `user-invocable`

- [ ] **Step 2: Run the tests and verify they fail**
- [ ] **Step 3: Implement frontmatter execution policy objects and apply them during skill invocation**
- [ ] **Step 4: Run tests to verify they pass**

## Chunk 3: Shared Tool Runtime, Hooks, and Permissions

### Task 7: Extract a shared tool runtime from finding_runtime/tooling.py

**Files:**
- Create: `backend/app/services/runtime_core/tool_runtime.py`
- Create: `backend/app/services/runtime_core/tool_registry.py`
- Create: `backend/app/services/runtime_core/tool_orchestrator.py`
- Modify: `backend/app/services/finding_runtime/tooling.py`
- Test: `backend/tests/runtime_core/test_tool_runtime.py`

- [ ] **Step 1: Write failing tests for shared tool orchestration**

Cover:
- validation
- concurrency partitioning
- permission gate callback
- pre/post hooks
- uniform result envelope
- telemetry/event payload hooks

- [ ] **Step 2: Run the tool-runtime tests and verify they fail**
- [ ] **Step 3: Extract the shared tool runtime and adapt finding_runtime/tooling to delegate to it**
- [ ] **Step 4: Run the tests and verify they pass**

### Task 8: Add shared hook runtime compatible with skill frontmatter hooks

**Files:**
- Create: `backend/app/services/runtime_core/hook_runtime.py`
- Modify: `backend/app/services/runtime_core/skill_invocation.py`
- Test: `backend/tests/runtime_core/test_hook_runtime.py`

- [ ] **Step 1: Write failing tests for session-scoped and agent-scoped hooks**
- [ ] **Step 2: Run the tests and verify they fail**
- [ ] **Step 3: Implement hook registration, event dispatch, and Stop/SubagentStop semantics**
- [ ] **Step 4: Run the tests and verify they pass**

### Task 9: Add a general permission runtime that every tool and skill call uses

**Files:**
- Create: `backend/app/services/runtime_core/permission_runtime.py`
- Modify: `backend/app/services/runtime_core/tool_runtime.py`
- Modify: `backend/app/services/runtime_core/skill_invocation.py`
- Test: `backend/tests/runtime_core/test_permission_runtime.py`

- [ ] **Step 1: Write failing tests for allow/deny/ask policy resolution**
- [ ] **Step 2: Run the tests and verify they fail**
- [ ] **Step 3: Implement session-scoped + persisted + managed permission decision layers**
- [ ] **Step 4: Run the tests and verify they pass**

## Chunk 4: Generic Interaction Runtime and Session Memory OS

### Task 10: Add Todo / AskUser / Plan-mode runtime primitives

**Files:**
- Create: `backend/app/services/runtime_core/interaction_runtime.py`
- Create: `backend/app/services/agent/tools/todo_runtime_tool.py`
- Create: `backend/app/services/agent/tools/ask_user_runtime_tool.py`
- Create: `backend/app/services/agent/tools/plan_mode_runtime_tool.py`
- Test: `backend/tests/runtime_core/test_interaction_runtime.py`

- [ ] **Step 1: Write failing tests for todo lists, user questions, and plan-mode state**
- [ ] **Step 2: Run the tests and verify they fail**
- [ ] **Step 3: Implement the interaction runtime and expose it through agent tools**
- [ ] **Step 4: Run the tests and verify they pass**

### Task 11: Promote finding memory preload into a generic session memory runtime

**Files:**
- Create: `backend/app/services/runtime_core/memory_runtime.py`
- Modify: `backend/app/services/finding_runtime/memory.py`
- Modify: `backend/app/services/finding_runtime/adapters/finding.py`
- Test: `backend/tests/runtime_core/test_memory_runtime.py`

- [ ] **Step 1: Write failing tests for session memory extraction and refresh cadence**
- [ ] **Step 2: Run the tests and verify they fail**
- [ ] **Step 3: Implement shared memory runtime and adapt finding to consume it**
- [ ] **Step 4: Run the tests and verify they pass**

## Chunk 5: Agent Integration and Finding Completion Alignment

### Task 12: Migrate agents to the shared runtime core

**Files:**
- Modify: `backend/app/services/agent/skill_service.py`
- Modify: `backend/app/services/agent/tools/base.py`
- Modify: `backend/app/services/agent/streaming/tool_stream.py`
- Modify: `backend/app/services/agent/config.py`
- Modify: `backend/app/services/agent/agents/finding.py`
- Modify: `backend/app/services/finding_runtime/adapters/finding.py`
- Test: `backend/tests/agent/test_agent_contracts.py`
- Test: `backend/tests/agent/test_finding_v2.py`

- [ ] **Step 1: Write failing integration tests for shared runtime consumption by agents**
- [ ] **Step 2: Run the tests and verify they fail**
- [ ] **Step 3: Adapt finding first, then wire orchestrator/recon/verification to the same runtime services**
- [ ] **Step 4: Run the tests and verify they pass**

### Task 13: Replace countdown-first finding termination with runtime-state completion rules

**Files:**
- Modify: `backend/app/services/agent/agents/finding.py`
- Modify: `backend/app/services/agent/agents/finding_controller.py`
- Modify: `backend/app/services/finding_runtime/adapters/finding.py`
- Test: `backend/tests/agent/test_finding_v2.py`
- Test: `backend/tests/finding_runtime/test_bridge.py`

- [ ] **Step 1: Write failing tests for evidence-based completion and no-progress termination**
- [ ] **Step 2: Run the tests and verify they fail**
- [ ] **Step 3: Replace fixed 6/3/1 coercion with shared runtime completion signals**
- [ ] **Step 4: Run the tests and verify they pass**

## Verification Milestones

- `cd backend; $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/skills_runtime -q`
- `cd backend; $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/runtime_core -q`
- `cd backend; $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/finding_runtime -q`
- `cd backend; $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/agent/test_agent_contracts.py tests/agent/test_finding_v2.py -q`
- `docker compose up -d --build backend`
- `docker compose logs --tail=200 backend`

## Recommended Execution Order

1. Chunk 1 first, because all later runtime behaviors need a stable session model.
2. Chunk 2 next, because explicit SkillTool invocation and invoked-skill session state are your highest-priority restored parity features.
3. Chunk 3 next, because Skill invocation must join the same tool/permission/hook runtime rather than staying a side channel.
4. Chunk 4 after that, because Todo / AskUser / Plan-mode and session memory should sit on the same shared runtime substrate.
5. Chunk 5 last, because agent migrations and finding completion changes should happen only after the shared runtime is real.

## Immediate First Slice

- Phase 1D: shared runtime session state + invoked-skills persistence
- Phase 1E: shared SkillTool runtime + true progressive loading
- Phase 1F: frontmatter execution semantics and session-hot install visibility
- Phase 1G: unify SkillTool with shared tool runtime, hooks, and permissions

Plan complete and saved to `docs/superpowers/plans/2026-04-08-runtime-core-alignment-implementation-plan.md`. Ready to execute.

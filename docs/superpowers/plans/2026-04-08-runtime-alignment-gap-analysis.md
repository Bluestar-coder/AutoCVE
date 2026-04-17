# AuditAI Runtime Alignment Gap Analysis

> Focus: compare `AuditAI-1.0.0` against `restored-from-cli-map-v3`, then phase migration work in the user-requested priority order.

## Current Gap Summary

### 1. Skill frontmatter and skill runtime semantics

- `AuditAI` already has a partial skills runtime in `backend/app/services/skills_runtime/`, but its metadata model is still thin.
- `backend/app/services/skills_runtime/models.py` only tracks `slug/name/description/tags/frontmatter/source_type/source_url` plus simple binding fields like `always_include`, `sort_order`, `match_keywords`, and `match_config`.
- `backend/app/services/skills_runtime/discovery.py` parses frontmatter with a line-based `key: value` parser and only supports primitive booleans/lists; it does not implement the richer semantics visible in `restored-from-cli-map-v3/src/skills/loadSkillsDir.ts`.
- `backend/app/services/skills_runtime/prompt.py` only emits a flat `<available_skills>` block and does not carry over execution semantics such as `allowed-tools`, `when_to_use`, `argument-hint`, `arguments`, `model`, `effort`, `context`, `agent`, `shell`, `hooks`, `paths`, `user-invocable`, conditional activation, or dynamic discovery.
- `backend/app/services/skills_runtime/route_plan.py` currently picks the first matched skill or first available skill; it does not reproduce the richer progressive-loading model from `restored-from-cli-map-v3`.
- `backend/app/services/skills_runtime/access.py` does implement basic path containment checks, so AuditAI already has the seed of safe skill resource access.

### 2. Finding orchestration and convergence

- `backend/app/services/agent/agents/finding_controller.py` hard-codes controller and worker budgets (`controller_budget=12`, `worker_budget=10`, `followup_worker_budget=4`, `max_followup_rounds_per_candidate=2`).
- `backend/app/services/agent/agents/finding.py` forces `report_finalization` when a closed exploit chain exists or when `rounds_left <= 6`, then adds stronger pressure at 6 / 3 / 1 rounds left.
- `backend/app/services/agent/agents/finding_loop_detector.py` blocks repeated no-progress tool patterns after three repeats, but this is still local anti-loop logic, not a general completion model.
- The current runtime is therefore better than the old single-loop agent, but it is still budget-first and phase-threshold-first. It does not yet have the more general “task runtime decides completion from task state + tool/task outcomes + hook outputs + user/runtime interrupts” style found in `restored-from-cli-map-v3`.

### 3. Generic interaction runtime

- In the current `AuditAI` codebase I did not find a general `TodoWrite`, `AskUser`, or `Plan-mode` runtime layer.
- `restored-from-cli-map-v3` has dedicated generic tools and stateful runtime for these interactions:
  - `src/tools/TodoWriteTool/TodoWriteTool.ts`
  - `src/tools/AskUserQuestionTool/AskUserQuestionTool.tsx`
  - `src/tools/EnterPlanModeTool/EnterPlanModeTool.ts`

### 4. Unified tool runtime and concurrent orchestration

- `AuditAI` still exposes tools mainly as per-agent/backend tool implementations; there is no evidence of a full shared tool runtime with uniform permission checks, hook execution, streaming progress, structured tool-result mapping, and concurrency partitioning.
- `restored-from-cli-map-v3` clearly has that layer in:
  - `src/services/tools/toolExecution.ts`
  - `src/services/tools/toolOrchestration.ts`
  - `src/services/tools/StreamingToolExecutor.ts`

### 5. Generic permission system and session memory OS

- `AuditAI` does not currently show a general cross-tool permission rule engine comparable to the restored runtime.
- `AuditAI` only has LLM-side compression (`backend/app/services/llm/memory_compressor.py`), not a full session memory operating system with extraction thresholds, persistence, update cadence, and turn-end memory workflows.
- `restored-from-cli-map-v3` has dedicated session-memory and permission subsystems:
  - `src/services/SessionMemory/sessionMemoryUtils.ts`
  - `src/utils/permissions/permissionsLoader.ts`
  - `src/query/stopHooks.ts`

### 6. Hooks lifecycle and MCP

- `AuditAI` currently has no visible general hook lifecycle or MCP external-resource runtime comparable to the restored runtime.
- `restored-from-cli-map-v3` has both:
  - hooks: `src/utils/hooks/registerFrontmatterHooks.ts`, `src/query/stopHooks.ts`
  - MCP: `src/tools/ListMcpResourcesTool/ListMcpResourcesTool.ts`, `src/tools/ReadMcpResourceTool/ReadMcpResourceTool.ts`, `src/tools/MCPTool/MCPTool.ts`

## Reference Runtime Behaviors To Align Toward

### Skills

- `restored-from-cli-map-v3/src/skills/loadSkillsDir.ts` parses and enforces richer frontmatter fields:
  - `allowed-tools`
  - `when_to_use`
  - `arguments`
  - `argument-hint`
  - `model`
  - `effort`
  - `context`
  - `agent`
  - `shell`
  - `hooks`
  - `paths`
  - `user-invocable`
  - `disable-model-invocation`
- It also supports:
  - multi-source loading (`managed`, `user`, `project`, `plugin`, `bundled`, `mcp`)
  - dedup by canonical realpath
  - dynamic skill discovery from touched paths
  - conditional activation via `paths`
  - MCP skill registration

### Hooks

- `restored-from-cli-map-v3/src/utils/hooks/registerFrontmatterHooks.ts` registers frontmatter hooks into session-scoped hooks and converts `Stop` to `SubagentStop` for agent contexts.
- `restored-from-cli-map-v3/src/query/stopHooks.ts` runs stop hooks, task-completed hooks, teammate-idle hooks, turn-end memory extraction, auto-dream, and cleanup in one turn-finalization path.

### Tool runtime

- `restored-from-cli-map-v3/src/services/tools/toolExecution.ts` centralizes:
  - tool lookup
  - validation
  - permission checks
  - pre/post tool hooks
  - progress streaming
  - telemetry
  - result shaping
  - abort/error handling
- `restored-from-cli-map-v3/src/services/tools/toolOrchestration.ts` partitions tool calls into concurrency-safe and serial batches.
- `restored-from-cli-map-v3/src/services/tools/StreamingToolExecutor.ts` streams progress/results while preserving ordering and interruption semantics.

### Interaction runtime

- `TodoWriteTool` manages session/agent-local task lists and injects verification nudges at completion boundaries.
- `AskUserQuestionTool` is a true runtime primitive with schemas, permission prompts, result messages, answer annotations, and UI contracts.
- `EnterPlanModeTool` changes session permission mode and injects execution-policy instructions for plan-only turns.

## Phased Migration Checklist

### Phase 1. Complete Skill Runtime Alignment

- Replace the current minimal frontmatter parser in `backend/app/services/skills_runtime/discovery.py` with a schema-based parser aligned to the restored runtime semantics.
- Expand `backend/app/services/skills_runtime/models.py` so `SkillEntry` can represent:
  - `allowed_tools`
  - `when_to_use`
  - `argument_hint`
  - `argument_names`
  - `version`
  - `model`
  - `disable_model_invocation`
  - `user_invocable`
  - `hooks`
  - `execution_context`
  - `agent`
  - `effort`
  - `shell`
  - `paths`
  - `loaded_from`
- Rework `backend/app/services/skills_runtime/prompt.py` so agents see a compact skill catalog plus execution semantics, not just a flat file listing.
- Rework `backend/app/services/skills_runtime/route_plan.py` to support:
  - deterministic selection
  - conditional activation
  - path-triggered progressive loading
  - per-agent selection semantics
  - cross-agent skill visibility boundaries
- Add dynamic skill discovery and path-activated skills modeled after `restored-from-cli-map-v3/src/skills/loadSkillsDir.ts`.
- Introduce session/agent-scoped “invoked skill” tracking so each agent only progressively loads the skills it actually invoked.
- Align skill resource access rules so every agent reads only its bound/selected skill roots.
- Add true multi-agent skill isolation:
  - main orchestrator skill set
  - finding-specific skill set
  - optional specialized skills for recon / verification / triage
- Implement skill installation/import pipeline:
  - canonical source of installed skills
  - per-agent bindings
  - runtime index/update records
  - optional import from packaged/local skill bundles
  - later extension point for remote/MCP-provided skills

### Phase 2. Rebuild Finding Task Runtime and Completion Model

- Stop treating finding completion primarily as a countdown problem.
- Extract a generic task runtime abstraction from the current `finding.py` loop:
  - task state
  - candidate queue state
  - evidence state
  - per-candidate worker state
  - completion conditions
  - yield / pause / rotate / finalize transitions
- Keep the current coverage-first queueing logic as one strategy, but move budgets and round thresholds behind policy objects rather than hard-coded phase switches.
- Replace fixed late-phase coercion (`6 / 3 / 1` rounds) with a layered termination model:
  - objective completion: enough validated evidence exists
  - exploration exhaustion: candidate queue truly drained or dominated
  - no-progress exhaustion: repeated non-advancing actions after structural alternatives explored
  - runtime interrupts: timeout, user stop, permission denial, tool failure storm
  - finalization readiness: evidence can be serialized without more exploration
- Preserve checkpointing, but make it a recovery/continuity feature instead of the main reason the loop converges.
- Add explicit “continue / pause / finalize / spawn verifier / rotate candidate” runtime actions, so the model is guided by runtime state instead of only prompt pressure.
- Add stronger runtime feedback to the model when evidence is insufficient:
  - what remains unverified
  - what candidate coverage remains
  - whether new tools/tasks are still warranted
- Study the latest audit record under `liuyh67@lenovo.com` and derive empirical anti-premature-convergence cases:
  - unexplored priority paths still present
  - unresolved authz/business-flow branches
  - no verification handoff despite strong candidate
  - finalization entered because of countdown, not evidence sufficiency

### Phase 3. Introduce Generic Interaction Runtime

- Add generic runtime tools equivalent to:
  - `TodoWrite`
  - `AskUser`
  - `EnterPlanMode`
  - `ExitPlanMode`
- Define shared state containers for:
  - per-session todo lists
  - per-agent todo lists
  - pending user questions
  - plan-mode state and permission-mode transitions
- Make these runtime primitives reusable by orchestrator, finding, verification, and future agents.
- Wire frontend/backend event streams so these interactions are first-class runtime events instead of ad hoc text.
- After this phase, finding/orchestrator should be able to:
  - ask for clarification through runtime
  - explicitly switch into plan-only exploration mode
  - maintain structured todo state across turns/agents

### Phase 4. Add Unified Tool Runtime and Parallel Orchestrator

- Introduce a shared tool execution layer comparable to the restored runtime:
  - input validation
  - permission gate
  - pre/post tool hooks
  - progress events
  - standardized tool results
  - structured errors
  - telemetry
- Add tool classification for concurrency-safe versus serial tools.
- Add a shared streaming executor that can:
  - queue tools
  - run read-only tools concurrently
  - preserve output ordering
  - propagate cancellation and sibling failures coherently
- Migrate finding/recon/verification/orchestrator to the same tool runtime instead of per-agent ad hoc execution paths.

### Phase 5. Add Generic Permission Runtime and Session Memory OS

- Implement a real permission rule model:
  - session-scoped rules
  - persisted rules
  - managed/policy rules
  - per-tool/per-command/per-path rules
  - allow/deny/ask behavior
- Add permission-mode transitions needed by plan mode and future agent/tool runtimes.
- Add a session memory subsystem instead of only LLM compression:
  - thresholds to initialize memory
  - thresholds to refresh memory
  - tool-call-based extraction cadence
  - durable session memory artifacts
  - turn-end extraction hooks
  - optional compaction / summarization policy

### Phase 6. Hooks Lifecycle and MCP

- Add session-scoped and agent-scoped hooks lifecycle:
  - pre-tool
  - post-tool
  - tool-failure
  - stop / subagent-stop
  - task-completed
- Add MCP runtime only after the earlier phases stabilize:
  - list resources
  - read resources
  - tool bridging
  - auth and status
  - output storage

## Recommended Execution Order

1. Finish Phase 1 first. Without the complete skill runtime semantics, every agent-level migration stays half-manual.
2. Then do Phase 2. This is the highest-impact runtime change for finding quality and premature convergence.
3. Then do Phase 3 + Phase 4 together or back-to-back, because plan/todo/ask-user runtime should sit on top of the shared tool runtime, not beside it.
4. Then do Phase 5.
5. Leave Phase 6 for last unless a previous phase proves blocked by hook infrastructure.

## Suggested First Implementation Slice

- Phase 1A: skill metadata model + parser parity
- Phase 1B: prompt-state parity + progressive loading
- Phase 1C: per-agent bindings + installation/import model
- Phase 2A: generic finding runtime state machine extraction
- Phase 2B: replace forced 6/3/1 finalization with evidence-based completion policy
- Phase 2C: replay latest failed audit records to tune stop conditions

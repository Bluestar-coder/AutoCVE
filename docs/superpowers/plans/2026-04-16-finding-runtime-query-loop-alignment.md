# Finding Runtime Query Loop Alignment Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AuditAI Finding Runtime fully align with `restored-from-cli-map-v3/src/query.ts` ReAct loop semantics, including explicit loop state, per-turn stage ordering, continue/terminal reasons, degradation and recovery paths, context preprocessing, context injection, message normalization, API calling, tool execution, stop hooks, and between-turn attachments.

**Architecture:** Refactor the current thin `query_loop.py + runner.py + bridge.py` flow into an explicit query-runtime state machine under `backend/app/services/finding_runtime/`. Land parity in layers: first align state vocabulary and transition reasons, then align stage ordering and checkpoints, then fill in recovery/compact/hook capabilities. This allows placeholder transitions such as `reactive_compact_retry` to exist before the expensive underlying implementation is ready.

**Tech Stack:** Python 3.12, FastAPI backend, SQLAlchemy audit session persistence, `runtime_core` services, existing LLM service, pytest.

---

## Scope And Alignment Target

- Reference behavior is `D:\ÎÄ¼þ\pythonProject\AICVE\AutoCVE\Projects\package\restored-from-cli-map-v3\src\query.ts` plus its helper surfaces in `src/query/stopHooks.ts` and `src/utils/messages.ts`.
- Primary migration target is the current runtime path:
  - `backend/app/services/finding_runtime/query_loop.py`
  - `backend/app/services/finding_runtime/runner.py`
  - `backend/app/services/finding_runtime/bridge.py`
  - `backend/app/services/finding_runtime/adapters/finding.py`
- This plan does **not** migrate legacy candidate/controller logic from `backend/app/services/agent/agents/finding.py`. Candidate queueing is a separate concern from `query.ts` loop parity.
- ¡°Fully aligned¡± means:
  - same loop state shape
  - same continue reasons and terminal reasons
  - same single-iteration stage ordering
  - same recovery/degradation decision points
  - equivalent hook and token-budget continuation semantics
  - equivalent between-turn message injection semantics

## Current Gap Summary

- Current runtime loop is a minimal two-branch loop:
  - tool calls exist -> execute tools -> continue
  - no tool calls -> coerce stop reason -> terminate
- Current runtime has no explicit `State` object equivalent to restored `query.ts`.
- Current runtime has no parity support for:
  - `max_output_tokens_escalate`
  - `max_output_tokens_recovery`
  - `collapse_drain_retry`
  - `reactive_compact_retry`
  - `stop_hook_blocking`
  - `token_budget_continuation`
- Current runtime does not implement the restored per-turn preprocessing pipeline:
  - compact-boundary slicing
  - tool-result budget handling
  - history snip
  - microcompact
  - context-collapse projection/drain
  - proactive autocompact
- Current runtime does not implement restored-style stop hooks, continuation nudges, withheld recoverable API errors, or between-turn attachment injection.

## Parity Contract

### 1. Target Loop State

Create a first-class `QueryLoopState` that mirrors restored `State`.

- `messages`
  Full logical transcript used as the source for the next iteration.
- `tool_use_context`
  Runtime tool execution context, including available tools, permission mode, abort signal, hook context, and session metadata.
- `auto_compact_tracking`
  Tracks whether compacting already ran, whether it failed, and what boundary/checkpoint was produced.
- `max_output_tokens_recovery_count`
  Counts how many ¡°resume directly¡± retries have already happened.
- `has_attempted_reactive_compact`
  Guards against retry loops for prompt-too-long/media recovery.
- `max_output_tokens_override`
  Per-request override for larger `max_output_tokens`.
- `pending_tool_use_summary`
  Async handle or persisted placeholder for previous turn tool summary generation.
- `stop_hook_active`
  Guard to prevent repeated stop-hook blocking loops.
- `turn_count`
  Restored-style turn counter used by `max_turns`.
- `transition`
  Explicit record of why the last iteration continued.

Implementation note:
- Persist the minimal serializable subset in `audit_sessions.runtime_state_json`.
- Persist per-turn transition/debug snapshots in `AuditCheckpoint.state_payload`.
- Do not keep this as loose local variables in `query_loop.py`.

### 2. Target Continue Reasons

Add a dedicated continue-reason enum and make every continue site write it explicitly.

- `next_turn`
  Model emitted tool calls and tool execution completed.
- `max_output_tokens_escalate`
  Output was truncated and the first retry upgrades token limit.
- `max_output_tokens_recovery`
  Output was truncated after escalation and a ¡°continue from where you left off¡± meta message is injected.
- `reactive_compact_retry`
  Prompt/media recoverable failure triggers reactive compact and retry.
- `collapse_drain_retry`
  Prompt-too-long plus pending context collapse triggers drain and retry.
- `stop_hook_blocking`
  Stop hook injects blocking correction messages and forces another turn.
- `token_budget_continuation`
  Token budget says the model should continue working even without tool use.

### 3. Target Terminal Reasons

Expand `RuntimeStopReason` so terminal outcomes match restored semantics.

- `completed`
- `blocking_limit`
- `prompt_too_long`
- `image_error`
- `model_error`
- `aborted_streaming`
- `aborted_tools`
- `stop_hook_prevented`
- `hook_stopped`
- `max_turns`

### 4. Placeholder-First Rule

Some transitions should exist before the backing subsystem is fully implemented.

Example:
- `reactive_compact_retry` should be introduced in the state machine and checkpoint payloads before AuditAI has a real reactive compact implementation.
- Until the underlying implementation lands, the runtime should:
  - classify the branch correctly
  - record the intended transition
  - attach a deterministic debug note such as `recovery_not_implemented: reactive_compact`
  - fall back to the correct temporary terminal behavior for that phase

This rule applies to:
- `reactive_compact_retry`
- `collapse_drain_retry`
- proactive autocompact
- tool-use summary parallelization
- token-budget continuation policy
- full stop-hook parity

## File Structure

### New finding runtime modules to create

- Create: `backend/app/services/finding_runtime/query_state.py`
- Create: `backend/app/services/finding_runtime/query_transitions.py`
- Create: `backend/app/services/finding_runtime/query_context.py`
- Create: `backend/app/services/finding_runtime/query_messages.py`
- Create: `backend/app/services/finding_runtime/query_degradation.py`
- Create: `backend/app/services/finding_runtime/query_stop_hooks.py`
- Create: `backend/app/services/finding_runtime/query_attachments.py`
- Create: `backend/app/services/finding_runtime/query_token_budget.py`

### Existing finding runtime modules to modify

- Modify: `backend/app/services/finding_runtime/models.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Modify: `backend/app/services/finding_runtime/runner.py`
- Modify: `backend/app/services/finding_runtime/bridge.py`
- Modify: `backend/app/services/finding_runtime/adapters/finding.py`
- Modify: `backend/app/services/finding_runtime/session_store.py`
- Modify: `backend/app/services/finding_runtime/tooling.py`
- Modify: `backend/app/services/finding_runtime/memory.py`
- Modify: `backend/app/services/finding_runtime/skills.py`

### Shared runtime modules likely needing alignment hooks

- Modify: `backend/app/services/runtime_core/tool_runtime.py`
- Modify: `backend/app/services/runtime_core/hook_runtime.py`
- Modify: `backend/app/services/runtime_core/interaction_runtime.py`
- Modify: `backend/app/services/runtime_core/session_state.py`
- Modify: `backend/app/models/audit_session.py`

### Tests to add or expand

- Create: `backend/tests/finding_runtime/test_query_state.py`
- Create: `backend/tests/finding_runtime/test_query_transitions.py`
- Create: `backend/tests/finding_runtime/test_query_degradation.py`
- Create: `backend/tests/finding_runtime/test_query_stop_hooks.py`
- Modify: `backend/tests/finding_runtime/test_bridge.py`
- Modify: `backend/tests/finding_runtime/test_skills.py`
- Modify: `backend/tests/agent/test_finding_v2.py`
- Modify: `backend/tests/runtime_core/test_hook_runtime.py`
- Modify: `backend/tests/runtime_core/test_interaction_runtime.py`

## Chunk 1: State Machine Parity First

### Task 1: Expand enums and result envelopes to carry restored reason vocabulary

**Files:**
- Modify: `backend/app/services/finding_runtime/models.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Modify: `backend/app/services/finding_runtime/runner.py`
- Test: `backend/tests/finding_runtime/test_query_transitions.py`

- [ ] **Step 1: Write failing tests for continue and terminal reason parity**

Cover:
- all seven continue reasons
- all ten terminal reasons
- checkpoint payload contains both `stop_reason` and `transition`

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend; $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/finding_runtime/test_query_transitions.py -q`
Expected: FAIL because the current runtime does not expose restored parity enums or transitions.

- [ ] **Step 3: Expand runtime models**

Implement:
- terminal stop-reason enum parity
- continue-reason enum
- explicit turn result envelope carrying `transition`
- runner behavior that distinguishes terminal reasons from continue transitions

- [ ] **Step 4: Run tests to verify they pass**

### Task 2: Introduce explicit `QueryLoopState` and remove local-state sprawl

**Files:**
- Create: `backend/app/services/finding_runtime/query_state.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Modify: `backend/app/services/finding_runtime/session_store.py`
- Test: `backend/tests/finding_runtime/test_query_state.py`

- [ ] **Step 1: Write failing tests for serialized loop state**

Cover:
- turn count
- stop-hook active flag
- max-output-token recovery count
- transition persistence
- placeholder compact tracking

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement `QueryLoopState` plus session-store serialization helpers**
- [ ] **Step 4: Run tests to verify they pass**

### Task 3: Make every continue site rebuild a full state object

**Files:**
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Modify: `backend/app/services/finding_runtime/query_transitions.py`
- Test: `backend/tests/finding_runtime/test_query_transitions.py`

- [ ] **Step 1: Write failing tests asserting full-state rewrites on every continue**
- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Refactor continue branches so each branch produces a complete `QueryLoopState`**
- [ ] **Step 4: Run tests to verify they pass**

## Chunk 2: Align Single-Iteration Stage Ordering

### Task 4: Extract the restored per-turn pipeline into dedicated helpers

**Files:**
- Create: `backend/app/services/finding_runtime/query_context.py`
- Create: `backend/app/services/finding_runtime/query_messages.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Test: `backend/tests/finding_runtime/test_query_state.py`

- [ ] **Step 1: Write failing tests for per-turn stage ordering**

Cover the restored order:
- compact-boundary slicing
- tool-result budget placeholder
- history snip placeholder
- microcompact placeholder
- context-collapse projection placeholder
- proactive autocompact placeholder
- context injection
- message normalization

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Move preprocessing into ordered helper functions**
- [ ] **Step 4: Run tests to verify they pass**

### Task 5: Add context injection parity hooks

**Files:**
- Create: `backend/app/services/finding_runtime/query_context.py`
- Modify: `backend/app/services/finding_runtime/adapters/finding.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Test: `backend/tests/finding_runtime/test_query_state.py`

- [ ] **Step 1: Write failing tests for system-context and user-context injection**

Cover:
- base system prompt
- skill/route/memory context from adapter
- per-turn user-context prepend
- injection order relative to message normalization

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement explicit `append_system_context(...)` and `prepend_user_context(...)` helpers in Python**
- [ ] **Step 4: Run tests to verify they pass**

### Task 6: Add message normalization before provider calls

**Files:**
- Create: `backend/app/services/finding_runtime/query_messages.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Test: `backend/tests/finding_runtime/test_query_state.py`

- [ ] **Step 1: Write failing tests for message normalization**

Cover:
- stripping synthetic API error artifacts from model input
- collapsing unsupported message shapes
- stable assistant/tool replay normalization
- preserving tool-result/user-message semantics

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement normalization and apply it immediately before model invocation**
- [ ] **Step 4: Run tests to verify they pass**

## Chunk 3: API Calling And Tool Execution Parity

### Task 7: Upgrade model-calling phase from one-shot completion to restored-style classified response handling

**Files:**
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Modify: `backend/app/services/finding_runtime/bridge.py`
- Modify: `backend/app/services/finding_runtime/models.py`
- Test: `backend/tests/finding_runtime/test_bridge.py`

- [ ] **Step 1: Write failing tests for API response classification**

Cover:
- normal completion
- tool-use completion
- prompt-too-long classification
- media/image error classification
- max-output-tokens classification
- model-error classification

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Introduce an internal response envelope that can carry withheld recoverable errors**
- [ ] **Step 4: Run tests to verify they pass**

### Task 8: Preserve restored `next_turn` semantics across tool execution

**Files:**
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Modify: `backend/app/services/runtime_core/tool_runtime.py`
- Modify: `backend/app/services/finding_runtime/tooling.py`
- Test: `backend/tests/finding_runtime/test_query_transitions.py`

- [ ] **Step 1: Write failing tests for assistant + tool_use + tool_result assembly**

Cover:
- assistant output is appended before tool results
- tool results are normalized into the transcript for the next turn
- `next_turn` transition carries updated `turn_count`

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Refactor tool execution path to build the next state exactly once after tools complete**
- [ ] **Step 4: Run tests to verify they pass**

### Task 9: Add between-turn attachments and pending tool-use summary plumbing

**Files:**
- Create: `backend/app/services/finding_runtime/query_attachments.py`
- Modify: `backend/app/services/finding_runtime/memory.py`
- Modify: `backend/app/services/finding_runtime/skills.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Test: `backend/tests/finding_runtime/test_skills.py`

- [ ] **Step 1: Write failing tests for between-turn injected messages**

Cover:
- memory attachments
- skill-discovery attachments
- tool-use summary placeholder and later concrete attachment

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement attachment builders and merge them into next-turn state construction**
- [ ] **Step 4: Run tests to verify they pass**

## Chunk 4: Recovery And Degradation Parity

### Task 10: Add `max_output_tokens` escalation and recovery

**Files:**
- Create: `backend/app/services/finding_runtime/query_degradation.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Test: `backend/tests/finding_runtime/test_query_degradation.py`

- [ ] **Step 1: Write failing tests for `max_output_tokens_escalate` and `max_output_tokens_recovery`**
- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement token-limit escalation and bounded recovery count**
- [ ] **Step 4: Run tests to verify they pass**

### Task 11: Add placeholder branches for `collapse_drain_retry` and `reactive_compact_retry`

**Files:**
- Create: `backend/app/services/finding_runtime/query_degradation.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Test: `backend/tests/finding_runtime/test_query_degradation.py`

- [ ] **Step 1: Write failing tests that assert branch selection before implementation exists**

Cover:
- prompt-too-long plus pending collapse => `collapse_drain_retry`
- recoverable prompt/media failure => `reactive_compact_retry`
- checkpoint records `recovery_not_implemented` when the concrete subsystem is absent

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Add placeholder transition handlers with deterministic fallback behavior**
- [ ] **Step 4: Run tests to verify they pass**

### Task 12: Implement real context-collapse/reactive-compact/autocompact behavior

**Files:**
- Modify: `backend/app/services/finding_runtime/query_context.py`
- Modify: `backend/app/services/finding_runtime/query_degradation.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Test: `backend/tests/finding_runtime/test_query_degradation.py`

- [ ] **Step 1: Write failing tests for real compact/retry semantics**
- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement actual collapse drain, reactive compact, and proactive autocompact**
- [ ] **Step 4: Run tests to verify they pass**

## Chunk 5: Stop Hooks, Token Budget Continuation, And Final Termination Semantics

### Task 13: Add restored-style stop-hook handling

**Files:**
- Create: `backend/app/services/finding_runtime/query_stop_hooks.py`
- Modify: `backend/app/services/runtime_core/hook_runtime.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Test: `backend/tests/finding_runtime/test_query_stop_hooks.py`

- [ ] **Step 1: Write failing tests for stop-hook outcomes**

Cover:
- blocking correction errors => `stop_hook_blocking`
- prevent continuation => `stop_hook_prevented`
- hook-stopped during/after tool execution => `hook_stopped`

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement stop-hook evaluation and message reinjection**
- [ ] **Step 4: Run tests to verify they pass**

### Task 14: Add token-budget continuation instead of early completion

**Files:**
- Create: `backend/app/services/finding_runtime/query_token_budget.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Test: `backend/tests/finding_runtime/test_query_stop_hooks.py`

- [ ] **Step 1: Write failing tests for `token_budget_continuation`**
- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement budget policy plus continuation nudge message injection**
- [ ] **Step 4: Run tests to verify they pass**

### Task 15: Align terminal outcomes and bridge/finalizer interaction

**Files:**
- Modify: `backend/app/services/finding_runtime/runner.py`
- Modify: `backend/app/services/finding_runtime/bridge.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Test: `backend/tests/finding_runtime/test_bridge.py`

- [ ] **Step 1: Write failing tests for terminal reason propagation through bridge/runner**

Cover:
- `completed`
- `max_turns`
- `prompt_too_long`
- `model_error`
- `aborted_streaming`
- `aborted_tools`

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Make bridge/finalizer respect the richer terminal taxonomy without collapsing reasons into a generic completion**
- [ ] **Step 4: Run tests to verify they pass**

## Chunk 6: Final Parity Verification And Cutover

### Task 16: Build parity fixtures from restored scenarios

**Files:**
- Create: `backend/tests/finding_runtime/fixtures/query_parity/`
- Modify: `backend/tests/finding_runtime/test_query_transitions.py`
- Modify: `backend/tests/finding_runtime/test_query_degradation.py`

- [ ] **Step 1: Add restored-inspired fixtures for each continue and terminal branch**
- [ ] **Step 2: Run tests to verify current runtime still misses some fixtures**
- [ ] **Step 3: Close remaining parity gaps until all fixtures pass**
- [ ] **Step 4: Run the full finding-runtime suite and verify it passes**

### Task 17: Remove temporary fallbacks and tighten feature flags

**Files:**
- Modify: `backend/app/services/finding_runtime/query_degradation.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Modify: `backend/app/services/finding_runtime/adapters/finding.py`
- Test: `backend/tests/finding_runtime/test_query_degradation.py`

- [ ] **Step 1: Inventory temporary `recovery_not_implemented` branches**
- [ ] **Step 2: Remove no-longer-needed placeholders behind explicit feature checks**
- [ ] **Step 3: Update docs/comments/checkpoint payloads to reflect final semantics**
- [ ] **Step 4: Run tests to verify final parity remains intact**

## Phase Summary

### Phase 1: State machine skeleton and reason parity

Deliver:
- expanded enums
- explicit state object
- explicit continue transitions
- richer checkpoints

Can land before:
- compaction implementation
- stop-hook implementation
- token-budget implementation

### Phase 2: Single-iteration pipeline parity

Deliver:
- ordered preprocessing hooks
- context injection helpers
- message normalization

Can use no-op placeholders for:
- history snip
- microcompact
- autocompact

### Phase 3: API and tool-execution parity

Deliver:
- classified model response envelope
- next-turn assembly parity
- between-turn attachment scaffolding

### Phase 4: Recovery and degradation parity

Deliver:
- max-output-token escalation/recovery
- placeholder then real `collapse_drain_retry`
- placeholder then real `reactive_compact_retry`

### Phase 5: Stop hooks and continuation-policy parity

Deliver:
- stop-hook blocking/prevented/hook-stopped semantics
- token-budget continuation
- richer terminal propagation through runner/bridge

### Phase 6: Final parity cleanup

Deliver:
- restored-inspired parity fixtures
- placeholder removal
- final cutover confidence

## Verification Milestones

- `cd backend; $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/finding_runtime/test_query_state.py tests/finding_runtime/test_query_transitions.py -q`
- `cd backend; $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/finding_runtime/test_query_degradation.py tests/finding_runtime/test_query_stop_hooks.py -q`
- `cd backend; $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/finding_runtime/test_bridge.py tests/finding_runtime/test_skills.py -q`
- `cd backend; $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/runtime_core/test_hook_runtime.py tests/runtime_core/test_interaction_runtime.py -q`
- `cd backend; $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/agent/test_finding_v2.py -q`

## Recommended Execution Order

1. Land Phase 1 first so the runtime has a stable explicit state machine and reason taxonomy.
2. Land Phase 2 next so per-turn ordering becomes deterministic before adding recovery complexity.
3. Land Phase 3 next so tool execution and next-turn assembly follow the right structure.
4. Land Phase 4 next so recovery branches exist even if some implementations remain temporary placeholders.
5. Land Phase 5 after that so stop hooks and token-budget continuation sit on top of the stabilized loop.
6. Finish with Phase 6 to remove placeholders and verify parity against restored-style fixtures.

## Immediate First Slice

- Phase 1A: expand `RuntimeStopReason`, add continue-reason enum, and persist `transition` in checkpoints
- Phase 1B: introduce `QueryLoopState` and move turn variables out of `query_loop.py`
- Phase 2A: extract per-turn pipeline helpers with no-op placeholder implementations
- Phase 3A: make tool execution rebuild next-turn state exactly once via `next_turn`
- Phase 4A: add `max_output_tokens_*` handling and placeholder `reactive_compact_retry` / `collapse_drain_retry`

Plan complete and saved to `docs/superpowers/plans/2026-04-16-finding-runtime-query-loop-alignment.md`. Ready to execute?

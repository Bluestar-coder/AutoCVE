# Finding Runtime Remaining Alignment Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining behavioral gaps between AuditAI finding runtime and `restored-from-cli-map-v3/src/query.ts`, with phased delivery that first removes the highest-signal placeholder surfaces and then lands the more expensive compact/hook/runtime-core subsystems.

**Architecture:** Keep the current explicit Python state machine (`QueryLoopState`, continue reasons, terminal reasons) and progressively replace placeholder helpers with real subsystems. Start with low-risk loop-adjacent gaps that are already represented in state and checkpoints, then move inward toward token-budget policy, stop hooks, overflow recovery, and final runtime-core convergence.

**Tech Stack:** Python 3.12, pytest, SQLAlchemy audit-session persistence, finding runtime services, runtime_core services.

---

## Current Gap Summary

The runtime loop now has restored-style state vocabulary and most branch taxonomy, but the following areas are still materially behind restored:

- `query_attachments.py` is still placeholder-only.
  - `build_between_turn_attachments()` returns `[]`
  - `start_pending_tool_use_summary()` returns `None`
- `pending_tool_use_summary` is persisted in state but not yet consumed into the next turn as a real message.
- `normalize_messages_for_model()` only strips `system` role messages.
  - It does not merge adjacent user messages, drop empty synthetic noise, or sanitize provider-facing transcript structure the way restored does.
- `RuntimeLLMModelClient.complete()` accepts `max_output_tokens_override` but still drops it.
- `blocking_limit` exists in the enum only; runtime does not yet have a preflight blocking-limit path.
- Stop hooks are metadata-driven stubs, not a real runtime hook pipeline.
- Token-budget continuation is metadata-driven, not computed from actual budget consumption.
- `collapse_drain_retry` and `reactive_compact_retry` now rewrite messages, but they are still simplified approximations.
  - reactive compact currently piggybacks on proactive autocompact logic
  - collapse drain currently projects a staged summary, not a persisted collapse queue / drain log
- Query-context preprocessing is now functional but still uses simple char-based heuristics instead of restored¡¯s token-aware subsystems.
- Finalizer behavior is closer to restored, but full cutover still depends on the gaps above.

## Why The First Phase Should Be Attachments + Tool Summary + Message Normalization

This is the best first slice because it is:

- already represented in the runtime state shape
- still obviously placeholder in current code
- low-risk compared with overflow recovery and hook-runtime integration
- directly improves next-turn context quality without redesigning the loop
- an enabling step for later stop-hook / token-budget / finalizer parity

This phase also gives us a safer provider-facing transcript before we touch more complex token and overflow decisions.

## File Structure

### Existing files to extend first

- Modify: `backend/app/services/finding_runtime/query_attachments.py`
  - Replace placeholder helpers with real between-turn attachment builders and tool-summary payload generation.
- Modify: `backend/app/services/finding_runtime/query_loop.py`
  - Consume pending tool-use summaries on the next turn and wire in new attachment helpers.
- Modify: `backend/app/services/finding_runtime/query_messages.py`
  - Upgrade message normalization for provider-safe transcript shaping.
- Modify: `backend/tests/finding_runtime/test_query_loop.py`
  - Add red/green coverage for next-turn summary injection and attachment persistence.
- Create: `backend/tests/finding_runtime/test_query_messages.py`
  - Cover normalization behavior independently.
- Create or Modify: `backend/tests/finding_runtime/test_query_attachments.py`
  - Cover attachment and pending-summary helper logic directly.

### Files for later phases

- Modify: `backend/app/services/finding_runtime/bridge.py`
- Modify: `backend/app/services/finding_runtime/query_degradation.py`
- Modify: `backend/app/services/finding_runtime/query_context.py`
- Modify: `backend/app/services/finding_runtime/query_stop_hooks.py`
- Modify: `backend/app/services/finding_runtime/query_token_budget.py`
- Modify: `backend/app/services/runtime_core/tool_runtime.py`
- Modify: `backend/app/services/runtime_core/interaction_runtime.py`
- Modify: `backend/app/services/runtime_core/session_state.py`

## Phase Plan

## Phase 1: Replace Empty Placeholder Surfaces

Deliver:
- real between-turn attachments
- real pending tool-use summary generation and next-turn consumption
- richer provider-facing message normalization

### Task 1: Implement between-turn attachments and pending tool-use summary

**Files:**
- Modify: `backend/app/services/finding_runtime/query_attachments.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Test: `backend/tests/finding_runtime/test_query_loop.py`
- Create: `backend/tests/finding_runtime/test_query_attachments.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- tool turn writes a non-empty structured pending tool-use summary
- next turn injects the pending summary as a synthetic message exactly once
- between-turn attachment helper emits a concise tool attachment message

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend; $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/finding_runtime/test_query_loop.py tests/finding_runtime/test_query_attachments.py -q`
Expected: FAIL because helpers are still placeholders and next-turn summary injection does not exist.

- [ ] **Step 3: Implement the minimal runtime helpers**

Implement:
- compact tool execution attachment message builder
- pending summary payload with tool names, status, and concise output excerpts
- next-turn summary message materialization and one-shot consumption

- [ ] **Step 4: Run tests to verify they pass**

### Task 2: Upgrade provider-facing message normalization

**Files:**
- Modify: `backend/app/services/finding_runtime/query_messages.py`
- Test: `backend/tests/finding_runtime/test_query_messages.py`
- Modify: `backend/tests/finding_runtime/test_query_loop.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- system messages are removed
- empty synthetic messages are dropped
- adjacent plain user messages are merged without collapsing structured tool or named synthetic messages

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement minimal normalization behavior**
- [ ] **Step 4: Run tests to verify they pass**

## Phase 2: Provider Controls And Blocking-Limit Preflight

Deliver:
- real `max_output_tokens_override` propagation
- real `blocking_limit` terminal path

### Focus
- plumb `max_output_tokens_override` through bridge/provider request construction
- add preflight token/blocking-limit decision before model call
- keep current char-based heuristic first, then swap to token-aware accounting later if needed

## Phase 3: Replace Metadata Stubs With Real Runtime Policies

Deliver:
- computed token-budget continuation
- real stop-hook decision inputs instead of plain metadata toggles

### Focus
- move `query_token_budget.py` off hardcoded metadata flags
- enrich stop-hook evaluation with actual turn outcome and tool-result context
- define a stable hook payload contract before deeper runtime_core merge

## Phase 4: Land Dedicated Reactive Compact

Deliver:
- true reactive compact path for prompt-too-long and media-size recovery

### Focus
- stop relying on `run_proactive_autocompact()` as the reactive retry implementation
- support media stripping / media-aware retry behavior
- preserve single-shot retry guards

## Phase 5: Land Real Collapse Drain And Persisted Collapse State

Deliver:
- real staged collapse queue / drain semantics
- replayable collapsed context view instead of simple projection-only summaries

### Focus
- persist staged collapse work in runtime/session state
- support commit/drain/replay behavior across iterations and resumes
- keep `collapse_drain_retry` checkpoint semantics intact

## Phase 6: Runtime-Core Convergence And Final Cutover

Deliver:
- shared hook/runtime alignment
- restored-style parity verification fixtures
- final cleanup of remaining approximations

### Focus
- converge stop hooks with `runtime_core`
- expand parity fixtures to integration-style restored scenarios
- remove leftover ¡°deferred approximation¡± notes where fully replaced

## Recommended Execution Order

1. Phase 1 first: remove the most obvious placeholder helpers and improve next-turn context quality.
2. Phase 2 next: make truncation and blocking behavior real at the provider boundary.
3. Phase 3 next: replace metadata-only policies with computed loop decisions.
4. Phase 4 after that: land real reactive compact.
5. Phase 5 after reactive compact: land real collapse drain.
6. Phase 6 last: runtime-core convergence, parity fixtures, cutover cleanup.

## Immediate First Slice To Execute Now

- Phase 1 / Task 1: implement between-turn attachments and pending tool-use summary
- Phase 1 / Task 2: upgrade provider-facing message normalization

## Verification Milestones

- `cd backend; $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/finding_runtime/test_query_loop.py tests/finding_runtime/test_query_attachments.py tests/finding_runtime/test_query_messages.py -q`
- `cd backend; $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/finding_runtime -q`

Plan complete and saved to `docs/superpowers/plans/2026-04-17-finding-runtime-remaining-alignment-plan.md`. Execution starts with Phase 1.

# Finding Runtime Compaction Alignment Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align AuditAI finding runtime's context compaction, microcompaction, PTL recovery, and post-compact message reconstruction with restored `compact.ts` / `autoCompact.ts` / `prompt.ts` so the ReAct loop behaves like restored under context pressure.

**Architecture:** Move AuditAI from its current character-budgeted inline summarization helpers to a dedicated compaction subsystem with explicit threshold computation, proactive auto-compact orchestration, PTL retry, prompt families, compaction result assembly, and failure circuit breaking. Preserve the existing `QueryLoopState` / `QueryLoop` state-machine shell, but replace the current simplified `query_context.py` / `query_degradation.py` logic with a restored-style compaction service boundary.

**Tech Stack:** Python, existing `finding_runtime` state machine, `runtime_core` session state/checkpoints, current model client bridge, pytest.

---

## Current State Summary

### Restored implements a full compaction subsystem

The restored branch splits compaction into at least three dedicated layers:

- `src/services/compact/autoCompact.ts`
  Owns proactive autocompact threshold math, warning/error/blocking thresholds, recursion guards, feature gates, session-memory-first path, and consecutive-failure circuit breaking.
- `src/services/compact/compact.ts`
  Owns full compaction execution, PTL retry, summary prompt invocation, post-compact attachment reconstruction, hooks, telemetry, cache-sharing fork path, and final `CompactionResult` assembly.
- `src/services/compact/prompt.ts`
  Owns three different compaction prompt families plus `NO_TOOLS_PREAMBLE` / `NO_TOOLS_TRAILER` wrappers.

### AuditAI currently has only a partial inline equivalent

Current AuditAI compaction logic is spread across:

- `backend/app/services/finding_runtime/query_context.py`
- `backend/app/services/finding_runtime/query_degradation.py`
- `backend/app/services/finding_runtime/query_state.py`
- `backend/app/services/finding_runtime/query_loop.py`

This implementation has useful parity scaffolding, but it is still a simplified Python-native approximation, not a feature-complete restored-style compaction subsystem.

---

## Detailed Gap Analysis

### 1. Threshold computation and trigger timing

### Restored

`autoCompact.ts` computes compaction thresholds from model context size, not from raw message size alone.

Key restored behavior:

- `getEffectiveContextWindowSize(model)`: context window minus reserved summary output budget (`MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000`), with optional env override `CLAUDE_CODE_AUTO_COMPACT_WINDOW`.
- `getAutoCompactThreshold(model)`: `effectiveContextWindow - AUTOCOMPACT_BUFFER_TOKENS`, where `AUTOCOMPACT_BUFFER_TOKENS = 13_000`.
- `calculateTokenWarningState(...)` derives warning/error/auto-compact/blocking states.
- `shouldAutoCompact(...)` uses token estimation plus recursion guards, feature gates, snip delta compensation, reactive-only suppression, context-collapse suppression, and query-source suppression.

### AuditAI now

AuditAI has no restored-equivalent threshold computation function.

Current behavior is much simpler:

- `run_proactive_autocompact(...)` in `query_context.py` triggers only if pipeline config contains `autocompact.max_chars` and current summed content chars exceed that value.
- `evaluate_blocking_limit(...)` is also character-count based, using `blocking_limit.max_chars`.
- There is no model-aware context-window calculation.
- There is no reserved summary output budget.
- There is no warning/error/auto-compact/blocking threshold family.
- There is no `shouldAutoCompact(...)`-style central gate.
- There is no recursion guard based on query source.
- There is no snip-aware token compensation.
- There is no feature-gated suppression when context-collapse owns headroom management.

### Gap assessment

This is a major gap. AuditAI currently has only static char ceilings, while restored uses a model-aware threshold policy.

---

### 2. Auto-compact tracking and circuit breaker

### Restored

`AutoCompactTrackingState` in `autoCompact.ts` carries structured proactive-compaction state:

- `compacted`
- `turnCounter`
- `turnId`
- `consecutiveFailures?`

`autoCompactIfNeeded(...)` enforces a circuit breaker:

- `MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3`
- consecutive failures increment when compacting fails
- successful compaction resets the counter to `0`
- once the breaker trips, future proactive attempts stop for the session

### AuditAI now

AuditAI stores `auto_compact_tracking` as a free-form dict on `QueryLoopState`.

It currently records fields like:

- `compacted`
- `summary_message_name`
- `compacted_messages`
- `boundary_name`
- `media_stripped_count`
- `pending_collapse`
- `last_recovery_strategy`
- `last_recovery_status`
- `reactive_compact_attempted`

But it does not implement restored-style proactive-failure protection:

- no canonical `consecutiveFailures`
- no breaker threshold
- no skip-on-trip behavior
- no `turnCounter` / `turnId` recompaction tracking analogous to restored
- no `autoCompactIfNeeded(...)` entrypoint that owns this state

### Gap assessment

The state bag exists, but the restored circuit-breaker semantics are still missing.

---

### 3. Prompt families and no-tools wrappers

### Restored

`prompt.ts` defines three distinct summary prompt families:

- `BASE_COMPACT_PROMPT`
- `PARTIAL_COMPACT_PROMPT`
- `PARTIAL_COMPACT_UP_TO_PROMPT`

It also wraps prompt content with:

- `NO_TOOLS_PREAMBLE`
- `NO_TOOLS_TRAILER`

### AuditAI now

AuditAI has no dedicated compaction prompt module.

Current summaries are generated inline via helper functions in `query_context.py`:

- `_build_autocompact_summary(...)`
- `_build_collapse_summary(...)`
- `_build_reactive_compact_summary(...)`

AuditAI currently lacks dedicated prompt families, no-tools wrappers, restored-style `<analysis>/<summary>` formatting, and custom instruction merging into compaction prompt generation.

### Gap assessment

This is a very large gap. AuditAI is not yet using prompt-driven compaction for proactive compaction; it is using inline heuristic summary builders.

---

### 4. Compaction execution flow and `CompactionResult`

### Restored

`compactConversation()` in `compact.ts` is a full orchestration pipeline. It handles preconditions, pre-compact hooks, prompt-cache-sharing fork path + fallback streaming path, PTL retry, assistant-text extraction, state rebuild, post-compact attachment regeneration, session-start hooks, boundary creation, summary message creation, telemetry, post-compact hooks, and structured `CompactionResult` return.

`buildPostCompactMessages()` canonicalizes final ordering:

- boundary marker
- summary messages
- preserved messages
- attachments
- hook results

### AuditAI now

AuditAI has no dedicated compaction result type or compaction execution service.

Current behavior is distributed across `run_proactive_autocompact(...)`, `run_reactive_compact(...)`, `apply_context_collapse_if_needed(...)`, `recover_context_collapse_from_overflow(...)`, `handle_recoverable_response(...)`, and `QueryLoop.run_turn(...)`.

Current compaction output is just a rewritten message list plus tracking state. It does not produce a restored-style `CompactionResult` object and does not have a canonical `buildPostCompactMessages()` step.

AuditAI currently lacks:

- a dedicated compaction service boundary
- structured compaction result object
- canonical post-compact message assembly ordering
- preserved `messagesToKeep` semantics as a first-class concept
- transcript relink / preserved-segment metadata
- restored post-compact attachment regeneration
- pre/post compact hook execution
- prompt-cache-sharing fork path and fallback logic
- compaction usage telemetry parity
- transcript-path summary message enrichment

### Gap assessment

This is the largest architecture gap. AuditAI has a set of compaction transforms, but not restored's compaction subsystem.

---

### 5. PTL retry strategy

### Restored

`truncateHeadForPTLRetry()` is a dedicated fallback when the compaction request itself hits prompt-too-long:

- strips prior retry marker before regrouping
- groups messages by API round
- parses `tokenGap` from the PTL error when possible
- otherwise falls back to dropping 20% of groups
- ensures at least one summarize-set group remains
- prepends a synthetic user retry marker if dropping the first group would make the sequence assistant-first

This logic is used inside `compactConversation()`'s retry loop with `MAX_PTL_RETRIES = 3`.

### AuditAI now

AuditAI has no `truncateHeadForPTLRetry()` equivalent.

When compaction-related overflow occurs:

- proactive autocompact is a local transform and never calls the model, so it has no PTL retry loop
- `prompt_too_long` from the main model call is handled in `handle_recoverable_response(...)`
- the available recovery paths are `collapse_drain_retry` then `reactive_compact_retry`
- if those fail, the loop terminates with `PROMPT_TOO_LONG`

AuditAI does not currently support compaction-request PTL retries, token-gap-aware drop-oldest retry logic, API-round grouping during retry trimming, or synthetic retry marker insertion.

---
### 6. `autoCompactIfNeeded()` orchestration entrypoint

### Restored

`autoCompactIfNeeded()` in `autoCompact.ts` is the proactive entrypoint used by the query loop. It owns:

- env disable checks
- circuit breaker checks
- `shouldAutoCompact(...)`
- recompaction info construction
- session-memory-first optimization path
- fallback to `compactConversation(...)`
- failure counting and reset
- post-compact cleanup hooks and state reset

### AuditAI now

AuditAI has no single equivalent proactive orchestrator.

Instead, `QueryLoop.run_turn()` directly runs a preprocessing chain:

- `get_messages_after_compact_boundary`
- `apply_tool_result_budget`
- `apply_history_snip`
- `apply_microcompact`
- `apply_context_collapse_if_needed`
- `run_proactive_autocompact`
- `evaluate_blocking_limit`

This means:

- compaction decision logic is implicit and inline
- proactive compaction is not a distinct stateful operation
- there is no session-memory-first path
- there is no central failure accounting
- there is no restored-like recompression telemetry

### Gap assessment

This is a major control-plane gap. AuditAI currently has stages, but not restored's orchestrator.

---

### 7. Other restored compaction mechanisms AuditAI still lacks

Beyond the six items above, restored also has these compaction-related behaviors that AuditAI still does not fully implement.

#### 7.1 Prompt-cache-sharing compaction path

Restored can try a cache-sharing forked-agent compaction path before falling back to regular streaming. AuditAI has no equivalent.

#### 7.2 Session-memory-first compaction

Restored `autoCompactIfNeeded()` first tries `trySessionMemoryCompaction(...)`. AuditAI has no session-memory compaction path in finding runtime.

#### 7.3 Post-compact attachment regeneration

Restored rebuilds:

- post-compact file attachments
- async agent attachments
- plan attachment
- plan mode attachment
- invoked skills attachment
- deferred tools delta attachment
- agent listing delta attachment
- MCP instructions delta attachment

AuditAI currently does none of this during compaction.

#### 7.4 Pre/post compact hooks

Restored executes:

- `executePreCompactHooks(...)`
- `processSessionStartHooks('compact', ...)`
- `executePostCompactHooks(...)`

AuditAI currently has no compaction hook pipeline.

#### 7.5 Boundary annotation / preserved segment relinking

Restored carries preserved segment metadata on the compact boundary. AuditAI currently inserts summary/boundary messages, but without restored-style relink metadata.

#### 7.6 Formatting and transcript usability

Restored uses `formatCompactSummary(...)` and `getCompactUserSummaryMessage(...)` to strip `<analysis>`, rewrite `<summary>`, include transcript path hints, and preserve continuation semantics. AuditAI currently emits terse synthetic summary lines only.

#### 7.7 Token-based micro decisions

Restored uses token estimation and API usage metrics throughout. AuditAI uses character counts almost everywhere in compaction logic.

---

## Detailed Current-vs-Restored Mapping

### What AuditAI already has

These are real building blocks already present and worth preserving:

- compact boundary detection after prior summaries
- tool result budgeting
- history snip stage
- microcompact stage
- context collapse staging / commit / projection shell
- reactive compact shell
- blocking-limit terminal reason
- `prompt_too_long` recovery branches in the main loop
- persisted `QueryLoopState` fields for compaction-related state

### What is only partially aligned

- proactive autocompact exists, but only as a local char-budget summary transform
- reactive compact exists, but it is still not restored's model-driven partial compact system
- context collapse exists, but not as a unified headroom manager coordinated by restored threshold policy
- compaction tracking exists, but not as restored's breaker-aware tracking state

### What is still fundamentally missing

- token-aware threshold controller
- dedicated compaction prompt families
- `autoCompactIfNeeded()` orchestration service
- `compactConversation()` service
- `CompactionResult` + `buildPostCompactMessages()`
- PTL retry during compaction request
- post-compact hooks and attachment reconstruction
- session-memory-first compaction
- prompt-cache-sharing compaction path

---

## Migration Strategy

The target is full behavioral alignment, but the migration should not start by ripping out current `query_context.py`. The safer path is:

1. Introduce restored-style control-plane types and service boundaries first.
2. Route the current simplified transforms through those boundaries.
3. Replace simplified implementations with restored-style implementations phase by phase.
4. Only after parity coverage exists, remove the old inline shortcuts.

---

## Files To Create Or Restructure

**Create:**
- `backend/app/services/finding_runtime/compaction/__init__.py`
- `backend/app/services/finding_runtime/compaction/auto_compact.py`
- `backend/app/services/finding_runtime/compaction/compact.py`
- `backend/app/services/finding_runtime/compaction/prompts.py`
- `backend/app/services/finding_runtime/compaction/models.py`
- `backend/app/services/finding_runtime/compaction/post_compact.py`
- `backend/tests/finding_runtime/test_auto_compact_runtime.py`
- `backend/tests/finding_runtime/test_compact_runtime.py`
- `backend/tests/finding_runtime/test_compact_prompts.py`

**Modify:**
- `backend/app/services/finding_runtime/query_context.py`
- `backend/app/services/finding_runtime/query_degradation.py`
- `backend/app/services/finding_runtime/query_loop.py`
- `backend/app/services/finding_runtime/query_state.py`
- `backend/app/services/finding_runtime/models.py`
- `backend/app/services/finding_runtime/bridge.py`
- `backend/tests/finding_runtime/test_query_context.py`
- `backend/tests/finding_runtime/test_query_degradation.py`
- `backend/tests/finding_runtime/test_query_loop.py`

---

## Phase Plan

## Chunk 1: Control Plane Parity

### Task 1: Introduce restored-style compaction models and prompt module

**Files:**
- Create: `backend/app/services/finding_runtime/compaction/models.py`
- Create: `backend/app/services/finding_runtime/compaction/prompts.py`
- Test: `backend/tests/finding_runtime/test_compact_prompts.py`

- [ ] **Step 1: Write failing prompt tests**

Add tests for:
- `NO_TOOLS_PREAMBLE` present on all compact prompts
- `NO_TOOLS_TRAILER` present on all compact prompts
- base compact prompt generation
- partial compact prompt generation
- partial-up-to compact prompt generation
- custom instruction merge behavior

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/finding_runtime/test_compact_prompts.py -q`
Expected: FAIL because the new prompt module does not exist yet.

- [ ] **Step 3: Implement prompt module and compaction models**

Add:
- `CompactionPromptKind`
- `CompactionResult`
- `AutoCompactTrackingState`
- `RecompactionInfo`
- `get_compact_prompt(...)`
- `get_partial_compact_prompt(...)`
- `format_compact_summary(...)`
- `get_compact_user_summary_message(...)`

- [ ] **Step 4: Run prompt tests to verify they pass**

Run: `pytest tests/finding_runtime/test_compact_prompts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/finding_runtime/compaction/models.py backend/app/services/finding_runtime/compaction/prompts.py backend/tests/finding_runtime/test_compact_prompts.py
git commit -m "feat: add restored-style compaction prompts and models"
```
### Task 2: Add restored-style threshold controller

**Files:**
- Create: `backend/app/services/finding_runtime/compaction/auto_compact.py`
- Modify: `backend/app/services/finding_runtime/query_state.py`
- Test: `backend/tests/finding_runtime/test_auto_compact_runtime.py`

- [ ] **Step 1: Write failing threshold tests**

Cover:
- effective context window calculation
- auto compact threshold calculation
- warning/error/blocking threshold calculation
- disable gates
- circuit breaker skip behavior

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/finding_runtime/test_auto_compact_runtime.py -q`
Expected: FAIL because the new controller does not exist.

- [ ] **Step 3: Implement threshold and circuit-breaker logic**

Add:
- `get_effective_context_window_size(...)`
- `get_auto_compact_threshold(...)`
- `calculate_token_warning_state(...)`
- `should_auto_compact(...)`
- breaker-aware `AutoCompactTrackingState`

Update `QueryLoopState` to stop using a free-form dict for proactive-tracking-only fields.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/finding_runtime/test_auto_compact_runtime.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/finding_runtime/compaction/auto_compact.py backend/app/services/finding_runtime/query_state.py backend/tests/finding_runtime/test_auto_compact_runtime.py
git commit -m "feat: add restored-style auto compact threshold controller"
```

## Chunk 2: Compaction Execution Parity

### Task 3: Introduce `compact_conversation()` and `build_post_compact_messages()`

**Files:**
- Create: `backend/app/services/finding_runtime/compaction/compact.py`
- Create: `backend/app/services/finding_runtime/compaction/post_compact.py`
- Test: `backend/tests/finding_runtime/test_compact_runtime.py`

- [ ] **Step 1: Write failing tests for compaction result assembly**

Cover:
- `CompactionResult` shape
- canonical post-compact ordering
- compact boundary + summary + preserved messages assembly
- preserved segment metadata

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/finding_runtime/test_compact_runtime.py -q`
Expected: FAIL because the new compact runtime does not exist.

- [ ] **Step 3: Implement minimal compaction runtime shell**

Implement:
- `build_post_compact_messages(...)`
- `annotate_boundary_with_preserved_segment(...)`
- `compact_conversation(...)` shell returning `CompactionResult`

Initially, this task may still call the existing Python summary builders internally, but must move assembly into the new service boundary.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/finding_runtime/test_compact_runtime.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/finding_runtime/compaction/compact.py backend/app/services/finding_runtime/compaction/post_compact.py backend/tests/finding_runtime/test_compact_runtime.py
git commit -m "feat: add compaction result assembly runtime"
```

### Task 4: Replace inline proactive autocompact with `auto_compact_if_needed()`

**Files:**
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Modify: `backend/app/services/finding_runtime/query_context.py`
- Modify: `backend/app/services/finding_runtime/compaction/auto_compact.py`
- Test: `backend/tests/finding_runtime/test_query_loop.py`

- [ ] **Step 1: Write failing integration test**

Cover:
- query loop calling `auto_compact_if_needed()` instead of inline `run_proactive_autocompact()`
- breaker state carried across turns
- threshold controller consulted before compacting

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/finding_runtime/test_query_loop.py -q`
Expected: FAIL on new assertions.

- [ ] **Step 3: Implement orchestration handoff**

Move proactive orchestration out of `query_context.py` and into `compaction/auto_compact.py`.
Keep `query_context.py` only for reusable transforms that still belong in the pre-model pipeline.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/finding_runtime/test_query_loop.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/finding_runtime/query_loop.py backend/app/services/finding_runtime/query_context.py backend/app/services/finding_runtime/compaction/auto_compact.py backend/tests/finding_runtime/test_query_loop.py
git commit -m "refactor: route proactive compaction through auto compact runtime"
```

## Chunk 3: Prompt-Driven Compaction and PTL Parity

### Task 5: Implement prompt-driven compaction summaries

**Files:**
- Modify: `backend/app/services/finding_runtime/compaction/compact.py`
- Modify: `backend/app/services/finding_runtime/bridge.py`
- Test: `backend/tests/finding_runtime/test_compact_runtime.py`

- [ ] **Step 1: Write failing tests for prompt-driven compaction calls**

Cover:
- compaction requests use compaction prompt module
- no-tools preamble/trailer are present in the actual model prompt
- compaction response is formatted with summary extraction

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/finding_runtime/test_compact_runtime.py -q`
Expected: FAIL on new prompt invocation assertions.

- [ ] **Step 3: Implement model-driven compaction path**

Replace inline `_build_autocompact_summary`-style generation for proactive/manual compaction with actual compaction-model requests.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/finding_runtime/test_compact_runtime.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/finding_runtime/compaction/compact.py backend/app/services/finding_runtime/bridge.py backend/tests/finding_runtime/test_compact_runtime.py
git commit -m "feat: use prompt-driven compaction summaries"
```
### Task 6: Add `truncate_head_for_ptl_retry()` and compaction PTL retry loop

**Files:**
- Modify: `backend/app/services/finding_runtime/compaction/compact.py`
- Test: `backend/tests/finding_runtime/test_compact_runtime.py`

- [ ] **Step 1: Write failing PTL retry tests**

Cover:
- retry marker stripping on subsequent attempts
- API-round grouping behavior
- token-gap-aware dropping
- 20% fallback dropping
- assistant-first repair with synthetic user retry marker

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/finding_runtime/test_compact_runtime.py -q`
Expected: FAIL on new PTL retry assertions.

- [ ] **Step 3: Implement PTL retry logic**

Port restored semantics into Python:
- `truncate_head_for_ptl_retry(...)`
- `MAX_PTL_RETRIES = 3`
- retry loop inside `compact_conversation(...)`

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/finding_runtime/test_compact_runtime.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/finding_runtime/compaction/compact.py backend/tests/finding_runtime/test_compact_runtime.py
git commit -m "feat: add compaction prompt-too-long retry logic"
```

## Chunk 4: Partial Compact and Reactive Compact Parity

### Task 7: Align reactive compact with restored partial compact prompt families

**Files:**
- Modify: `backend/app/services/finding_runtime/query_degradation.py`
- Modify: `backend/app/services/finding_runtime/compaction/compact.py`
- Modify: `backend/app/services/finding_runtime/compaction/prompts.py`
- Test: `backend/tests/finding_runtime/test_query_degradation.py`

- [ ] **Step 1: Write failing tests for partial compact directions**

Cover:
- `from` partial compact path
- `up_to` partial compact path
- preserved-tail behavior
- reactive media stripping combined with partial compact prompt selection

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/finding_runtime/test_query_degradation.py -q`
Expected: FAIL on new partial-compaction assertions.

- [ ] **Step 3: Implement restored-style partial compact execution**

Make reactive compact use partial compaction service semantics rather than ad hoc summary building.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/finding_runtime/test_query_degradation.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/finding_runtime/query_degradation.py backend/app/services/finding_runtime/compaction/compact.py backend/app/services/finding_runtime/compaction/prompts.py backend/tests/finding_runtime/test_query_degradation.py
git commit -m "feat: align reactive compact with partial compact prompt flows"
```

### Task 8: Reconcile context collapse ownership with auto-compact thresholds

**Files:**
- Modify: `backend/app/services/finding_runtime/compaction/auto_compact.py`
- Modify: `backend/app/services/finding_runtime/query_context.py`
- Test: `backend/tests/finding_runtime/test_query_context.py`

- [ ] **Step 1: Write failing tests for collapse/autocompact coordination**

Cover:
- proactive autocompact suppression when context collapse is the active headroom manager
- collapse-drain retry precedence before reactive compact
- no race between collapse staging and proactive compact

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/finding_runtime/test_query_context.py -q`
Expected: FAIL on new coordination assertions.

- [ ] **Step 3: Implement coordination policy**

Bring restored-style ownership rules into the Python runtime.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/finding_runtime/test_query_context.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/finding_runtime/compaction/auto_compact.py backend/app/services/finding_runtime/query_context.py backend/tests/finding_runtime/test_query_context.py
git commit -m "refactor: coordinate context collapse and auto compact thresholds"
```

## Chunk 5: Post-Compact Reconstruction Parity

### Task 9: Implement post-compact attachment and hook reconstruction

**Files:**
- Modify: `backend/app/services/finding_runtime/compaction/post_compact.py`
- Modify: `backend/app/services/finding_runtime/compaction/compact.py`
- Test: `backend/tests/finding_runtime/test_compact_runtime.py`

- [ ] **Step 1: Write failing tests for post-compact reconstruction**

Cover:
- file-state restoration attachment generation
- invoked-skill preservation attachment generation
- plan/mode/session attachments where applicable
- pre/post compact hooks integration
- final `build_post_compact_messages(...)` ordering remains stable

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/finding_runtime/test_compact_runtime.py -q`
Expected: FAIL on new reconstruction assertions.

- [ ] **Step 3: Implement post-compact rebuild pipeline**

Mirror restored ordering and reconstruction concepts as closely as current AuditAI architecture allows.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/finding_runtime/test_compact_runtime.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/finding_runtime/compaction/post_compact.py backend/app/services/finding_runtime/compaction/compact.py backend/tests/finding_runtime/test_compact_runtime.py
git commit -m "feat: rebuild post compact attachments and hooks"
```

## Chunk 6: Final Alignment and Cleanup

### Task 10: Remove obsolete inline summary builders and char-only shortcuts

**Files:**
- Modify: `backend/app/services/finding_runtime/query_context.py`
- Modify: `backend/app/services/finding_runtime/query_degradation.py`
- Modify: `backend/app/services/finding_runtime/query_loop.py`
- Test: `backend/tests/finding_runtime/*.py`

- [ ] **Step 1: Write failing cleanup regression tests if needed**

Add any missing regression assertions for:
- no legacy inline autocompact summary builder usage
- no char-only threshold gating in proactive compaction path
- no duplicated post-compact assembly paths

- [ ] **Step 2: Run targeted tests to verify failures**

Run targeted pytest commands for any new regressions.
Expected: FAIL where legacy code still leaks through.

- [ ] **Step 3: Remove obsolete paths**

Delete or reduce:
- `_build_autocompact_summary(...)` as proactive primary path
- inline proactive trigger logic in `query_loop.py`
- legacy-only tracking keys that duplicate typed compaction state

- [ ] **Step 4: Run full verification**

Run: `pytest tests/finding_runtime tests/runtime_core -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/finding_runtime/query_context.py backend/app/services/finding_runtime/query_degradation.py backend/app/services/finding_runtime/query_loop.py backend/tests/finding_runtime backend/tests/runtime_core
git commit -m "refactor: complete restored compaction alignment"
```

---

## Recommended Implementation Order

The first parts to implement should be:

1. restored-style prompt module and compaction models
2. threshold controller and breaker-aware `auto_compact_if_needed()` control plane
3. `CompactionResult` + `build_post_compact_messages()` service boundary

Reason:

- These three pieces define the API surface the rest of the runtime should program against.
- They let us stop growing the current ad hoc `query_context.py` helpers.
- They minimize rework when prompt-driven compaction and PTL retry are added later.

Only after that should we migrate:

- PTL retry
- partial compact / reactive compact parity
- post-compact attachment reconstruction
- final cleanup of char-only shortcuts

---

## Verification Commands

Use these as the migration proceeds:

- `cd backend && $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/finding_runtime/test_compact_prompts.py -q`
- `cd backend && $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/finding_runtime/test_auto_compact_runtime.py -q`
- `cd backend && $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/finding_runtime/test_compact_runtime.py -q`
- `cd backend && $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/finding_runtime/test_query_context.py tests/finding_runtime/test_query_degradation.py tests/finding_runtime/test_query_loop.py -q`
- `cd backend && $env:PYTHONPATH='.'; uv run --with pytest --with pytest-asyncio pytest tests/finding_runtime tests/runtime_core -q`

---

## Expected End State

When this plan is complete, AuditAI should match restored in these ways:

- proactive autocompact trigger uses model-aware threshold math, not only static char budgets
- breaker-aware autocompact retries stop after repeated failures
- compaction uses dedicated prompt families with no-tools wrappers
- compaction requests can retry on PTL by dropping oldest API-round groups
- proactive/manual/reactive compaction all return a structured `CompactionResult`
- post-compact messages are assembled in a canonical restored-style order
- partial compact and preserved-tail semantics behave like restored
- post-compact attachment and hook reconstruction is first-class
- the query loop calls one explicit compaction orchestration entrypoint rather than scattering compaction control across several inline helpers

Plan complete and saved to `docs/superpowers/plans/2026-04-17-finding-runtime-compaction-alignment-plan.md`. Ready to execute?

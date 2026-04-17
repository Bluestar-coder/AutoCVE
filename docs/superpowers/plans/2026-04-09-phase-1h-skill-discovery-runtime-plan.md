# Phase 1H: Skill Discovery Scheduling Alignment Plan

Date: 2026-04-09
Status: proposed
Worktree: runtime-alignment-gap-analysis

## Goal

Align AuditAI skill selection with the restored-from-cli-map-v3 discovery style runtime.
The target is to move from static route-plan-first skill recommendation to session-state-driven, evidence-aware skill discovery and invocation.

## Current State

AuditAI already has these pieces:
- per-agent bindings and install registry
- session-level invoked skill state
- explicit Skill invocation runtime
- progressive loading stages for body/references/examples/scripts
- hot-refresh on continue_session for finding runtime
- allowed_tools and hooks connected into the shared tool runtime

But the actual selection strategy is still mostly static:
- bindings define visible skills
- keyword/config matching produces matched skills
- route_plan chooses primary_skill / secondary_skills / deferred_skills
- runtime starts from that static ordering

This is still a routing model, not a discovery scheduler.

## Restored-Style Target

Bindings should only define visibility and hard constraints.
They should not directly decide the one skill the model should use first.

Actual skill choice should happen dynamically during the session based on:
- current agent type
- current task and latest user request
- current project profile and recon payload
- touched_paths and recent tool results
- active candidate or current audit objective
- already invoked skills and current loading stage
- frontmatter constraints such as agent/context/disable-model-invocation

The scheduler should continuously answer:
- which skills are currently visible
- which skills are currently relevant
- which skill should be opened next
- how deep that skill should be loaded
- whether a previously invoked skill should be revisited or expanded

## Proposed Runtime Shape

### 1. Visibility Layer

Keep bindings as the visibility gate.
A skill is only eligible if:
- it is enabled for the current agent
- frontmatter agent constraints allow this agent
- the skill is active

Bindings still carry:
- enabled
- sort_order
- always_include
- match_keywords
- match_config

But sort_order becomes only a tie-breaker, not the main selector.

### 2. Discovery Candidate Layer

Add a shared discovery scorer, for example:
- backend/app/services/runtime_core/skill_discovery.py

It should evaluate every visible skill and compute:
- visibility_reason
- relevance_score
- trigger_reasons
- suggested_stage: body/references/examples/scripts
- freshness: unseen / seen-body / seen-references / saturated
- invocation_mode: suggest / auto-expand / wait

Inputs should include:
- session runtime state
- latest user message
- recon payload
- current touched paths
- recent tool results
- current active candidate metadata
- skill frontmatter and binding metadata

### 3. Session Discovery Memory

Extend SessionRuntimeState metadata with discovery state:
- discovery.current_candidates[agent]
- discovery.last_ranked_skills[agent]
- discovery.last_selected_skill[agent]
- discovery.suppressed_skills[agent]
- discovery.auto_invoked_skills[agent]
- discovery.reason_history[agent]

This is separate from invoked_skills.
Invoked state answers what happened.
Discovery state answers why a skill is or is not being considered now.

### 4. Route Plan Downgrade

Keep route_plan, but change its role.
It becomes only a cold-start shortlist generator.

New responsibilities:
- provide initial candidate ordering when the session starts
- provide startup hint text for the model
- never act as the final authority once runtime evidence exists

After the first runtime turn, actual selection should come from discovery state.

### 5. Discovery-Aware Skill Invocation

SkillInvocationRuntime should gain two modes:
- explicit invocation: model/user/runtime names a specific skill
- discovery invocation: runtime selects the best next skill based on ranked candidates

A new method shape could be:
- discover_next_skill(...)
- invoke_discovered_skill(...)

The runtime should:
- prefer unseen but high-relevance skills
- revisit a previously invoked skill only if there is a reason to deepen from body to references/examples/scripts
- avoid repeatedly reopening saturated skills

### 6. Progressive Loading Rules

Recommended progressive loading policy:
- first sighting: load body only
- if body mentions relevant references or if touched_paths intersect frontmatter paths, expand to references
- if the model is trying to perform a concrete workflow, expand examples
- only expand scripts when the agent actually needs execution-oriented guidance

This should be stateful.
If a skill is already at references stage, do not reload body as if it is new.

### 7. Prompt Contract

Prompting should change from:
- here is your primary skill, then maybe secondary skills

to:
- here are currently discoverable skills
- these are the strongest candidates right now
- if your task shifts, re-check the skill catalog before forcing a stale skill

Important:
Mentioning a skill in the user prompt should raise its relevance score.
It should not blindly force loading unless policy says it must.

## Selection Algorithm After Phase 1H

### Step 1: Build visible skill set

Start from agent bindings.
Filter out disabled or agent-incompatible skills.

### Step 2: Score each visible skill

Score components:
- direct user mention score
- current task semantic score
- recon/project-profile score
- touched_paths / frontmatter paths overlap score
- agent affinity score
- recency penalty for already-saturated skills
- bonus if the skill was previously invoked and remains relevant
- penalty if the skill was recently rejected or proved unhelpful

### Step 3: Rank and classify

Each candidate becomes one of:
- immediate candidate
- background candidate
- dormant candidate
- suppressed candidate

### Step 4: Decide next action

If the top immediate candidate is unseen, open body.
If already seen and task specificity increased, expand to references/examples/scripts.
If no candidate crosses threshold, do not force a skill load.

### Step 5: Persist reasoning

Write the ranking and reasons into session discovery metadata.
This gives us traceability and prevents oscillation.

## Concrete Behavior Answers

### If the prompt says: use code audit for code review

Yes, this should help.
After Phase 1H, an explicit user mention like code audit should heavily increase that skill's relevance score.

But it should not be treated as a blind hard force by default.
Recommended behavior:
- explicit mention raises the skill to the top candidate list
- if the skill is visible and invocable, runtime should auto-open its body or strongly recommend it immediately
- if policy wants strict behavior, we can add a force flag for direct skill mentions later

So the expected answer is:
- useful: yes
- guaranteed hard force load: not always, unless we add a strict-force policy
- practical effect: very likely selected first if it is visible for that agent

### If later an AI-component audit skill is added

Yes, it should be auto-discovered when the project or recon context shows AI relevance.

Examples of triggers:
- project languages/frameworks mention langchain, openai, transformers, llamaindex, rag, mcp, agent, tool calling
- recon summary or touched files indicate model serving, prompt orchestration, vector search, tool execution, sandboxing, chat pipelines
- frontmatter tags/match_config/path rules align with AI-related code

In that case the discovery scorer should promote the AI audit skill without needing the user to name it.
This is exactly the kind of behavior Phase 1H should add.

### If the user asks in-session to use a report-writing skill

Yes, this should work, provided three conditions hold:
- the skill is visible to that agent or the current orchestrator/runtime can invoke it
- frontmatter allows user invocation
- the skill is semantically relevant to the current subtask

Recommended runtime behavior:
- the direct user request strongly boosts the report skill score
- runtime invokes the skill body immediately
- if the skill needs examples/templates, expand to references/examples on demand

So in practice: yes, this should succeed after Phase 1H, assuming binding/frontmatter permit it.

## Implementation Plan

### Phase 1H-A
- add runtime_core skill discovery scorer
- persist ranked candidates and selection reasons in session state
- downgrade route_plan to startup shortlist only

### Phase 1H-B
- connect discovery scoring to SkillInvocationRuntime
- add discover_next_skill and auto-expand stage policy
- prevent repeated reopening of saturated skills

### Phase 1H-C
- update finding runtime prompts to expose discoverable skill candidates instead of a static primary/secondary contract
- preserve explicit direct skill invocation support

### Phase 1H-D
- add tests for direct mention, AI-context auto-selection, report-skill invocation, and repeat-load suppression

## Acceptance Criteria

- A directly named skill rises to the top of discovery selection for the current agent.
- A newly added AI audit skill is automatically selected when the project context indicates AI-specific code.
- A report-writing skill can be invoked mid-session from user instruction, with correct frontmatter checks.
- Already-saturated skills are not repeatedly reloaded without new evidence.
- Route plan is no longer the final selection authority after session startup.

## Recommendation

Do Phase 1H before entering Phase 2.
Otherwise Phase 2 will inherit a static skill-routing model and the later task orchestration work will be built on a weaker skill substrate.
# BrowserAgentV2 End-to-End System Specification

**Status:** target architecture for implementation planning. Individual choices marked `GATE` still require an experiment before freeze.

## 0. Product definition

BrowserAgentV2 is a local-first browser automation system that accepts broad natural-language goals, operates a real browser through a constrained deterministic runtime, persists task state and evidence, pauses safely for human intervention, and can later expand into long research and connector-backed workflows.

It is **not** a collection of hard-coded website scripts and it is **not** an LLM with unrestricted browser/computer access.

## 1. Architectural invariants

1. There is one authoritative `TaskController` state machine.
2. The model never directly owns a Playwright object, browser handle, shell, or arbitrary JS evaluator.
3. Every model-selected target is observation-scoped.
4. A state-changing action is persisted as intent before execution.
5. Browser execution success is distinct from task/postcondition success.
6. State-changing actions are never generically retried after ambiguous failure.
7. Web content is untrusted data, never authority.
8. Full traces are persisted but not automatically copied into model context.
9. User authentication/challenges are handled through explicit handoff states.
10. A capability is not accepted until deterministic tests cover its main failure classes.

---

# 2. Top-level runtime

```text
┌─────────────────────────────────────────────────────────────────┐
│ User / UI                                                       │
│  goal, optional URLs/files, confirmations, human handoff        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────────┐
│ TaskService                                                     │
│ create/resume/cancel/status                                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────────┐
│ TaskController  (single authoritative state machine)            │
│                                                                 │
│  PlanState ── ContextBuilder ── ModelAdapter                     │
│     │              │              │                              │
│     │              └──── DecisionSchemaValidator                │
│     │                             │                              │
│     └──── PolicyEngine <──────────┘                              │
│                    │                                            │
│                    v                                            │
│             BrowserKernel                                       │
│                    │                                            │
│                    v                                            │
│                 Browser                                         │
│                    │                                            │
│        fresh observation/result                                 │
│                    │                                            │
│                    v                                            │
│                Verifier                                         │
│                    │                                            │
│          Progress / Loop Detector                               │
│                    │                                            │
│   StateStore + FactStore + EventTrace + ArtifactStore           │
└─────────────────────────────────────────────────────────────────┘
```

Optional later branch:

```text
TaskController -> CapabilityRouter -> BrowserKernel
                               \-> deterministic connector/API
```

The router is introduced only when a connector is explicitly available and materially more reliable than manipulating the corresponding website UI.

---

# 3. State machine

```text
NEW
  |
  v
INITIALIZING
  |
  v
RUNNING <-----------------------------+
  |                                   |
  +--> WAITING_FOR_USER --------------+
  |
  +--> WAITING_FOR_CONFIRMATION ------+
  |
  +--> RECONCILING -------------------+
  |
  +--> REPLANNING --------------------+
  |
  +--> COMPLETED
  |
  +--> FAILED
  |
  +--> CANCELLED
```

No recursive agent calls are needed. "Replanning" is a state transition that produces a revised `PlanState`, then returns to `RUNNING`.

---

# 4. Canonical persisted schemas

Exact implementation may use Pydantic models + SQLite JSON columns initially.

## 4.1 TaskRecord

```json
{
  "task_id": "...",
  "goal": "...",
  "success_criteria": [],
  "created_at": "...",
  "status": "RUNNING",
  "risk_policy": "standard",
  "input_artifact_ids": [],
  "step_budget": 100
}
```

## 4.2 PlanState

```json
{
  "plan_version": 3,
  "subgoals": [
    {"id":"sg1","description":"...","status":"done"},
    {"id":"sg2","description":"...","status":"active"}
  ],
  "active_subgoal_id": "sg2",
  "open_questions": [],
  "completion_requirements": []
}
```

## 4.3 Observation

```json
{
  "observation_id": "obs_00042",
  "page_id": "page_3",
  "url": "https://...",
  "title": "...",
  "frame_tree_version": 8,
  "tabs": [
    {"page_id":"page_3","url":"...","title":"...","owner":"AGENT","active":true}
  ],
  "modal": null,
  "elements": [
    {
      "target":"obs_00042:f0:e17",
      "role":"textbox",
      "name":"Search",
      "value":"",
      "frame_id":"f0"
    }
  ],
  "text_blocks": [],
  "change_summary": [],
  "state_fingerprint": "..."
}
```

Observation is immutable. Target IDs are invalid once the BrowserKernel declares the observation incompatible with current page state.

## 4.4 Decision

The model returns exactly one decision.

```json
{
  "kind":"BROWSER_ACTION",
  "subgoal_id":"sg2",
  "action":"TYPE",
  "target":"obs_00042:f0:e17",
  "args":{"text":"machine learning"},
  "expected_outcome":{"field_value":"machine learning"},
  "reason_short":"Enter query"
}
```

Allowed `kind` values:

```text
BROWSER_ACTION
EXTRACT
ASK_USER
REQUEST_CONFIRMATION
REPLAN
FINISH
FAIL
NEED_VISUAL_GROUNDING
```

The model does not choose retry count, raw selectors, browser process commands, filesystem paths, or policy overrides.

## 4.5 ActionIntent

Persist before executing a mutating action.

```json
{
  "intent_id":"intent_...","+"
  "decision_id":"...",
  "action":"CLICK",
  "target":"...",
  "risk":"CONSEQUENTIAL",
  "idempotence":"UNKNOWN",
  "status":"PREPARED"
}
```

## 4.6 ActionResult

```json
{
  "intent_id":"...",
  "execution_status":"OK",
  "kernel_error":null,
  "new_page_ids":[],
  "download_artifact_ids":[],
  "dialog":null,
  "observation_id_after":"obs_00043"
}
```

## 4.7 VerificationResult

```json
{
  "status":"SATISFIED",
  "checks":[...],
  "evidence":{},
  "confidence":"deterministic"
}
```

Status:

```text
SATISFIED
NOT_SATISFIED
AMBIGUOUS
```

## 4.8 Fact

```json
{
  "fact_id":"fact_...",
  "key":"assignment.calculus.due_date",
  "value":"2026-09-18T23:59:00-04:00",
  "source_url":"...",
  "source_page_id":"page_4",
  "source_observation_id":"obs_00077",
  "source_text":"...",
  "retrieved_at":"...",
  "confidence":0.95,
  "sensitivity":"normal"
}
```

Conflicting facts coexist with contradiction metadata; one does not silently overwrite another.

---

# 5. BrowserKernel

## 5.1 Interface

```text
start()
health()
observe(page_id?) -> Observation
navigate(url)
click(target)
type(target, text, submit=false, slowly=false)
select(target, option)
press(target_or_page, key)
scroll(page_id, direction/amount)
back(page_id)
find(query, page_id)
switch_tab(page_id)
new_tab(url?)
close_agent_tab(page_id)
handle_dialog(...)
download(...)
upload(artifact_ids...)
take_screenshot(...)
shutdown()
```

Methods return typed results/errors only.

## 5.2 Candidate implementation: Playwright MCP (`GATE`)

Playwright MCP currently provides:
- semantic accessibility snapshots with refs;
- stale-ref failure;
- fresh state returned after actions;
- navigation/back;
- type/fill forms/press key;
- tabs;
- dialogs;
- file upload;
- screenshots;
- network/console inspection;
- storage/auth capabilities.

This is close to our desired kernel surface.

**MCP tools that should NOT be exposed to the model/controller action schema in MVP:**
- `browser_run_code_unsafe`;
- arbitrary `browser_evaluate`;
- network mocking/routing;
- unrestricted file access.

The adapter may use lower-level capabilities internally only if an explicit deterministic feature needs them and tests cover the behavior.

Sources:
- https://playwright.dev/mcp/introduction
- https://playwright.dev/mcp/snapshots
- https://playwright.dev/mcp/tools/forms
- https://playwright.dev/mcp/tools/tabs

## 5.3 Direct Playwright fallback

If MCP fails the kernel adoption spike, the interface remains unchanged. Direct Playwright implements semantic locator/snapshot generation itself.

This is why no controller code may depend on MCP-specific tool names.

---

# 6. Browser ownership model

## Dedicated profile default

MVP default:

```text
BrowserAgent-owned persistent Chromium profile
```

Reason:
- stable authentication persistence;
- clear tab ownership;
- native Playwright lifecycle control;
- fewer surprises than attaching to daily-driver Chrome.

Existing-browser CDP attach becomes optional later because Playwright documents CDP as significantly lower fidelity than its native protocol.

## Tab registry

Every page creation event immediately creates:

```text
PageRecord(page_id, owner, opener, created_event_id, url, closed)
```

Ownership:
- `AGENT` — created by BrowserAgent;
- `USER` — pre-existing/manual page;
- `EXTERNAL` — page created by external integration;
- `UNKNOWN` — conservative fallback.

Only `AGENT` pages may be automatically closed.

---

# 7. Observation pipeline

## Tier 1 — semantic snapshot

Primary representation:
- role;
- accessible name;
- value/state;
- selected structural text;
- frame scope;
- interaction ref.

## Tier 2 — targeted retrieval

For large pages:
- snapshot subtree;
- `find` by text/regex/semantic term;
- current viewport/near-target context.

## Tier 3 — DOM metadata enrichment

Only when semantic snapshot is insufficient:
- label/placeholder/title;
- select options;
- useful attributes;
- limited layout metadata.

## Tier 4 — vision fallback

Screenshot/boxes only when task requires visual information or a semantic target is missing.

The controller records why visual mode was invoked so we can measure its actual necessity.

---

# 8. ContextBuilder

Prompt/context packet is ordered for stability:

```text
SYSTEM/POLICY
CANONICAL TASK + SUCCESS CRITERIA
ACTIVE PLAN/SUBGOAL
RELEVANT FACTS
PREVIOUS ACTION + VERIFIED RESULT
CURRENT CHANGE SUMMARY
CURRENT RELEVANT OBSERVATION
ALLOWED DECISION SCHEMA
```

Hard budgets per block prevent page text from displacing the goal/policy.

No raw event history is included. The model can request additional page/search information through decisions.

---

# 9. ModelAdapter

Initial model: Qwen3:8B via Ollama because it is already available locally.

## Decision-interface gate

Evaluate two modes against the same frozen observation dataset:

1. native/Hermes-style tool calling;
2. one strict JSON `Decision` schema.

Metrics:
- parse/schema validity;
- allowed-action validity;
- correct target;
- correct action;
- hallucinated target rate;
- latency;
- token usage;
- recovery after validation error.

Do not choose based on one demo.

## Model upgrade path

`ModelAdapter` allows later:
- larger local Qwen/other open model;
- fine-tuned browser policy;
- WebRL/trajectory-style training;
- optional stronger diagnostic remote model.

Architecture must not assume a specific model intelligence level.

---

# 10. Planning

## Initial plan

For simple tasks, a plan may be one subgoal.

For complex tasks, the model generates 2-8 coarse subgoals, not browser actions.

Example:

```text
Goal: collect assignments from three Canvas accounts and create calendar events

sg1: inspect account A and persist assignment facts
sg2: inspect account B and persist assignment facts
sg3: inspect account C and persist assignment facts
sg4: normalize/deduplicate assignment facts
sg5: request confirmation for calendar writes
sg6: use calendar integration / browser action to create events
sg7: verify event coverage
```

Plan is revised only when evidence invalidates it or progress detector identifies a dead end.

---

# 11. Verification

Verifier prioritizes deterministic postconditions.

## Examples

### TYPE
- target still corresponds to field or matching semantic field;
- field value equals intended value.

### CLICK navigation
- expected URL/title/element change;
- new page/tab captured if relevant.

### CLICK toggle
- checked/expanded/selected state changed.

### SUBMIT
- task-specific success marker or destination state;
- otherwise `AMBIGUOUS`, never automatic success.

### EXTRACT
- result has source/provenance;
- required fields present.

### FINISH
- all explicit success criteria backed by state/facts.

---

# 12. Retry/recovery policy

## Read-only operations

Safe bounded retries may be allowed for:
- snapshot;
- find;
- extracting text;
- health checks;
- transient navigation fetch when no state change occurred.

## State-changing operations

No generic retry. On timeout/disconnect:
- reconcile current state;
- only replay if confirmed not applied.

## Stale/invalid target

Always:

```text
fresh observation -> new model decision
```

Never selector guessing.

---

# 13. Human handoff

Triggers:
- password/login;
- MFA;
- CAPTCHA;
- unexpected consent flow;
- consequential ambiguity;
- policy-required approval.

Protocol:

1. checkpoint;
2. set `WAITING_FOR_USER` or `WAITING_FOR_CONFIRMATION`;
3. release automation lock but preserve browser;
4. user acts;
5. resume signal;
6. invalidate all old browser targets;
7. rediscover pages/modal/auth state;
8. continue active subgoal.

---

# 14. Memory architecture

## Level A — execution trace

Append-only events for debugging/replay.

## Level B — working task state

Current plan, current page IDs, recent verified actions, active handoff/intent.

## Level C — task facts

Structured information with provenance used across pages/sites.

## Level D — retrieval/index

Introduce FTS only once fact count requires it.

## Level E — persistent cross-task memory

Defer until task-level system is reliable. Cross-task memory has privacy and stale-information risks and should not be required for basic operation.

---

# 15. Long research mode (later phase)

Long research is a controller mode, not a larger normal prompt.

Additional state:

```text
research_questions
coverage_requirements
visited_sources
source_quality
facts/evidence
contradictions
remaining_gaps
```

Loop:

```text
choose evidence gap
-> browse/search
-> extract provenance facts
-> deduplicate/contradict
-> update coverage
-> continue until coverage condition satisfied
```

External deterministic calculation/code may be useful for analysis later, but arbitrary webpage-triggered code execution remains forbidden.

---

# 16. Security/authority architecture

Authority ordering:

```text
system/product policy
> explicit user goal/approval
> trusted connector contract
> browser/page content
```

Page content can provide facts but cannot:
- broaden tool permissions;
- request filesystem secrets;
- disable confirmations;
- change the user's goal;
- authorize cross-origin transfer;
- invoke hidden tools.

PolicyEngine checks every action after model selection and before execution.

---

# 17. Artifacts/files

Run workspace:

```text
runtime/<task_id>/
  task.sqlite
  browser_profile/ (or profile reference)
  artifacts/
  downloads/
  screenshots/
  traces/
```

Downloads are explicitly saved because Playwright temporary downloads may disappear when context closes.

Uploads reference approved `artifact_id` records, not model-provided arbitrary local paths.

---

# 18. Observability

Every controller step records:
- context/token counts;
- model latency;
- decision;
- policy result;
- action intent;
- kernel result;
- verification;
- before/after observation IDs;
- failure classification;
- recovery transition;
- model/browser versions.

This is required to distinguish model failures from browser/runtime failures.

---

# 19. External integrations

BrowserAgent remains browser-first for arbitrary sites, but structured services should eventually use deterministic integrations when available.

Routing rule:

```text
if a trusted structured connector exists for the exact action
and it preserves user intent/auth/confirmation semantics:
    prefer connector for structured write/read
else:
    use browser
```

Example: browser can inspect Canvas, while Calendar event creation can use a Calendar API/connector instead of visually clicking through Calendar UI.

---

# 20. Architecture freeze gates

This architecture is frozen only when:

1. MCP vs direct Playwright spike is complete;
2. dedicated persistent profile works across restart;
3. primitive stress suite passes;
4. tab ownership invariant passes;
5. stale refs fail safely;
6. Qwen interface evaluation meets threshold or model plan is revised;
7. crash/ambiguous-submit reconciliation is demonstrated;
8. auth handoff/resume passes;
9. prompt-injection/policy tests pass;
10. controlled multi-step tasks complete without architecture-specific patches.

Only then should Codex receive the full implementation sequence.

# Grounding and Target Resolution

## Decision summary

BrowserAgentV2 should **not** create one durable `UniversalElement` object that pretends DOM nodes, AX/UIA nodes, OCR boxes and raw pixels share identity semantics. The minimum useful cross-route abstraction is instead an **ephemeral TargetSpec + fresh TargetCandidate set + adapter-local ExecutionRef**.

The model/planner should describe *what it intends to act on*. The active adapter should resolve that description against a fresh observation immediately before action. Opaque DOM/AX/UIA handles and coordinates remain adapter-local and short-lived.

```text
Goal/subgoal
  -> TargetSpec (semantic intent, route-neutral)
  -> fresh observation
  -> adapter resolver
  -> ranked TargetCandidate(s) with provenance + confidence
  -> ambiguity/staleness gate
  -> adapter-local ExecutionRef
  -> pre-action revalidation
  -> execute
  -> fresh observation
  -> verifier
```

## Why this is preferable to a universal element

The current Phase 0 evidence already demonstrates incompatible identity semantics:

- Playwright/DOM targets can be re-rendered and detached.
- macOS AX elements can be rebuilt after mutation; stale fixture elements correctly become invalid.
- visual targets have geometry but no stable object identity.
- duplicate labels make role/name alone insufficient.
- coordinates can become wrong after reflow, window movement or overlays.

External systems converge on the same separation. BrowserGym-style environments expose temporary browser IDs for action selection; ComponentBench documents accessibility-tree IDs/Set-of-Mark IDs as observation-local references rather than durable application identity. Agent S uses mixed screenshot + accessibility observations and a separate grounding layer. Tactile (2026) explicitly represents target candidates with source/provenance, role/text/state/geometry, executable affordances and verification cues rather than anonymous coordinates.

## Proposed contracts

### 1. `TargetSpec` — planner-owned intent

Store only durable-enough semantic intent:

```python
@dataclass(frozen=True)
class TargetSpec:
    app: str | None
    window_hint: str | None
    role: str | None
    name: str | None
    text_hint: str | None
    state_constraints: dict[str, object]
    relation: RelationHint | None      # e.g. inside dialog X, right of label Y
    ordinal: int | None               # only when user/task semantics truly imply it
    route_preferences: tuple[str, ...]
```

Do **not** store DOM node objects, AXUIElement refs, UIA runtime IDs, or coordinates here.

### 2. `TargetCandidate` — observation-local evidence

```python
@dataclass(frozen=True)
class TargetCandidate:
    observation_id: str
    source: Literal['dom','browser_ax','mac_ax','uia','ocr','vision']
    role: str | None
    name: str | None
    text: str | None
    states: dict[str, object]
    bounds: Rect | None
    ancestry_hint: tuple[str, ...]
    affordances: frozenset[str]
    confidence: float
    provenance: dict[str, object]
    execution_ref: object             # opaque, adapter-local, never persisted as identity
```

The `execution_ref` dies with the observation or any known mutation. Persist the semantic fingerprint/provenance for audit, not the handle.

### 3. `ResolutionResult`

```text
RESOLVED(candidate, confidence)
AMBIGUOUS(candidates, reason)
STALE(reason)
UNSUPPORTED(reason)
NOT_FOUND(reason)
```

A resolver must be allowed to abstain. `AMBIGUOUS` is a success of the grounding safety contract, not an exception to hide with a guessed click.

## Matching policy

Use deterministic matching before model-based grounding when structured semantics exist:

1. application/window scope;
2. role/affordance compatibility;
3. exact accessible name/text when available;
4. state constraints;
5. ancestry/dialog/container relation;
6. geometric relation only as supporting evidence;
7. fuzzy/model scoring only after deterministic filters.

If multiple candidates remain materially plausible, do not silently choose the highest score for consequential actions. Escalate to richer observation (screenshot/vision), request a fresh observation, or abstain/handoff according to risk.

## Staleness and TOCTOU

There are two separate stale-target problems:

1. **Object staleness:** the DOM/AX/UIA object was replaced.
2. **semantic rebinding:** the old coordinates/label now refer to a different control.

The second is more dangerous because the API may still execute successfully. A 2026 desktop-GUI TOCTOU study formalizes observation-to-action manipulation and proposes immediate pre-execution UI revalidation. BrowserAgentV2 should therefore revalidate consequential targets immediately before dispatch:

- same app/window identity;
- same semantic fingerprint where available;
- geometry still compatible with observation;
- no unexpected overlay/focus/window transition;
- if visual route: target-region/global-state freshness check when latency is high.

This is especially important for irreversible or externally visible actions.

## Cross-route escalation

The router should not translate one route's opaque handle into another route. It should translate **intent**:

```text
TargetSpec
  -> Playwright resolver fails/ambiguous
  -> fresh browser AX resolver
  -> fresh screenshot/vision resolver
```

This avoids pretending a DOM node ID and a vision box are the same object. Their relationship is established by fresh evidence (semantic fields + geometry + current observation), not by durable identity.

## Confidence policy

Confidence should be calibrated per resolver and action class, not one global magic threshold. Record:

- resolver confidence;
- number/margin of competing candidates;
- evidence sources agreeing/disagreeing;
- observation age;
- route/action risk.

High-risk actions require stronger evidence or confirmation/handoff. Low-risk reversible actions may tolerate lower confidence plus strict postcondition verification.

## Required BrowserAgentV2 experiments

1. **Duplicate labels:** two same-name buttons in different containers; reorder between observe and act. Correct result is re-resolution by container relation or `AMBIGUOUS`, never arbitrary selection.
2. **DOM replacement:** replace target node after observation but before action. Old ref must fail/re-resolve.
3. **AX replacement:** repeat existing stale-element fixture with semantic re-resolution.
4. **Coordinate reflow:** move/resize window after visual grounding. Old coordinates must be rejected/re-grounded.
5. **Overlay hijack:** inject a benign overlay between observe and dispatch; pre-action freshness gate must stop action.
6. **Cross-route agreement:** compare DOM/AX/vision candidates on the same browser fixture and measure agreement, ambiguity and latency.
7. **Custom/canvas UI:** semantics absent -> vision candidate with explicit provenance and lower calibrated confidence, followed by deterministic/visual postcondition.

## Provisional decision

**DECISION:** Ephemeral `TargetSpec -> TargetCandidate -> adapter-local ExecutionRef`; no durable universal element.

**CONFIDENCE:** 95%

**Primary remaining uncertainty:** how much cross-source fusion is worth implementing before local visual grounding is benchmarked. Start without a learned fusion layer.

## Sources

- BrowserAgentV2 Phase 0 runner and macOS capability experiments (direct repository evidence).
- Agent S source/README: mixed screenshot + accessibility observations and separate grounding agent: https://github.com/simular-ai/Agent-S
- ComponentBench observation modes / BrowserGym-style bid IDs: https://github.com/TianchenGuan/ComponentBench/blob/main/docs/observation_modes.md
- Tactile: Giving Computer-Using Agents Hands and Feet, arXiv:2607.14443.
- Temporal UI State Inconsistency in Desktop GUI Agents, arXiv:2604.18860.

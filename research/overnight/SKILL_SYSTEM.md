# Reusable Skill System

## Decision
Skills should be **versioned procedural packages that compile into controller-visible preconditions/actions/verifiers**, not autonomous sub-agents and not free-form memories promoted after one success.

BrowserAgentV2 should adopt progressive disclosure: keep only compact skill metadata in the normal model context; load full procedural guidance/resources only when a skill is selected. This pattern is now used by Agent Skills and OpenHands and directly supports BrowserAgentV2's bounded-context requirement.

## Skill boundary
A skill is justified when a workflow has repeated semantic structure and can provide stronger preconditions/postconditions than generic reasoning. Examples: navigate a known application flow, create a calendar event, download-and-verify a file, fill a repeated form, or perform a repository workflow. Atomic click/type primitives are adapters, not skills. One-off natural-language plans are plans, not skills.

## Minimal manifest
Each skill should declare:
- `skill_id`, semantic name, version, content hash, provenance
- short trigger/description metadata
- required capabilities and allowed destinations/resources
- input schema and output schema
- preconditions
- ordered workflow template or deterministic implementation entry point
- allowed adapters/routes
- success predicates and safety invariants
- idempotency/reversibility class per consequential operation
- expected failure classes and permitted recovery transitions
- test fixture references and last validated version/environment

The controller validates this manifest. The model may select/propose a skill but cannot alter its capability envelope.

## Progressive disclosure
Tier 0, always visible: skill ID, one-line description, capability summary, input schema summary.
Tier 1, selected skill: core procedure, pre/postconditions, expected failure handling.
Tier 2, on demand: app-specific references/examples/edge cases.
Tier 3, executable deterministic helpers/resources, invoked by controller rather than pasted into model context.

This prevents a large skill library from linearly inflating the prompt. Anthropic's Agent Skills design explicitly uses metadata-first progressive disclosure; OpenHands' current extension registry likewise stores reusable skills separately and loads domain guidance as needed.

## Skill execution
`select -> validate inputs -> capability/policy gate -> instantiate versioned skill run -> execute controller step(s) -> independently verify -> commit evidence`

A skill is not allowed to mark itself successful. Its verifier contract is evaluated through the same typed verification layer as generic actions.

## Skill learning/promotion
Do not automatically convert successful trajectories into executable skills. A trajectory may contain accidental workarounds, stale selectors, unsafe authority assumptions, or unnecessary steps.

Promotion pipeline:
1. detect repeated successful semantic pattern;
2. propose candidate skill offline;
3. minimize to stable semantic steps;
4. infer explicit preconditions/postconditions/invariants;
5. declare capabilities and side-effect classes;
6. run regression + perturbation fixtures repeatedly;
7. human/local trusted promotion into signed/versioned library;
8. monitor failures and revoke/roll back by version.

Untrusted web/document content and retrieved memory can never create/promote executable skills.

## Routing
Use deterministic matching where input/task schema makes a skill obvious. Otherwise let the generalist rank candidate skill metadata. If no candidate clears confidence/precondition checks, use generic planning. Do not force a skill because its name is semantically similar.

## Skill composition
Composition is controller-owned. Parent plans may call skills as typed operations, but capabilities compose by intersection/explicit grant, never union through nesting. Each child skill preserves its own verifier and side-effect journal entries. A failed child returns a classified failure rather than free-form text that silently changes the parent goal.

## When not to create a skill
- workflow has not repeated enough to establish stable structure;
- UI/app semantics are too volatile and no stable verifier exists;
- the only benefit is saving a short prompt;
- capability envelope cannot be stated safely;
- procedure is better expressed as deterministic code/tool API;
- task is simple enough that the controller + one model proposal is cheaper.

## Experiment
Create 10 representative skills and 100 decoy/irrelevant skill metadata entries. Compare:
A. all full skill text injected;
B. metadata progressive disclosure;
C. metadata + deterministic schema filter before model ranking.

Measure required-skill recall, false skill activation, active tokens, selection latency, execution success, and authority violations. Target >=99% required-skill recall on controlled fixtures while prompt size remains approximately flat as skill bodies grow.

Then perturb each selected skill's UI/app state and verify that stale skill assumptions trigger classified re-ground/replan rather than blind continuation.

## Rejected designs
- each skill is its own agent: duplicates planner/controller state and authority.
- vector similarity directly executes a skill: retrieval is not authorization or applicability proof.
- full skill library in system prompt: violates bounded context.
- automatic self-modification after success: unsafe and hard to regress.
- raw recorded coordinate macros as skills: brittle identity and no semantic verifier.

## Confidence
**93%** for versioned progressive-disclosure skills under the deterministic controller. **84%** for the exact manifest fields; validate by implementing 10 representative workflows before freezing schema.

## Sources checked
- Anthropic, `Equipping agents for the real world with Agent Skills` (2025): metadata-first progressive disclosure, on-demand SKILL.md/resources, executable helpers.
- OpenHands extensions/skills repositories (2026): reusable Markdown skills and executable plugins with repository-scoped guidance.
- Anthropic code-execution/MCP engineering guidance: on-demand tool definition loading and filtering to reduce context.
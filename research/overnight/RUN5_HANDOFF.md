# Run 5 Handoff — Security + Controller

## Architecture-changing conclusions
1. **Authority/information separation (96%)**: external/UI/tool/retrieved content is evidence, never authority. Only explicit task scope, deterministic local policy, pre-granted capabilities and durable workflow state may authorize side effects.
2. **Deterministic action gate (96%)**: every state-changing ActionIntent must pass structured non-LLM policy before dispatch. Injection detection is defense-in-depth, not the authorization boundary.
3. **Data-flow-aware least privilege (91%)**: track sensitive reads and external destinations so individually permitted tools cannot compose into an unauthorized exfiltration path.
4. **Single durable controller (94%)**: do not build autonomous planner/executor/recovery agents. One deterministic lifecycle owns persistence, retry budgets, policy, routing, verification and handoff; models are bounded proposal functions.
5. **Typed failure-driven recovery (92%)**: retry/re-ground/switch-route/replan/handoff decisions come from classified failure + action risk/idempotency, not free-form model looping.

## New artifacts
- `SECURITY_POLICY.md`
- `PLANNER_RECOVERY_STATE_MACHINE.md`

## Evidence that changed the design
- Current OWASP agent guidance explicitly recommends treating external content as untrusted, least privilege, structured validation, and not relying solely on model output for authorization.
- OpenAI's computer-use deployment uses layered confirmations/injection monitoring rather than model behavior alone.
- Anthropic's 2026 containment report describes a controlled red-team case in which a user-delivered malicious prompt successfully caused credential exfiltration in 24/25 retries; filesystem/network boundaries were identified as the defense that would hold even when model intent defenses did not.
- Anthropic's 2026 auto-mode architecture independently separates input injection probing from an action-side classifier.
- PromptArmor/AgentSentry demonstrate useful model-level defenses, but 2025 benchmark analysis reports that apparently saturated injection benchmarks can still be bypassed in practice. Therefore injection detection cannot be the root policy boundary.

## Do not redo next run
Do not repeat broad prompt-injection-defense surveys, memory/vector DB surveys, generic workflow durability research, Windows/UIA research, or GUI-grounder leaderboard collection unless contradictory evidence appears.

## Highest-value next queue
1. **Local model routing benchmark design**: choose realistic candidate generalist(s), structured-output strategy, KV/prefix reuse, escalation rules, and benchmark matrix for M5 24 GB + RTX 4070 12 GB. Do not freeze specialists without measurements.
2. **Skill architecture**: define narrow reusable skills as capability + preconditions + TargetSpec/action template + verifier + invariants, without turning skills into an uncontrolled second planner.
3. **Experiment specifications**: grounding fault injection, verifier coverage, crash matrix, prompt-flatness, policy/injection adversarial fixtures.
4. **Final architecture simplification pressure**: look for components that can be removed before synthesis.

## Proposed ADR additions
### ADR-O11 — Authority/information separation + deterministic policy gate
Confidence 96%. External content cannot grant authority. Structured ActionIntent is checked against task-scoped capabilities and invariants outside the acting model. Model-level injection defenses are supplementary.

### ADR-O12 — Single durable controller; models are proposal functions
Confidence 94%. Controller owns lifecycle/recovery. Replanning versions state; model cannot mark success, widen capabilities, waive verification or rewrite history.

### ADR-O13 — Failure-class-driven bounded recovery
Confidence 92%. Exact retry is limited to classified safe transient failures; stale/ambiguous targets re-ground; capability failures may switch approved route; structural/precondition failure replans; ambiguous irreversible effects and policy expansion hand off.

## Final-state pressure test
The architecture is converging toward a small core: durable state/event journal + deterministic controller/policy + semantic/visual adapters + typed verifier + bounded model proposal interface. Avoid adding independent agents, a vector DB, a permanent critic, or permanent GUI grounder unless the remaining hardware benchmarks prove necessity.
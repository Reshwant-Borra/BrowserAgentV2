# Related Systems — Initial Architecture-Relevant Pass

## Purpose
This is not a catalog. It records external systems/research only where they change or stress BrowserAgentV2 architecture decisions.

## OpenAI Computer-Using Agent (CUA)
**Observed design:** raw screenshots + virtual mouse/keyboard in an iterative perception/reasoning/action loop. OpenAI reported 38.1% on OSWorld, 58.1% WebArena and 87.0% WebVoyager in the January 2025 release.

**Architecture lesson:** a pixel/action universal interface is genuinely broad, but broadness is not the same as reliability. It proves BrowserAgentV2 needs a universal fallback, not that it should discard semantic routes. The repo's measured Playwright path has deterministic postcondition checks and background behavior that raw host input cannot inherently provide.

**Decision impact:** keep vision/coordinates as escalation, not default. Do not attempt to clone a frontier-model-dependent pixel-only stack with an 8B local model.

## Agent S2
**Observed design:** compositional generalist/specialist architecture; Mixture-of-Grounding plus proactive hierarchical planning. Reported improvements over strong baselines on OSWorld/WindowsAgentArena/AndroidWorld.

**Architecture lesson:** grounding and long-horizon planning are separable bottlenecks and can benefit from specialist components. However, this does not justify permanent multi-model decomposition for BrowserAgentV2 until local-hardware measurements show net benefit.

**Decision impact:** benchmark selective specialist escalation (grounder and/or critic) against a minimal baseline; do not create many always-on agents.

## OpenCUA
**Observed design:** open computer-use foundation models trained from broad cross-OS/application demonstrations. OpenCUA-32B reported 34.8% on OSWorld-Verified; later work using OpenCUA-72B shows failure-driven inference-time patches can materially improve success without retraining.

**Architecture lesson:** broad GUI competence increasingly belongs in the model, but agent harness design still changes outcomes. This supports keeping the model adapter replaceable and investing in failure instrumentation rather than assuming model upgrades remove the need for a reliability layer.

## UI-TARS-2
**Observed design:** native GUI-centered agent with multi-turn RL plus a hybrid GUI environment integrating filesystems and terminals. Reported 47.5 on OSWorld and 50.6 on WindowsAgentArena.

**Architecture lesson:** even strong GUI-native agents benefit from non-GUI tools. A universal ComputerAgent should route among tools and GUI, not force every task through pixels.

## OSWorld / OSWorld-Verified family
**Observed findings:** original OSWorld identified coordinate grounding errors, repetitive actions, unexpected-window failures, and cross-app weakness. Accessibility trees/Set-of-Mark could help but could also mislead depending on model. Repeated-history/high-resolution inputs can improve success at context cost.

**Architecture lesson:** do not feed giant raw accessibility trees or ever-growing screenshot history. Use bounded semantic observations, state deltas and targeted visual escalation. Evaluate cross-app tasks and unexpected-window noise explicitly.

## On the Reliability of Computer Use Agents (2026)
**Observed finding:** repeated executions of the same task can have materially different outcomes; reliability depends on task ambiguity and behavioral variability. Authors argue for repeated execution evaluation and stable strategies.

**Architecture lesson:** one-shot benchmark success is insufficient. BrowserAgentV2 validation should report repeated-trial task success and variance, not only a single successful trajectory.

## Rethinking Inference-Time Scaling in Local CUAs (2026)
**Observed finding:** on Qwen3-VL-8B/30B-A3B, UI-TARS-1.5-7B and OpenCUA-7B, more inference compute often gives diminishing returns; more history can improve trajectory stability but shifts failures toward premature false success; longer horizons can merely extend wrong trajectories; two-stage decomposition can add planning/formatting overhead.

**Architecture lesson:** this directly argues against 'just give the local agent more context/steps/models.' BrowserAgentV2 needs explicit verification, failure-aware compute allocation and bounded retries. Any specialist split must earn its latency/accuracy cost empirically.

## OpenComputer (2026)
**Observed design:** verifier-grounded software worlds with app-specific structured state verifiers, execution-grounded verifier improvement, machine-checkable tasks, full trajectory recording and partial-credit evaluation across 33 apps / 1,000 tasks. Hard-coded state verifiers aligned better with human adjudication than LLM-as-judge for fine-grained state.

**Architecture lesson:** strongest external support found so far for BrowserAgentV2's independent Verifier. When deterministic/app-state verification exists, prefer it to model self-evaluation or visual 'looks done' judgments.

**Decision impact:** elevate verification from a generic post-action check to a first-class per-skill/per-adapter contract with structured success predicates and evidence provenance.

## CUADebug (2026)
**Observed finding:** human annotation of 204 failed OSWorld trajectories found task reasoning/control as the largest failure family, followed by perception and grounding/interaction. Debugging suspicious steps with paired before/after screenshots and action traces improved re-execution success over history-only continuation.

**Architecture lesson:** store compact before/action/after evidence for state-changing steps and classify failures before retry/replan. Do not treat all failures as grounding failures or blindly append trajectory history.

## OS-Oracle (2025)
**Observed design:** a GUI critic model for pre-action assessment; reported improvements when placed before native GUI agents.

**Architecture lesson:** a specialist critic is plausible for uncertain/irreversible visual actions, but BrowserAgentV2 should first implement deterministic policy + verifier checks. A learned critic should be an escalation, not the authority.

## OSGuard (2026)
**Observed finding:** agents can satisfy nominal task objectives via unsafe shortcuts; end-to-end safety evaluation needs state-based safety invariants in addition to local action judgments.

**Architecture lesson:** BrowserAgentV2's policy layer needs task-level invariants, not only per-action allow/deny checks. Verification should check both desired effects and prohibited effects.

## OSWorld-MCP (2025)
**Observed finding:** tool availability improved success in tested settings, but even strong models underused tools.

**Architecture lesson:** exposing tools is insufficient. InteractionRouter decisions and tool-vs-GUI selection need explicit evaluation and potentially deterministic routing rules for known capabilities.

## Synthesis
External evidence does **not** point to one universal sensory/action representation. The converging pattern is: strong GUI-native models for broad fallback; semantic/tools when available; explicit hierarchical state for long tasks; verifier/critic mechanisms; repeated-trial evaluation; and failure-aware recovery. This is compatible with the repo's current direction, with one strengthening: verification and failure diagnosis should be more central than the current architecture diagram implies.

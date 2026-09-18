# BrowserAgentV2 — Do Not Build Yet

These are deliberate exclusions until measurements falsify the simpler architecture.

- **No pixel-only universal controller.** Existing semantic browser evidence is stronger; pixels are fallback.
- **No durable UniversalElement.** DOM/AX/UIA/visual identities have incompatible lifetimes. Persist semantic intent, not handles.
- **No browser-through-AX primary route.** Direct Chrome false-success evidence rejects this.
- **No physical mouse/keyboard default.** Keep as capability-gated foreground fallback only.
- **No autonomous planner/executor/verifier/recovery agent hierarchy.** One durable deterministic controller owns state and lifecycle.
- **No always-on planner + grounder + critic ensemble.** Benchmark one generalist and escalate only on measured gaps.
- **No fixed Qwen dependency.** Qwen3-VL-8B is a benchmark candidate behind a replaceable typed interface.
- **No mandatory GUI specialist.** UI-TARS/ZonUI/UGround remain challengers until BrowserAgentV2-specific tests justify residency/latency.
- **No model-as-verifier for deterministic state.** Model verification is fallback for evidence that cannot be expressed structurally.
- **No model-authorized capability expansion.** Untrusted content and model output cannot grant authority.
- **No prompt-injection classifier as root security boundary.** Use deterministic capability/data-flow policy.
- **No full-transcript memory.** Correctness state is structured and durable; model context is bounded.
- **No vector DB for execution truth.** Start SQLite/FTS; retrieval is advisory.
- **No automatic skill induction into trusted execution.** Successful traces are candidates requiring explicit contracts and regression tests.
- **No Graphify runtime memory.** Keep graph tooling developer-only/removable if useful at all.
- **No generic exactly-once claim for arbitrary UI/external effects.** Use idempotency/reconciliation and surface outcome unknown.
- **No screenshot-difference-equals-success rule.** Verify semantic postconditions and safety invariants.
- **No OTel backend as recovery state.** Telemetry is derived and disposable.
- **No raw screenshot/prompt/tool-output logging everywhere by default.** Store compact events and opt-in artifact references.
- **No production controller inside Phase 0 ExperimentRunner.** Preserve Phase 0 as an independent measurement harness.
- **No use of Phase 0 JSONL as transactional journal.** Production recovery needs SQLite/durable transactions.
- **No benchmark chasing before controller contracts pass.** A strong model can mask broken grounding/recovery without fixing them.
- **No GUI dashboard in the first vertical slice.** It adds no confidence in correctness contracts.
- **No Windows abstraction claims before real UIA hardware tests.** Capability is measured per app/action.

## Reconsideration rule
A deferred component is added only when a reproducible failure or benchmark shows the current simpler contract cannot meet a defined gate, and the proposed component fixes that failure without weakening authority, verification, recovery, or observability invariants.
# BrowserAgentV2 Open Questions — Pre-Final Convergence

## Architecture-design blockers
At this point, none are known that require another broad survey. The core architecture is coherent enough to implement as falsifiable contracts. A failure in the vertical-slice fixtures may reopen an architecture decision, but that should be evidence-driven rather than speculative.

## Implementation-validation blockers
These remain real and must not be represented as solved.

### P0 — Grounding freshness contract
**Question:** Can `TargetSpec -> fresh observation-local candidate -> ephemeral ExecutionRef -> pre-dispatch freshness` achieve zero wrong/stale dispatch under seeded UI mutations?
**Why unresolved:** specified but not implemented/run.
**Exact test:** `VERTICAL_SLICE_BUILD_SPEC.md` Fixture A / V1; >=1,000 seeded trials.
**Failure consequence:** architecture blocker for consequential GUI actions.

### P0 — Verifier false-success resistance
**Question:** Does the small typed predicate vocabulary detect no-op/wrong/partial/collateral mutations without app-specific DSL explosion?
**Why unresolved:** specified but not implemented/run.
**Exact test:** Fixture B / V2; >=1,000 injected trials; zero false success.
**Failure consequence:** revisit verifier observation independence/vocabulary.

### P0 — Crash reconciliation
**Question:** Does durable intent + reconciliation avoid unsafe duplicates across all kill points?
**Why unresolved:** no process-kill harness has been run.
**Exact test:** Fixture C / V3, all four side-effect classes and every durable boundary.
**Failure consequence:** production side effects remain blocked; class-D must still stop as outcome unknown.

### P1 — Bounded state reconstruction
**Question:** Can 200/500/1,000-action tasks reconstruct correctness-critical state exactly while active model projection stays bounded?
**Why unresolved:** benchmark not implemented.
**Exact test:** V4 synthetic trajectories with failures/replans/superseded facts.
**Failure consequence:** revise state/projector schema before model integration.

### P1 — Actual local model/runtime
**Question:** Does Qwen3-VL-8B at practical quantization meet schema quality, abstention, latency and memory gates on Apple Silicon 24 GB and RTX 4070 12 GB?
**Why unresolved:** requires target hardware/runtime benchmark.
**Exact test:** V5; compare optional 2-3B GUI specialists only on semantic-gap cases.
**Failure consequence:** replace model behind stable proposal interface; not automatically an architecture failure.

### P1 — Windows UIA capability matrix
**Question:** Which Windows app/action pairs have independently verified UIA behavior, including background/occluded conditions?
**Why unresolved:** target Windows hardware not exercised in this research environment.
**Exact test:** V8 across representative Win32, WPF/WinUI, Electron, Chrome/Edge, custom-rendered surfaces.
**Failure consequence:** route-specific capability downgrade/fallback; not automatically an architecture failure.

### P2 — Skill progressive disclosure
**Question:** Does metadata-filtered skill loading reduce context without increasing false activation or capability widening?
**Exact test:** V6 with 10 real + 100 decoy skills.
**Failure consequence:** keep skills explicit/manual longer; core controller unaffected.

### P2 — Visual specialist value
**Question:** Is a dedicated GUI grounder materially better than the generalist on semantic-gap tasks after latency/residency cost?
**Exact test:** V5 compare UI-TARS-2B, ZonUI-3B, UGround-V1-2B only after generalist baseline.
**Failure consequence:** omit specialist.

### P2 — External benchmark mapping
**Question:** Which small OSWorld/WindowsWorld/web subset best exercises BrowserAgentV2's routes and recovery semantics?
**Why deferred:** external score cannot validate broken deterministic contracts.
**Failure consequence:** none for architecture; affects comparability only.

## Final-run decision rule
A final verdict may be `READY_TO_BUILD` even with P1/P2 hardware/performance questions unresolved if the architecture exposes replaceable interfaces and the unresolved questions do not require a redesign. Use `READY_WITH_BLOCKERS` if P0 correctness contracts remain entirely unimplemented and the report's meaning of "build" implies production deployment rather than beginning the falsification-first implementation. Do not use `NOT_READY` unless evidence reveals a contradiction in the core architecture or no safe testable implementation sequence exists.

## Single next engineering task
Implement Fixture A and the minimal `TargetSpec`/observation-version/freshness gate only. Do not start model integration. Run 1,000 seeded mutation trials and turn every failure seed into a regression test. This is the cheapest experiment capable of falsifying the current target/control architecture.
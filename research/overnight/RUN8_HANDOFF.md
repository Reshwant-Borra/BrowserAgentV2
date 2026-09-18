# Run 8 Handoff — Final Convergence Preparation

## What changed
Broad architecture research was intentionally stopped. This pass inspected the existing Phase 0 harness and converted the remaining high-risk assumptions into the smallest production-shaped vertical slice.

New artifacts:
- `VERTICAL_SLICE_BUILD_SPEC.md` — exact package/files, controller path, fixtures, invariants, gates, stop conditions, and first runnable campaign.
- `OPEN_QUESTIONS.md` — remaining uncertainties classified as implementation-validation blockers rather than unresolved broad architecture questions.

## Direct repository evidence used
`phase0/harness/runner.py` already enforces the critical distinction between `execute()` and independently observable `verify()`: exception-free dispatch alone never counts as success. Preserve this semantic contract.

`phase0/harness/persistence.py` is intentionally JSONL experiment evidence. Preserve it for campaigns, but do not confuse it with the production recovery journal; the production controller should use transactional SQLite durable state/journal.

The repository already has a real unit-test substrate under `tests/phase0/`, so the next implementation should add `tests/computer_agent/` rather than introducing a new framework.

## Architecture status
No new broad architecture-design blocker was found. The remaining high-impact uncertainty is empirical:
1. grounding freshness/abstention under seeded mutation
2. verifier false-success resistance
3. crash reconciliation across commit boundaries
4. bounded state reconstruction at 1,000 actions
5. target-hardware local-model measurements
6. Windows UIA capability measurements

The first four can be tested without committing to a production model. Model/hardware failures should normally replace an adapter/model behind stable interfaces rather than force a controller redesign.

## Single next engineering task
Implement only the pure-Python mutable-UI grounding fixture plus minimal `TargetSpec`, `ObservationVersion`, `TargetCandidate`, and pre-dispatch freshness gate. Run >=1,000 seeded trials. Require zero wrong-target and zero stale-target dispatch. Ambiguous/absent targets must abstain. Persist failing seeds as regression cases.

Do not integrate Qwen, a GUI grounder, vector memory, skills, Windows UIA, OpenTelemetry backend, or external benchmarks before this contract is tested.

## Final-pass instruction
The next pass is the final synthesis. Do not reopen broad surveys unless a direct contradiction is discovered. Review all ADRs and artifacts for internal consistency; red-team the candidate architecture; create/update `FINAL_ARCHITECTURE.md`, `BUILD_PLAN.md`, `DO_NOT_BUILD.md`, `OPEN_QUESTIONS.md`, and `FINAL_RESEARCH_REPORT.md`. Distinguish "ready to begin the falsification-first build" from "production validated." The report must not imply that V1-V8 hardware/fault campaigns have already run when they have only been specified.
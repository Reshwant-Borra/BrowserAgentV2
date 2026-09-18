# Developer Console v0

A local, observational view of ComputerAgent's deterministic backend (D-025, D-026). It is not the consumer product (M11).

```bash
.venv-phase0/bin/python -m devconsole            # http://127.0.0.1:8765/
.venv-phase0/bin/python -m devconsole --port 9000
```

**Stack.** It uses the stdlib `http.server`, bound to localhost only, plus one static `static/index.html` with no build step and no dependencies. `views.py` runs a backend trial and serializes the verdicts the backend already computed. The page renders those values generically: objects become key/value tables, arrays become tables, and outcome words get colored badges.

**Tabs.**
- **M1 · Grounding (Fixture A):** TargetSpec, observation versions, candidates, resolution, freshness, dispatch or abstain, and the oracle grading.
- **M2 · Verification (Fixture B):** the action intent, the executor claim (recorded only), the before and after state, the spec, per-predicate results, the side-effect check, and the oracle.
- **M3 · Lifecycle (Fixture C):** a per-step lifecycle built from the SQLite journal, plus the oracle and an ordered timeline of journal events. Harness `CRASH`/`RESTART` markers are interleaved in the timeline and labeled as harness events. Use the scenario menu to pick combined M1→M2→M3 scenarios, or `crash:<class>:<boundary>`.

Any trial can be rerun by keeping the same seed.

**Boundary.** The page and `views.py` never resolve targets, check freshness, verify, recover or grade. Nothing under `computer_agent/` imports this package. `tests/devconsole/test_console.py` enforces both rules and checks every view against the backend's own verdicts.

# Run 3 Handoff

## Architecture changes
1. **Windows semantic route:** Use UIA as the default Windows desktop semantic adapter, but capability-gate every action/pattern and retain injected-input + visual fallbacks. Confidence 91%. Microsoft's current Windows automation tooling itself uses this hybrid pattern across WPF, WinForms, Win32, Electron, and WinUI 3. Do not infer background safety from UIA availability; measure it per action/control/app.
2. **Visual fallback shortlist:** Do not freeze a dedicated GUI model yet. Benchmark UI-TARS-2B first, with ZonUI-3B and UGround-V1-2B as challengers. Confidence 82% that a small specialist is the correct experiment; lower confidence that any particular model wins. Optimize for wrong-confident-click rate and abstention, not ScreenSpot headline score.
3. **Architecture simplification:** A dedicated grounder must be optional and narrow. It produces observation-local target candidates only. It does not plan, own memory, or verify task completion. If it fails to materially beat the generalist baseline on BrowserAgentV2 fixtures, remove it from v1.

## Evidence summary
- Microsoft documents UIA inspection/control patterns and current `winapp ui` coverage across modern Windows frameworks including Electron, while retaining synthetic mouse/keyboard fallbacks where UIA patterns cannot act.
- pywinauto's UIA backend similarly covers modern frameworks/browsers but documents browser/custom-control limitations. This falsifies UIA-only universality while supporting semantic-first routing.
- UI-TARS-2B has strong public GUI grounding results and third-party evidence suggesting roughly 4.1 GB VRAM / ~1.2 s warm element-find latency on NVIDIA; runtime evidence is anecdotal and must be reproduced.
- ZonUI-3B reports stronger ScreenSpot-v2 aggregate grounding than UI-TARS-2B in its comparison table and is the most important challenger.
- UGround-V1-2B is a useful same-size control. OS-Atlas and larger generalists should not be the first narrow-grounder experiment.

## New artifacts
- `WINDOWS_UIA.md`
- `VISUAL_GROUNDING.md`

## Next queue
1. **Long-horizon state + memory:** design the minimal Goal/Plan/Event/Fact/Recovery representation that keeps active prompt size approximately flat from 200 to 1,000 actions; separate authoritative state from retrieval memory.
2. **Crash reconciliation:** specify and falsify intent/commit semantics so an unresolved `ACTION_INTENT` cannot duplicate irreversible external side effects after restart.
3. **Local model split:** define a common fixture benchmark comparing one generalist, +dedicated grounder, +critic, and both. Do not select models from leaderboards alone.
4. **Security:** convert indirect prompt injection and task constraints into deterministic policy/verifier invariants.
5. **Experiments:** implement Windows capability matrix and the visual-grounding fixture corpus when target hardware execution becomes available.

## Negative results / rejected assumptions
- `UIA available` does not mean `safe background action available`.
- Electron does not automatically require pixel control, but custom-rendered surfaces can still defeat semantics.
- A GUI-grounding leaderboard win does not establish safe action routing; absent-target abstention and wrong-target rate are first-class metrics.
- A dedicated visual grounder is not yet a permanent architecture component.

## Recommended next-run behavior
Do not redo Windows/UIA or broad visual-grounder surveys unless contradictory implementation evidence appears. Move directly into long-horizon state, prompt compaction, event sourcing/checkpointing, and crash reconciliation. Those are now higher-impact uncertainties than the control-route hierarchy.
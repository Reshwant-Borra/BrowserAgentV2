import type { BrowserKernel } from "../contracts/kernel.js";
import { FIXTURE_BASE, SuiteRecorder, type CandidateName, type SuiteResult } from "./harness.js";

// This fixture deliberately replaces the <input> DOM node (new element
// identity) on EVERY keystroke, simulating the worst-case controlled-input
// re-render pattern that caused typing regressions in the prior BrowserAgent.
// A single-shot fill() only touches the DOM once, so it should generally
// survive; character-by-character typing is expected to be the harder case
// — we measure both rather than assume either passes.
const REPS_FILL = 10;
const REPS_SEQUENTIAL = 10;

export async function run(kernel: BrowserKernel, candidate: CandidateName): Promise<SuiteResult> {
  const rec = new SuiteRecorder("react_controlled_typing", candidate);
  const page = await kernel.newPage();

  for (let i = 0; i < REPS_FILL; i++) {
    const name = `react-fill-${i}`;
    const value = `fillval-${i}-${"x".repeat(i % 5)}`;
    try {
      await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/b`);
      const obs = await kernel.observe(page.pageId);
      const input = obs.elements.find((e) => e.role === "textbox");
      if (!input) throw new Error("controlled-input not found");
      await kernel.fill(input.target, value);
      const obs2 = await kernel.observe(page.pageId);
      const refreshed = obs2.elements.find((e) => e.role === "textbox");
      if (refreshed?.value !== value) {
        throw new Error(`fill lost value across re-render: expected ${JSON.stringify(value)}, got ${JSON.stringify(refreshed?.value)}`);
      }
      rec.pass(name, { value });
    } catch (err) {
      rec.fail(name, err, { value, method: "fill" });
    }
  }

  for (let i = 0; i < REPS_SEQUENTIAL; i++) {
    const name = `react-typeSequential-${i}`;
    const value = `seq${i}abc`;
    try {
      await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/b`);
      const obs = await kernel.observe(page.pageId);
      const input = obs.elements.find((e) => e.role === "textbox");
      if (!input) throw new Error("controlled-input not found");
      await kernel.typeSequential(input.target, value);
      const obs2 = await kernel.observe(page.pageId);
      const refreshed = obs2.elements.find((e) => e.role === "textbox");
      if (refreshed?.value !== value) {
        throw new Error(
          `typeSequential lost/garbled value across per-keystroke re-render: expected ${JSON.stringify(value)}, got ${JSON.stringify(refreshed?.value)}`
        );
      }
      rec.pass(name, { value });
    } catch (err) {
      rec.fail(name, err, { value, method: "typeSequential" });
    }
  }

  return rec.finish();
}

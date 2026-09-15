import type { BrowserKernel } from "../contracts/kernel.js";
import { FIXTURE_BASE, SuiteRecorder, type CandidateName, type SuiteResult } from "./harness.js";

const REPS = 50;

export async function run(kernel: BrowserKernel, candidate: CandidateName): Promise<SuiteResult> {
  const rec = new SuiteRecorder("stable_click", candidate);
  const page = await kernel.newPage();

  for (let i = 0; i < REPS; i++) {
    const name = `click-${i}`;
    try {
      await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/d`);
      const before = await kernel.readText(page.pageId, "click-log");
      if (before !== "no-clicks") throw new Error(`unexpected initial click-log state: ${before}`);

      const start = performance.now();
      const obs = await kernel.observe(page.pageId);
      const btn = obs.elements.find((e) => e.role === "button" && e.name === "Click Me A");
      if (!btn) throw new Error("target-btn not found in observation");
      await kernel.click(btn.target);
      const latency = performance.now() - start;

      const after = await kernel.readText(page.pageId, "click-log");
      if (after !== "clicked:0") throw new Error(`click did not take effect, click-log=${after}`);

      rec.pass(name, { after }, latency);
    } catch (err) {
      rec.fail(name, err);
    }
  }

  return rec.finish();
}

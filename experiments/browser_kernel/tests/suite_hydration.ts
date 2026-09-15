import type { BrowserKernel } from "../contracts/kernel.js";
import { FIXTURE_BASE, SuiteRecorder, sleep, type CandidateName, type SuiteResult } from "./harness.js";

const REPS_WAIT_THEN_FILL = 10;
const REPS_FILL_BEFORE_HYDRATION = 10;
const HYDRATION_WAIT_TIMEOUT_MS = 3000;
const HYDRATION_MAX_DELAY_MS = 1400; // fixture uses 900-1300ms

async function waitForHydration(kernel: BrowserKernel, pageId: string): Promise<void> {
  const deadline = Date.now() + HYDRATION_WAIT_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const status = await kernel.readText(pageId, "hydration-status");
    if (status === "hydrated") return;
    await sleep(60);
  }
  throw new Error("hydration did not complete within timeout");
}

export async function run(kernel: BrowserKernel, candidate: CandidateName): Promise<SuiteResult> {
  const rec = new SuiteRecorder("delayed_hydration", candidate);
  const page = await kernel.newPage();

  // Legitimate pattern: wait for the documented hydration-complete signal,
  // THEN fill, THEN verify via a fresh observation.
  for (let i = 0; i < REPS_WAIT_THEN_FILL; i++) {
    const name = `hydration-wait-then-fill-${i}`;
    const value = `posthydrate-${i}`;
    try {
      await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/c`);
      await waitForHydration(kernel, page.pageId);
      const obs = await kernel.observe(page.pageId);
      const input = obs.elements.find((e) => e.role === "textbox");
      if (!input) throw new Error("hydrate-input not found after hydration");
      await kernel.fill(input.target, value);
      const obs2 = await kernel.observe(page.pageId);
      const refreshed = obs2.elements.find((e) => e.role === "textbox");
      if (refreshed?.value !== value) throw new Error(`value mismatch after hydration-safe fill: ${refreshed?.value}`);
      rec.pass(name, { value });
    } catch (err) {
      rec.fail(name, err, { value });
    }
  }

  // Negative control: fill BEFORE hydration completes. The fixture's
  // hydration swap discards whatever was typed into the pre-hydration node.
  // "Pass" here means the kernel does NOT falsely persist/report the
  // pre-hydration value as the final state — either fill() itself reports a
  // mismatch, or a fresh post-hydration observation reveals the reset.
  for (let i = 0; i < REPS_FILL_BEFORE_HYDRATION; i++) {
    const name = `hydration-fill-before-ready-${i}`;
    const value = `prehydrate-${i}`;
    try {
      await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/c`);
      const obs = await kernel.observe(page.pageId);
      const input = obs.elements.find((e) => e.role === "textbox");
      if (!input) throw new Error("hydrate-input not found before hydration");

      let immediateMismatch = false;
      try {
        await kernel.fill(input.target, value);
      } catch (err: any) {
        if (err?.code === "INPUT_VALUE_MISMATCH") immediateMismatch = true;
        else throw err;
      }

      await sleep(HYDRATION_MAX_DELAY_MS);
      const obs2 = await kernel.observe(page.pageId);
      const refreshed = obs2.elements.find((e) => e.role === "textbox");
      const finalValue = refreshed?.value ?? "";
      const falselyPersisted = !immediateMismatch && finalValue === value;

      if (falselyPersisted) {
        throw new Error(
          `HYDRATION_RESET not detected: kernel reported success and the value ${JSON.stringify(value)} incorrectly appears to have survived hydration`
        );
      }
      rec.pass(name, { immediateMismatch, finalValue });
    } catch (err) {
      rec.fail(name, err, { value });
    }
  }

  return rec.finish();
}

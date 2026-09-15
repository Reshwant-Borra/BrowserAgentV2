import type { BrowserKernel, Target } from "../contracts/kernel.js";
import { FIXTURE_BASE, SuiteRecorder, sleep, type CandidateName, type SuiteResult } from "./harness.js";
import { fireControl, newSession, withSid } from "./controlHelper.js";

const REPS = 30;
const SCENARIOS = ["rerender", "navigate", "spa", "domreplace"] as const;
type Scenario = (typeof SCENARIOS)[number];

async function captureTarget(kernel: BrowserKernel, pageId: string, sid: string, scenario: Scenario): Promise<Target> {
  await kernel.navigate(pageId, withSid(`${FIXTURE_BASE}/fixtures/d`, sid));
  const obs = await kernel.observe(pageId);
  if (scenario === "rerender") {
    const el = obs.elements.find((e) => e.role === "button" && e.name === "Click Me A");
    if (!el) throw new Error("target-btn not found");
    return el.target;
  }
  if (scenario === "navigate") {
    const el = obs.elements.find((e) => e.role === "button" && e.name === "Click Me A");
    if (!el) throw new Error("target-btn not found");
    return el.target;
  }
  if (scenario === "spa") {
    const el = obs.elements.find((e) => e.role === "button" && e.name === "SPA Home Button");
    if (!el) throw new Error("spa-btn-home not found");
    return el.target;
  }
  // domreplace
  const el = obs.elements.find((e) => e.name === "Item One");
  if (!el) throw new Error("item-1 not found");
  return el.target;
}

export async function run(kernel: BrowserKernel, candidate: CandidateName): Promise<SuiteResult> {
  const rec = new SuiteRecorder("stale_target_rejection", candidate);
  const page = await kernel.newPage();

  for (let i = 0; i < REPS; i++) {
    const scenario = SCENARIOS[i % SCENARIOS.length];
    const name = `stale-${scenario}-${i}`;
    const sid = newSession();
    try {
      const staleTarget = await captureTarget(kernel, page.pageId, sid, scenario);

      const eventName = `stale_${scenario}`;
      await fireControl(sid, eventName);
      await sleep(scenario === "navigate" ? 700 : 400);

      let rejected = false;
      let errorCode: string | undefined;
      try {
        await kernel.click(staleTarget);
      } catch (err: any) {
        rejected = true;
        errorCode = err?.code;
      }

      if (!rejected) {
        throw new Error("stale target was NOT rejected — action against a superseded element silently proceeded");
      }
      if (errorCode !== "TARGET_STALE") {
        throw new Error(`stale target rejected but with unexpected error code ${errorCode} (expected TARGET_STALE)`);
      }
      rec.pass(name, { scenario, errorCode });
    } catch (err) {
      rec.fail(name, err, { scenario });
    }
  }

  return rec.finish();
}

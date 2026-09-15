import type { BrowserKernel } from "../contracts/kernel.js";
import { FIXTURE_BASE, SuiteRecorder, type CandidateName, type SuiteResult } from "./harness.js";

const SCENARIOS = ["blank_link", "window_open", "delayed_popup", "nested_popup"] as const;
type Scenario = (typeof SCENARIOS)[number];
const REPS_PER_SCENARIO = 5; // 4 scenarios * 5 = 20

export async function run(kernel: BrowserKernel, candidate: CandidateName): Promise<SuiteResult> {
  const rec = new SuiteRecorder("popup_capture", candidate);
  const main = await kernel.newPage();

  for (let i = 0; i < REPS_PER_SCENARIO; i++) {
    for (const scenario of SCENARIOS) {
      const name = `popup-${scenario}-${i}`;
      try {
        await kernel.navigate(main.pageId, `${FIXTURE_BASE}/fixtures/e`);
        const obs = await kernel.observe(main.pageId);

        const elByName: Record<Scenario, string> = {
          blank_link: "target=_blank link",
          window_open: "window.open",
          delayed_popup: "Delayed popup (800ms)",
          nested_popup: "Open popup with its own nested-popup button",
        };
        const el = obs.elements.find((e) => e.name === elByName[scenario]);
        if (!el) throw new Error(`element for scenario ${scenario} not found`);

        await kernel.click(el.target);
        const timeoutMs = scenario === "delayed_popup" ? 3000 : 2000;
        const popup = await kernel.waitForNewPage(timeoutMs);
        if (!popup) throw new Error("no new page detected");
        if (popup.owner !== "AGENT") throw new Error(`expected AGENT owner, got ${popup.owner}`);

        if (scenario === "nested_popup") {
          const childObs = await kernel.observe(popup.pageId);
          const nestedBtn = childObs.elements.find((e) => e.name === "Open nested popup");
          if (!nestedBtn) throw new Error("nested popup trigger button not found on child page");
          await kernel.click(nestedBtn.target);
          const nested = await kernel.waitForNewPage(2000);
          if (!nested) throw new Error("nested popup not detected");
          if (nested.owner !== "AGENT") throw new Error(`nested popup expected AGENT owner, got ${nested.owner}`);
        }

        rec.pass(name, { popupUrl: popup.url, owner: popup.owner });
      } catch (err) {
        rec.fail(name, err, { scenario });
      }
    }
  }

  return rec.finish();
}

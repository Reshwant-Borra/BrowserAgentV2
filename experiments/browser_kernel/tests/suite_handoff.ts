import type { BrowserKernel } from "../contracts/kernel.js";
import { FIXTURE_BASE, SuiteRecorder, sleep, type CandidateName, type SuiteResult } from "./harness.js";
import { fireControl, newSession, withSid } from "./controlHelper.js";

// Automated simulation of human handoff: an out-of-band control-channel
// event mutates the page exactly like a real human completing a login would
// (DOM replacement, optional new tab) WITHOUT going through the kernel under
// test — see fixtures/controlChannel.ts for the rationale. This exercises
// the real browser-level events (navigation/DOM-replace/window.open) the
// kernel must react to; a literal OS-level mouse/keyboard pass would not
// exercise anything further since fixture I's login button only toggles
// in-page text, not a real auth flow.
const REPS = 5;

export async function run(kernel: BrowserKernel, candidate: CandidateName): Promise<SuiteResult> {
  const rec = new SuiteRecorder("human_handoff_resume", candidate);
  const page = await kernel.newPage();

  for (let i = 0; i < REPS; i++) {
    const withPopup = i % 2 === 0;
    const name = `handoff-${withPopup ? "popup" : "dom-replace"}-${i}`;
    const sid = newSession();
    try {
      await kernel.navigate(page.pageId, withSid(`${FIXTURE_BASE}/fixtures/i`, sid));
      const preObs = await kernel.observe(page.pageId);
      const usernameField = preObs.elements.find((e) => e.name === "username" || e.role === "textbox");
      if (!usernameField) throw new Error("username field not found pre-handoff");

      // Simulate: agent pauses here (WAITING_FOR_USER in production).
      await fireControl(sid, "complete_login", { openPopup: withPopup });
      await sleep(500);

      // Invariant: ALL old target references are considered invalid.
      let staleRejected = false;
      let staleCode: string | undefined;
      try {
        await kernel.click(usernameField.target);
      } catch (err: any) {
        staleRejected = true;
        staleCode = err?.code;
      }
      if (!staleRejected) throw new Error("old pre-handoff target was NOT invalidated after resume");
      if (staleCode !== "TARGET_STALE") throw new Error(`expected TARGET_STALE, got ${staleCode}`);

      // Invariant: fresh observation discovers post-handoff content.
      const postObs = await kernel.observe(page.pageId);
      const dashboardBtn = postObs.elements.find((e) => e.name === "Dashboard Button");
      if (!dashboardBtn) throw new Error("post-handoff dashboard content not discovered via fresh observation");

      // Invariant: tabs/pages are rediscovered if a popup appeared during handoff.
      if (withPopup) {
        const popup = await kernel.waitForNewPage(2500);
        if (!popup) throw new Error("post-login popup not rediscovered");
      }

      // Invariant: execution safely continues — a normal action on the
      // fresh target succeeds.
      await kernel.click(dashboardBtn.target);

      rec.pass(name, { withPopup, staleCode });
    } catch (err) {
      rec.fail(name, err, { withPopup });
    }
  }

  return rec.finish();
}

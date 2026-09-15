import type { BrowserKernel } from "../contracts/kernel.js";
import { FIXTURE_BASE, SuiteRecorder, sleep, type CandidateName, type SuiteResult } from "./harness.js";
import { fireControl, newSession, withSid } from "./controlHelper.js";

export async function run(kernel: BrowserKernel, candidate: CandidateName): Promise<SuiteResult> {
  const rec = new SuiteRecorder("frame_targeting", candidate);
  const page = await kernel.newPage();

  // 1. Fill + click inside the first same-origin iframe (label A), 6x
  for (let i = 0; i < 6; i++) {
    const name = `frame-a-${i}`;
    try {
      await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/f`);
      const obs = await kernel.observe(page.pageId);
      const input = obs.elements.find((e) => e.role === "textbox" && e.target.framePath.some((f) => f.startsWith("iframe:")) && e.target.framePath.length === 2);
      if (!input) throw new Error("frame A input not found");
      const value = `frameA-${i}`;
      await kernel.fill(input.target, value);
      const obs2 = await kernel.observe(page.pageId);
      const refreshed = obs2.elements.find((e) => e.target.refToken === input.target.refToken || (e.target.framePath.join(">") === input.target.framePath.join(">") && e.role === "textbox"));
      if (refreshed?.value !== value) throw new Error(`frame A fill mismatch: got ${refreshed?.value}`);
      rec.pass(name, { value, framePath: input.target.framePath });
    } catch (err) {
      rec.fail(name, err);
    }
  }

  // 2. Fill inside the doubly-nested iframe (Outer > Nested), 6x
  for (let i = 0; i < 6; i++) {
    const name = `frame-nested-${i}`;
    try {
      await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/f`);
      const obs = await kernel.observe(page.pageId);
      const nestedInput = obs.elements.find((e) => e.role === "textbox" && e.target.framePath.length === 3);
      if (!nestedInput) throw new Error("nested frame input not found");
      const value = `nested-${i}`;
      await kernel.fill(nestedInput.target, value);
      const obs2 = await kernel.observe(page.pageId);
      const refreshed = obs2.elements.find((e) => e.target.framePath.length === 3 && e.role === "textbox");
      if (refreshed?.value !== value) throw new Error(`nested frame fill mismatch: got ${refreshed?.value}`);
      rec.pass(name, { value, framePath: nestedInput.target.framePath });
    } catch (err) {
      rec.fail(name, err);
    }
  }

  // 3. No cross-talk between sibling frames with identically-named controls, 4x
  for (let i = 0; i < 4; i++) {
    const name = `frame-sibling-no-crosstalk-${i}`;
    try {
      await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/f`);
      let obs = await kernel.observe(page.pageId);
      const depth2Inputs = obs.elements.filter((e) => e.role === "textbox" && e.target.framePath.length === 2);
      if (depth2Inputs.length < 2) throw new Error(`expected 2 depth-2 frame inputs, found ${depth2Inputs.length}`);
      const [first, second] = depth2Inputs;
      const value = `crosstalk-${i}`;
      await kernel.fill(first.target, value);
      obs = await kernel.observe(page.pageId);
      const refreshedFirst = obs.elements.find((e) => e.target.framePath.join(">") === first.target.framePath.join(">") && e.role === "textbox");
      const refreshedSecond = obs.elements.find((e) => e.target.framePath.join(">") === second.target.framePath.join(">") && e.role === "textbox");
      if (refreshedFirst?.value !== value) throw new Error("target frame did not receive the value");
      if (refreshedSecond?.value === value) throw new Error("sibling frame leaked the value — cross-frame contamination");
      rec.pass(name, { targetFrame: first.target.framePath, siblingFrame: second.target.framePath });
    } catch (err) {
      rec.fail(name, err);
    }
  }

  // 4. Frame replacement (src change) invalidates the old target, 4x
  for (let i = 0; i < 4; i++) {
    const name = `frame-replace-stale-${i}`;
    const sid = newSession();
    try {
      await kernel.navigate(page.pageId, withSid(`${FIXTURE_BASE}/fixtures/f`, sid));
      const obs = await kernel.observe(page.pageId);
      const oldTarget = obs.elements.find((e) => e.role === "button" && e.name === "Frame Button A");
      if (!oldTarget) throw new Error("Frame Button A not found");
      await fireControl(sid, "replace_frame");
      await sleep(500);
      let rejected = false;
      let code: string | undefined;
      try {
        await kernel.click(oldTarget.target);
      } catch (err: any) {
        rejected = true;
        code = err?.code;
      }
      if (!rejected) throw new Error("stale frame target was not rejected");
      if (code !== "TARGET_STALE") throw new Error(`expected TARGET_STALE, got ${code}`);
      rec.pass(name, { code });
    } catch (err) {
      rec.fail(name, err);
    }
  }

  return rec.finish();
}

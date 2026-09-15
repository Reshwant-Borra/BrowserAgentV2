import type { BrowserKernel } from "../contracts/kernel.js";
import { FIXTURE_BASE, SuiteRecorder, type CandidateName, type SuiteResult } from "./harness.js";
import { fireControl, newSession, withSid } from "./controlHelper.js";

export async function run(kernel: BrowserKernel, candidate: CandidateName): Promise<SuiteResult> {
  const rec = new SuiteRecorder("page_ownership", candidate);

  // 1. Pages present before any explicit agent page creation must not be AGENT.
  try {
    const initial = await kernel.listPages();
    const bad = initial.filter((p) => p.owner === "AGENT");
    if (bad.length > 0) throw new Error(`pre-existing page(s) incorrectly marked AGENT: ${JSON.stringify(bad)}`);
    rec.pass("initial-pages-not-agent", { count: initial.length });
  } catch (err) {
    rec.fail("initial-pages-not-agent", err);
  }

  // 2. Explicit newPage() -> AGENT, 5x
  for (let i = 0; i < 5; i++) {
    const name = `newpage-agent-${i}`;
    try {
      const p = await kernel.newPage(`${FIXTURE_BASE}/fixtures/a`);
      if (p.owner !== "AGENT") throw new Error(`expected AGENT, got ${p.owner}`);
      rec.pass(name, { pageId: p.pageId });
    } catch (err) {
      rec.fail(name, err);
    }
  }

  // 3. Popup spawned by an agent click on an agent page -> AGENT, 5x
  const main = await kernel.newPage();
  for (let i = 0; i < 5; i++) {
    const name = `agent-popup-agent-${i}`;
    try {
      await kernel.navigate(main.pageId, `${FIXTURE_BASE}/fixtures/l`);
      const obs = await kernel.observe(main.pageId);
      const link = obs.elements.find((e) => e.name === "Agent-triggered new tab");
      if (!link) throw new Error("agent-open-tab-link not found");
      await kernel.click(link.target);
      const popup = await kernel.waitForNewPage(2000);
      if (!popup) throw new Error("popup not detected");
      if (popup.owner !== "AGENT") throw new Error(`expected AGENT, got ${popup.owner}`);
      rec.pass(name, { pageId: popup.pageId });
    } catch (err) {
      rec.fail(name, err);
    }
  }

  // 4. Out-of-band tab creation (simulated human, no agent action in flight) -> must NOT be AGENT, 5x
  for (let i = 0; i < 5; i++) {
    const name = `external-tab-not-agent-${i}`;
    const sid = newSession();
    try {
      await kernel.navigate(main.pageId, withSid(`${FIXTURE_BASE}/fixtures/l`, sid));
      // Let enough time pass since the last agent action that the bounded
      // attribution window (1500ms) has definitely elapsed before the
      // external actor opens its tab, so this is an unambiguous negative case.
      await new Promise((r) => setTimeout(r, 1800));
      await fireControl(sid, "external_open_tab");
      const popup = await kernel.waitForNewPage(3000);
      if (!popup) throw new Error("externally-opened tab not detected");
      if (popup.owner === "AGENT") throw new Error("externally-opened tab was incorrectly marked AGENT");
      rec.pass(name, { pageId: popup.pageId, owner: popup.owner });
    } catch (err) {
      rec.fail(name, err);
    }
  }

  // 5. closePage() must refuse to close a non-AGENT page, 2x
  for (let i = 0; i < 2; i++) {
    const name = `close-refuses-non-agent-${i}`;
    try {
      const pages = await kernel.listPages();
      const nonAgent = pages.find((p) => p.owner !== "AGENT" && !p.isClosed);
      if (!nonAgent) throw new Error("no non-agent page available to test against");
      let threw = false;
      let code: string | undefined;
      try {
        await kernel.closePage(nonAgent.pageId);
      } catch (err: any) {
        threw = true;
        code = err?.code;
      }
      if (!threw) throw new Error("closePage on non-AGENT page did not throw");
      if (code !== "OWNERSHIP_VIOLATION") throw new Error(`expected OWNERSHIP_VIOLATION, got ${code}`);
      rec.pass(name, { targetPageId: nonAgent.pageId });
    } catch (err) {
      rec.fail(name, err);
    }
  }

  // 6. closePage() succeeds for an AGENT page, 2x
  for (let i = 0; i < 2; i++) {
    const name = `close-succeeds-agent-${i}`;
    try {
      const p = await kernel.newPage(`${FIXTURE_BASE}/fixtures/a`);
      await kernel.closePage(p.pageId);
      const after = await kernel.listPages();
      const found = after.find((x) => x.pageId === p.pageId);
      if (!found?.isClosed) throw new Error("page not marked closed after closePage()");
      rec.pass(name, { pageId: p.pageId });
    } catch (err) {
      rec.fail(name, err);
    }
  }

  return rec.finish();
}

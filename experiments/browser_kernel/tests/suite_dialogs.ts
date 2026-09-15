import type { BrowserKernel } from "../contracts/kernel.js";
import { FIXTURE_BASE, SuiteRecorder, type CandidateName, type SuiteResult } from "./harness.js";

const REPS_PER_TYPE = 10;

async function triggerAndCapture(kernel: BrowserKernel, pageId: string, targetName: string) {
  const obs = await kernel.observe(pageId);
  const el = obs.elements.find((e) => e.name === targetName);
  if (!el) throw new Error(`${targetName} button not found`);
  try {
    await kernel.click(el.target);
  } catch (err: any) {
    if (err?.code !== "DIALOG_OPEN") throw err; // MCP surfaces the dialog synchronously via the click response
  }
  const dialog = await kernel.waitForDialog(3000);
  if (!dialog) throw new Error("dialog was not detected via waitForDialog");
  return dialog;
}

export async function run(kernel: BrowserKernel, candidate: CandidateName): Promise<SuiteResult> {
  const rec = new SuiteRecorder("dialog_handling", candidate);
  const page = await kernel.newPage();

  for (let i = 0; i < REPS_PER_TYPE; i++) {
    const name = `dialog-alert-${i}`;
    try {
      await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/g`);
      const dialog = await triggerAndCapture(kernel, page.pageId, "Alert");
      if (dialog.kind !== "alert") throw new Error(`expected alert kind, got ${dialog.kind}`);
      await kernel.handleDialog(true);
      const result = await kernel.readText(page.pageId, "alert-result");
      if (result !== "dismissed") throw new Error(`unexpected alert-result: ${result}`);
      rec.pass(name, { dialog });
    } catch (err) {
      rec.fail(name, err);
    }
  }

  for (let i = 0; i < REPS_PER_TYPE; i++) {
    const name = `dialog-confirm-${i}`;
    const accept = i % 2 === 0;
    try {
      await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/g`);
      const dialog = await triggerAndCapture(kernel, page.pageId, "Confirm");
      if (dialog.kind !== "confirm") throw new Error(`expected confirm kind, got ${dialog.kind}`);
      await kernel.handleDialog(accept);
      const result = await kernel.readText(page.pageId, "confirm-result");
      const expected = accept ? "accepted" : "dismissed";
      if (result !== expected) throw new Error(`expected confirm-result=${expected}, got ${result}`);
      rec.pass(name, { accept, dialog });
    } catch (err) {
      rec.fail(name, err, { accept });
    }
  }

  for (let i = 0; i < REPS_PER_TYPE; i++) {
    const name = `dialog-prompt-${i}`;
    const accept = i % 2 === 0;
    const promptText = `answer-${i}`;
    try {
      await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/g`);
      const dialog = await triggerAndCapture(kernel, page.pageId, "Prompt");
      if (dialog.kind !== "prompt") throw new Error(`expected prompt kind, got ${dialog.kind}`);
      await kernel.handleDialog(accept, promptText);
      const result = await kernel.readText(page.pageId, "prompt-result");
      const expected = accept ? `value:${promptText}` : "null";
      if (result !== expected) throw new Error(`expected prompt-result=${expected}, got ${result}`);
      rec.pass(name, { accept, dialog });
    } catch (err) {
      rec.fail(name, err, { accept });
    }
  }

  return rec.finish();
}

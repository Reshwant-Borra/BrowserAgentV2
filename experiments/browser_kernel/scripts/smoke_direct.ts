import { DirectPlaywrightKernel } from "../adapters/direct_playwright/directKernel.js";
import path from "node:path";
import os from "node:os";
import fs from "node:fs";

const BASE = process.env.FIXTURE_BASE ?? "http://localhost:4173";

async function main() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "bk-smoke-"));
  const kernel = new DirectPlaywrightKernel();
  await kernel.start({ userDataDir: path.join(dir, "profile"), headless: true, downloadsDir: path.join(dir, "downloads") });

  const pages = await kernel.listPages();
  console.log("initial pages:", pages.map((p) => ({ id: p.pageId, owner: p.owner, url: p.url })));

  const page = await kernel.newPage(`${BASE}/fixtures/a`);
  console.log("new page owner:", page.owner);

  let obs = await kernel.observe(page.pageId);
  console.log("elements found:", obs.elements.length, obs.elements.map((e) => e.name).slice(0, 5));

  const input = obs.elements.find((e) => e.name === "" && e.role === "textbox");
  const plain = obs.elements.find((e) => e.value === "" && e.role === "textbox");
  console.log("plain input target:", plain?.target.debugLabel);

  if (plain) {
    await kernel.fill(plain.target, "hello world");
    console.log("fill ok");
  }

  obs = await kernel.observe(page.pageId);
  const refilled = obs.elements.find((e) => e.value === "hello world");
  console.log("value verified after fresh observe:", !!refilled);

  // stale target check: try reusing the OLD plain target after refresh observation
  try {
    if (plain) await kernel.fill(plain.target, "should fail");
    console.log("STALE CHECK FAILED: old target was accepted");
  } catch (err: any) {
    console.log("stale check ok, error code:", err.code);
  }

  await kernel.stop();
  console.log("SMOKE TEST DONE");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

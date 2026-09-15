import crypto from "node:crypto";
import type { BrowserKernel } from "../contracts/kernel.js";
import { FIXTURE_BASE, SuiteRecorder, type CandidateName, type SuiteResult } from "./harness.js";

function expectedSha256(name: string, size: number): string {
  const seed = crypto.createHash("sha256").update(name).digest();
  const content = Buffer.alloc(size);
  for (let i = 0; i < size; i++) content[i] = seed[i % seed.length];
  return crypto.createHash("sha256").update(content).digest("hex");
}

const REPORT_SHA = expectedSha256("report.txt", 2048);
const SLOW_SHA = expectedSha256("slow.bin", 500000);

export async function run(kernel: BrowserKernel, candidate: CandidateName): Promise<SuiteResult> {
  const rec = new SuiteRecorder("downloads", candidate);
  const page = await kernel.newPage();

  for (let i = 0; i < 4; i++) {
    const name = `download-report-${i}`;
    try {
      await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/j`);
      const obs = await kernel.observe(page.pageId);
      const link = obs.elements.find((e) => e.name.includes("report.txt"));
      if (!link) throw new Error("download-link not found");
      const start = performance.now();
      const result = await kernel.clickAndWaitForDownload(link.target, 10000);
      const latency = performance.now() - start;
      if (result.sha256 !== REPORT_SHA) throw new Error(`sha256 mismatch: expected ${REPORT_SHA}, got ${result.sha256}`);
      if (result.byteSize !== 2048) throw new Error(`byte size mismatch: expected 2048, got ${result.byteSize}`);
      rec.pass(name, { path: result.savedPath }, latency);
    } catch (err) {
      rec.fail(name, err);
    }
  }

  for (let i = 0; i < 3; i++) {
    const name = `download-slow-${i}`;
    try {
      await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/j`);
      const obs = await kernel.observe(page.pageId);
      const link = obs.elements.find((e) => e.name.includes("slow.bin"));
      if (!link) throw new Error("download-slow-link not found");
      const start = performance.now();
      const result = await kernel.clickAndWaitForDownload(link.target, 10000);
      const latency = performance.now() - start;
      if (result.sha256 !== SLOW_SHA) throw new Error(`sha256 mismatch for slow.bin`);
      if (result.byteSize !== 500000) throw new Error(`byte size mismatch: expected 500000, got ${result.byteSize}`);
      rec.pass(name, { path: result.savedPath }, latency);
    } catch (err) {
      rec.fail(name, err);
    }
  }

  for (let i = 0; i < 3; i++) {
    const name = `download-fail-${i}`;
    try {
      await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/j`);
      const obs = await kernel.observe(page.pageId);
      const link = obs.elements.find((e) => e.name.includes("broken.bin"));
      if (!link) throw new Error("download-fail-link not found");
      let threw = false;
      let code: string | undefined;
      try {
        await kernel.clickAndWaitForDownload(link.target, 8000);
      } catch (err: any) {
        threw = true;
        code = err?.code;
      }
      if (!threw) throw new Error("expected download failure to be detected, but clickAndWaitForDownload succeeded");
      if (code !== "DOWNLOAD_FAILED") throw new Error(`expected DOWNLOAD_FAILED, got ${code}`);
      rec.pass(name, { code });
    } catch (err) {
      rec.fail(name, err);
    }
  }

  return rec.finish();
}

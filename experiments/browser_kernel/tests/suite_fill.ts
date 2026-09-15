import type { BrowserKernel } from "../contracts/kernel.js";
import { FIXTURE_BASE, SuiteRecorder, type CandidateName, type SuiteResult } from "./harness.js";

const REPS = 50;
const SAMPLE_VALUES = [
  "hello world",
  "The quick brown fox",
  "user+test@example.com",
  "  leading and trailing  ",
  "line1\ttabbed",
  "special !@#$%^&*()_+-=[]{}",
  "unicode: café ☃ 中文",
  "12345",
  "a",
  "a rather long string to make sure nothing truncates it unexpectedly at some arbitrary boundary",
];

export async function run(kernel: BrowserKernel, candidate: CandidateName): Promise<SuiteResult> {
  const rec = new SuiteRecorder("exact_fill", candidate);
  const page = await kernel.newPage();

  for (let i = 0; i < REPS; i++) {
    const name = `fill-${i}`;
    const value = SAMPLE_VALUES[i % SAMPLE_VALUES.length] + `#${i}`;
    try {
      await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/a`);
      let obs = await kernel.observe(page.pageId);
      const target = i % 2 === 0
        ? obs.elements.find((e) => e.name === "Plain input")
        : obs.elements.find((e) => e.name === "Prefilled (clear + replace)");
      if (!target) throw new Error("input target not found");

      const start = performance.now();
      await kernel.fill(target.target, value);
      const latency = performance.now() - start;

      obs = await kernel.observe(page.pageId);
      const refreshed = i % 2 === 0
        ? obs.elements.find((e) => e.name === "Plain input")
        : obs.elements.find((e) => e.name === "Prefilled (clear + replace)");
      if (refreshed?.value !== value) {
        throw new Error(`value mismatch: expected ${JSON.stringify(value)}, got ${JSON.stringify(refreshed?.value)}`);
      }
      rec.pass(name, { value }, latency);
    } catch (err) {
      rec.fail(name, err, { value });
    }
  }

  return rec.finish();
}

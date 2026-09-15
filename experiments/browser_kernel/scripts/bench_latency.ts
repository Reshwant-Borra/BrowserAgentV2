// Dedicated latency micro-benchmark, run separately from the correctness
// suites so a slow-but-correct action never gets misread as a failure and a
// verification failure never pollutes a latency number. Each primitive is
// measured in isolation, N times, against a fresh kernel instance.
import fs from "node:fs";
import path from "node:path";
import { freshDirs, kernelFactory, median, percentile, FIXTURE_BASE, type CandidateName } from "../tests/harness.js";

const N = 20;

function stats(samples: number[]) {
  return { medianMs: Math.round(median(samples)), p95Ms: Math.round(percentile(samples, 95)), n: samples.length };
}

async function benchStartup(candidate: CandidateName): Promise<number[]> {
  const samples: number[] = [];
  for (let i = 0; i < N; i++) {
    const opts = freshDirs(`bench-startup-${candidate}-${i}`);
    const kernel = kernelFactory(candidate);
    const start = performance.now();
    await kernel.start(opts);
    samples.push(performance.now() - start);
    await kernel.stop().catch(() => {});
  }
  return samples;
}

async function benchSteadyState(candidate: CandidateName) {
  const opts = freshDirs(`bench-steady-${candidate}`);
  const kernel = kernelFactory(candidate);
  await kernel.start(opts);
  const page = await kernel.newPage(`${FIXTURE_BASE}/fixtures/a`);

  const observeSamples: number[] = [];
  const clickSamples: number[] = [];
  const fillSamples: number[] = [];
  const switchSamples: number[] = [];

  for (let i = 0; i < N; i++) {
    await kernel.navigate(page.pageId, `${FIXTURE_BASE}/fixtures/a`);

    let start = performance.now();
    let obs = await kernel.observe(page.pageId);
    observeSamples.push(performance.now() - start);

    const input = obs.elements.find((e) => e.name === "Plain input");
    if (input) {
      start = performance.now();
      await kernel.fill(input.target, `bench-${i}`);
      fillSamples.push(performance.now() - start);
    }

    obs = await kernel.observe(page.pageId);
    const link = obs.elements.find((e) => e.role === "link" && e.name === "index");
    if (link) {
      start = performance.now();
      await kernel.click(link.target);
      clickSamples.push(performance.now() - start);
    }
  }

  const page2 = await kernel.newPage(`${FIXTURE_BASE}/fixtures/a`);
  for (let i = 0; i < N; i++) {
    const start = performance.now();
    await kernel.switchActivePage(i % 2 === 0 ? page.pageId : page2.pageId);
    switchSamples.push(performance.now() - start);
  }

  await kernel.stop().catch(() => {});
  return { observeSamples, clickSamples, fillSamples, switchSamples };
}

async function main() {
  const candidates: CandidateName[] = ["direct_playwright", "mcp"];
  const results: Record<string, Record<string, ReturnType<typeof stats>>> = {};

  for (const candidate of candidates) {
    console.log(`\n=== benchmarking ${candidate} ===`);
    const startup = await benchStartup(candidate);
    console.log("startup", stats(startup));
    const { observeSamples, clickSamples, fillSamples, switchSamples } = await benchSteadyState(candidate);
    console.log("observe", stats(observeSamples));
    console.log("click", stats(clickSamples));
    console.log("fill", stats(fillSamples));
    console.log("switchActivePage", stats(switchSamples));

    results[candidate] = {
      startup: stats(startup),
      observe: stats(observeSamples),
      click: stats(clickSamples),
      fill: stats(fillSamples),
      switchActivePage: stats(switchSamples),
    };
  }

  const outPath = path.resolve(import.meta.dirname, "..", "results", "latency.json");
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2));
  console.log(`\nwritten to ${outPath}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

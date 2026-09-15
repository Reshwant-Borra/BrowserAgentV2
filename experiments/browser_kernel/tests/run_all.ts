import fs from "node:fs";
import path from "node:path";
import {
  freshDirs,
  kernelFactory,
  median,
  percentile,
  type CandidateName,
  type SuiteResult,
} from "./harness.js";
import * as suiteClick from "./suite_click.js";
import * as suiteFill from "./suite_fill.js";
import * as suiteStale from "./suite_stale.js";
import * as suitePopup from "./suite_popup.js";
import * as suiteOwnership from "./suite_ownership.js";
import * as suiteFrame from "./suite_frame.js";
import * as suitePersistence from "./suite_persistence.js";
import * as suiteReactTyping from "./suite_react_typing.js";
import * as suiteHydration from "./suite_hydration.js";
import * as suiteDialogs from "./suite_dialogs.js";
import * as suiteDownloads from "./suite_downloads.js";
import * as suiteHandoff from "./suite_handoff.js";
import * as suiteCrashReconnect from "./suite_crash_reconnect.js";

const SINGLE_KERNEL_SUITES = [
  suiteClick,
  suiteFill,
  suiteStale,
  suitePopup,
  suiteOwnership,
  suiteFrame,
  suiteReactTyping,
  suiteHydration,
  suiteDialogs,
  suiteDownloads,
  suiteHandoff,
] as const;

const OWN_LIFECYCLE_SUITES = [suitePersistence, suiteCrashReconnect] as const;

async function runCandidate(candidate: CandidateName): Promise<SuiteResult[]> {
  const results: SuiteResult[] = [];

  for (const suite of SINGLE_KERNEL_SUITES) {
    console.log(`\n=== [${candidate}] ${suite.run.name} ===`);
    const opts = freshDirs(`${candidate}-suite`);
    const kernel = kernelFactory(candidate);
    try {
      await kernel.start(opts);
      const result = (await (suite.run as any)(kernel, candidate)) as SuiteResult;
      results.push(result);
      console.log(`  ${result.suite}: ${result.passed}/${result.total} passed`);
      if (result.passed < result.total) {
        for (const c of result.cases.filter((c) => !c.passed)) {
          console.log(`    FAIL ${c.name}: [${c.errorCode ?? "?"}] ${c.errorMessage}`);
        }
      }
    } catch (err) {
      console.error(`  SUITE CRASHED: ${(err as Error).message}`);
      results.push({
        suite: suite.run.name,
        candidate,
        passed: 0,
        total: 0,
        cases: [{ name: "suite-crash", passed: false, errorMessage: String(err) }],
        latenciesMs: [],
        startedAt: new Date().toISOString(),
        finishedAt: new Date().toISOString(),
      });
    } finally {
      await kernel.stop().catch(() => {});
    }
  }

  for (const suite of OWN_LIFECYCLE_SUITES) {
    console.log(`\n=== [${candidate}] ${suite.run.name} ===`);
    try {
      const result = (await (suite.run as any)(candidate)) as SuiteResult;
      results.push(result);
      console.log(`  ${result.suite}: ${result.passed}/${result.total} passed`);
      if (result.passed < result.total) {
        for (const c of result.cases.filter((c) => !c.passed)) {
          console.log(`    FAIL ${c.name}: [${c.errorCode ?? "?"}] ${c.errorMessage}`);
        }
      }
    } catch (err) {
      console.error(`  SUITE CRASHED: ${(err as Error).message}`);
      results.push({
        suite: suite.run.name,
        candidate,
        passed: 0,
        total: 0,
        cases: [{ name: "suite-crash", passed: false, errorMessage: String(err) }],
        latenciesMs: [],
        startedAt: new Date().toISOString(),
        finishedAt: new Date().toISOString(),
      });
    }
  }

  return results;
}

async function main() {
  const arg = process.argv[2] ?? "both";
  const candidates: CandidateName[] = arg === "both" ? ["direct_playwright", "mcp"] : [arg as CandidateName];

  const resultsDir = path.resolve(import.meta.dirname, "..", "results");
  fs.mkdirSync(resultsDir, { recursive: true });

  for (const candidate of candidates) {
    const started = Date.now();
    const results = await runCandidate(candidate);
    const elapsedSec = ((Date.now() - started) / 1000).toFixed(1);

    const allLatencies = results.flatMap((r) => r.latenciesMs);
    const summary = {
      candidate,
      generatedAt: new Date().toISOString(),
      totalElapsedSec: Number(elapsedSec),
      overall: {
        passed: results.reduce((a, r) => a + r.passed, 0),
        total: results.reduce((a, r) => a + r.total, 0),
      },
      latency: {
        medianMs: median(allLatencies),
        p95Ms: percentile(allLatencies, 95),
        sampleCount: allLatencies.length,
      },
      suites: results,
    };

    const outPath = path.join(resultsDir, `${candidate}.json`);
    fs.writeFileSync(outPath, JSON.stringify(summary, null, 2));
    console.log(`\n>>> [${candidate}] ${summary.overall.passed}/${summary.overall.total} passed in ${elapsedSec}s`);
    console.log(`>>> written to ${outPath}`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

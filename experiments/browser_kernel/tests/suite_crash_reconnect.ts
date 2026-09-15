import { spawn, execSync, type ChildProcess } from "node:child_process";
import readline from "node:readline";
import path from "node:path";
import fs from "node:fs";
import os from "node:os";
import { FIXTURE_BASE, SuiteRecorder, sleep, type CandidateName, type SuiteResult } from "./harness.js";

const REPS = 10;
const READY_TIMEOUT_MS = 25000;
const CHECK_TIMEOUT_MS = 25000;
const WORKER_PATH = path.resolve(import.meta.dirname, "crashWorker.ts");
const TSX_BIN = path.resolve(import.meta.dirname, "..", "node_modules", ".bin", "tsx");

interface LaunchedWorker {
  proc: ChildProcess;
  waitForLine: (prefix: string, timeoutMs: number) => Promise<string | null>;
  kill: () => void;
}

function killTree(proc: ChildProcess): void {
  // `npx tsx <script>` spawns extra wrapper layers whose children are NOT
  // reliably reachable by signalling the top-level pid alone — confirmed via
  // `ps aux` showing the worker's node process AND its Chromium child still
  // running (and still holding the profile lock) after killing only that
  // top-level pid. Invoking tsx directly with `detached: true` makes this
  // process the leader of its own process group, so signalling the negative
  // pid reaches the whole tree (worker + browser) in one shot.
  if (!proc.pid) return;
  try {
    process.kill(-proc.pid, "SIGKILL");
  } catch {
    try {
      proc.kill("SIGKILL");
    } catch {
      // already gone
    }
  }
}

function launchWorker(candidate: CandidateName, userDataDir: string, downloadsDir: string, mode: "seed" | "check"): LaunchedWorker {
  const proc = spawn(TSX_BIN, [WORKER_PATH, candidate, userDataDir, downloadsDir, mode], {
    env: { ...process.env, FIXTURE_BASE },
    stdio: ["ignore", "pipe", "pipe"],
    detached: true,
  });
  const rl = readline.createInterface({ input: proc.stdout! });
  const lines: string[] = [];
  const waiters: Array<{ prefix: string; resolve: (line: string | null) => void }> = [];
  rl.on("line", (line) => {
    lines.push(line);
    for (const w of [...waiters]) {
      if (line.startsWith(w.prefix)) {
        waiters.splice(waiters.indexOf(w), 1);
        w.resolve(line);
      }
    }
  });
  const waitForLine = (prefix: string, timeoutMs: number): Promise<string | null> =>
    new Promise((resolve) => {
      const existing = lines.find((l) => l.startsWith(prefix));
      if (existing) return resolve(existing);
      const w = { prefix, resolve };
      waiters.push(w);
      setTimeout(() => {
        const idx = waiters.indexOf(w);
        if (idx !== -1) {
          waiters.splice(idx, 1);
          resolve(null);
        }
      }, timeoutMs);
    });
  return { proc, waitForLine, kill: () => killTree(proc) };
}

function killAnyProcessReferencing(marker: string): void {
  try {
    execSync(`pkill -9 -f "${marker}"`, { stdio: "ignore" });
  } catch {
    // no matching process — fine
  }
}

export async function run(candidate: CandidateName): Promise<SuiteResult> {
  const rec = new SuiteRecorder("crash_reconnect", candidate);

  for (let i = 0; i < REPS; i++) {
    const name = `crash-reconnect-${i}`;
    const rootDir = fs.mkdtempSync(path.join(os.tmpdir(), `bk-crash-${candidate}-${i}-`));
    const userDataDir = path.join(rootDir, "profile");
    const downloadsDir = path.join(rootDir, "downloads");
    try {
      const seedWorker = launchWorker(candidate, userDataDir, downloadsDir, "seed");
      const readyLine = await seedWorker.waitForLine("READY:", READY_TIMEOUT_MS);
      if (!readyLine) throw new Error("seed worker did not become READY in time");
      const seeded = JSON.parse(readyLine.slice("READY:".length));
      if (seeded.cookie !== "abc123" || seeded.local !== "xyz789") {
        throw new Error(`seed worker reported unexpected seeded values: ${readyLine}`);
      }

      // Abrupt kill: no SIGTERM, no clean shutdown handshake.
      seedWorker.kill();
      await sleep(300);

      const checkWorker = launchWorker(candidate, userDataDir, downloadsDir, "check");
      const start = performance.now();
      const resultLine = await Promise.race([
        checkWorker.waitForLine("RESULT:", CHECK_TIMEOUT_MS),
        checkWorker.waitForLine("ERROR:", CHECK_TIMEOUT_MS),
      ]);
      const reconnectLatency = performance.now() - start;
      checkWorker.kill();

      if (!resultLine) {
        throw new Error(`reconnect worker produced no result within ${CHECK_TIMEOUT_MS}ms (hang/timeout — likely profile lock contention)`);
      }
      if (resultLine.startsWith("ERROR:")) {
        throw new Error(`reconnect worker errored: ${resultLine}`);
      }
      const result = JSON.parse(resultLine.slice("RESULT:".length));
      if (result.cookie !== "abc123") throw new Error(`cookie did not survive crash+reconnect: ${result.cookie}`);
      if (result.local !== "xyz789") throw new Error(`localStorage did not survive crash+reconnect: ${result.local}`);

      rec.pass(name, { reconnectLatencyMs: reconnectLatency }, reconnectLatency);
    } catch (err) {
      rec.fail(name, err);
    } finally {
      // Best-effort cleanup so a leftover orphaned browser process (holding
      // this rep's profile lock) can't affect later reps.
      killAnyProcessReferencing(userDataDir);
      await sleep(300);
    }
  }

  return rec.finish();
}

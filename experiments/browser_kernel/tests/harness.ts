import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { DirectPlaywrightKernel } from "../adapters/direct_playwright/directKernel.js";
import { McpKernel } from "../adapters/mcp/mcpKernel.js";
import type { BrowserKernel, StartOptions } from "../contracts/kernel.js";

export const FIXTURE_BASE = process.env.FIXTURE_BASE ?? "http://localhost:4173";
export type CandidateName = "direct_playwright" | "mcp";

export function kernelFactory(candidate: CandidateName): BrowserKernel {
  return candidate === "direct_playwright" ? new DirectPlaywrightKernel() : new McpKernel();
}

export function freshDirs(prefix: string): StartOptions {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `bk-${prefix}-`));
  return {
    userDataDir: path.join(dir, "profile"),
    downloadsDir: path.join(dir, "downloads"),
    headless: true,
  };
}

export interface CaseResult {
  name: string;
  passed: boolean;
  errorCode?: string;
  errorMessage?: string;
  latencyMs?: number;
  detail?: Record<string, unknown>;
}

export interface SuiteResult {
  suite: string;
  candidate: CandidateName;
  passed: number;
  total: number;
  cases: CaseResult[];
  latenciesMs: number[];
  startedAt: string;
  finishedAt: string;
}

export class SuiteRecorder {
  private cases: CaseResult[] = [];
  private latencies: number[] = [];
  private startedAt = new Date().toISOString();

  constructor(
    public readonly suite: string,
    public readonly candidate: CandidateName
  ) {}

  async timed<T>(name: string, fn: () => Promise<T>): Promise<T> {
    const start = performance.now();
    const result = await fn();
    const elapsed = performance.now() - start;
    this.latencies.push(elapsed);
    return result;
  }

  pass(name: string, detail?: Record<string, unknown>, latencyMs?: number) {
    this.cases.push({ name, passed: true, detail, latencyMs });
    if (latencyMs !== undefined) this.latencies.push(latencyMs);
  }

  fail(name: string, err: unknown, detail?: Record<string, unknown>) {
    const code = (err as any)?.code;
    const message = err instanceof Error ? err.message : String(err);
    this.cases.push({ name, passed: false, errorCode: code, errorMessage: message, detail });
  }

  finish(): SuiteResult {
    const passed = this.cases.filter((c) => c.passed).length;
    return {
      suite: this.suite,
      candidate: this.candidate,
      passed,
      total: this.cases.length,
      cases: this.cases,
      latenciesMs: this.latencies,
      startedAt: this.startedAt,
      finishedAt: new Date().toISOString(),
    };
  }
}

export function percentile(values: number[], p: number): number {
  if (values.length === 0) return NaN;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length));
  return sorted[idx];
}

export function median(values: number[]): number {
  return percentile(values, 50);
}

/** Starts a kernel with a fresh profile, runs fn, always stops the kernel
 * afterwards (best-effort) even on throw. */
export async function withKernel<T>(candidate: CandidateName, fn: (kernel: BrowserKernel, opts: StartOptions) => Promise<T>): Promise<T> {
  const opts = freshDirs(candidate);
  const kernel = kernelFactory(candidate);
  await kernel.start(opts);
  try {
    return await fn(kernel, opts);
  } finally {
    await kernel.stop().catch(() => {});
  }
}

export function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {
  KernelError,
  type BrowserKernel,
  type StartOptions,
  type Observation,
  type ObservationElement,
  type Target,
  type PageInfo,
  type PageKind,
  type DialogInfo,
  type DownloadResult,
  type FrameInfo,
} from "../../contracts/kernel.js";
import { parseSnapshot, parseTabList, type TabRow } from "./snapshotParser.js";

const TOOL_TIMEOUT_MS = 10000;
const OWNERSHIP_ATTRIBUTION_WINDOW_MS = 1500;

interface TrackedPage {
  info: PageInfo;
  lastKnownIndex: number;
  currentObservationId: string | null;
}

interface ObsIndexEntry {
  mcpRef: string;
  framePath: string[];
}

function textOf(result: any): string {
  return (result.content ?? []).map((c: any) => c.text ?? "").join("\n");
}

export class McpKernel implements BrowserKernel {
  readonly name = "mcp" as const;

  private client: Client | null = null;
  private transport: StdioClientTransport | null = null;
  private pages = new Map<string, TrackedPage>();
  private creationSeq = 0;
  /** Highest creationSeq already "claimed" by an explicit newPage() caller
   * or a prior waitForNewPage() consumption. waitForNewPage() reports the
   * lowest-seq page above this cursor rather than diffing a before/after
   * page-id set — a before/after Set is unreliable here because click()
   * itself calls reconcileTabs() before returning, so the popup is already
   * registered by the time waitForNewPage() would compute its "before". */
  private lastConsumedPageSeq = -1;
  private observationIndex = new Map<string, Map<string, ObsIndexEntry>>();
  private lastAgentActionEndTs = -Infinity;
  private lastAgentActionPageId: string | null = null;
  private downloadsDir = "";
  private outputDir = "";
  /** Number of times duplicate (title,url) tabs forced a best-effort,
   * unverifiable reconciliation guess. Surfaced to tests/report as a direct
   * measure of MCP's lack of stable page identity. */
  ambiguousReconciliations = 0;
  private lastToolText = "";

  async start(options: StartOptions): Promise<void> {
    fs.mkdirSync(options.userDataDir, { recursive: true });
    fs.mkdirSync(options.downloadsDir, { recursive: true });
    this.downloadsDir = options.downloadsDir;
    this.outputDir = path.join(options.userDataDir, "..", "mcp-output");
    fs.mkdirSync(this.outputDir, { recursive: true });

    this.transport = new StdioClientTransport({
      command: "npx",
      args: [
        "@playwright/mcp@0.0.81",
        "--user-data-dir",
        options.userDataDir,
        "--output-dir",
        this.outputDir,
        ...(options.headless ? ["--headless"] : []),
      ],
    });
    this.client = new Client({ name: "browser-kernel-spike", version: "0.1.0" });
    await this.client.connect(this.transport);
    await this.reconcileTabs();
    // Pages discovered by this initial reconcile (e.g. the default blank
    // tab) are not "new" from any caller's perspective — seed the cursor so
    // waitForNewPage()'s first call doesn't treat them as fresh.
    this.lastConsumedPageSeq = this.creationSeq - 1;
  }

  async stop(): Promise<void> {
    // Relying on stdin-close to trigger the server's own cleanup does not
    // reliably flush persistent-profile state (empirically: cookies/
    // localStorage set moments earlier were lost across a restart even
    // though the SDK's close() waits up to ~2s for a graceful child exit).
    // Explicitly calling the server's own browser_close tool first — the
    // same graceful path MCP itself advertises — is the architecturally
    // correct shutdown sequence, not a timing workaround.
    if (this.client) {
      await this.callTool("browser_close", {}, 5000).catch(() => {});
    }
    await this.client?.close().catch(() => {});
    this.client = null;
    this.transport = null;
  }

  async crash(): Promise<void> {
    // See tests/suite_crash_reconnect.ts for the real process-level crash
    // test (forked worker + SIGKILL). This in-process variant just drops
    // the client connection without a clean MCP shutdown handshake.
    const pid = this.transport?.pid;
    if (pid) {
      try {
        process.kill(pid, "SIGKILL");
      } catch {
        // already gone
      }
    }
    this.client = null;
    this.transport = null;
  }

  async reconnect(options: StartOptions): Promise<void> {
    await this.start(options);
  }

  private async callTool(name: string, args: Record<string, unknown>, timeoutMs = TOOL_TIMEOUT_MS) {
    if (!this.client) throw new KernelError("RUNTIME_UNAVAILABLE", "MCP client not connected");
    let result: any;
    try {
      result = await this.client.callTool({ name, arguments: args }, undefined, { timeout: timeoutMs });
    } catch (err: any) {
      if (err?.code === -32001 || /timed out/i.test(String(err?.message))) {
        throw new KernelError("TIMEOUT", `MCP tool ${name} timed out after ${timeoutMs}ms`, { tool: name });
      }
      throw new KernelError("RUNTIME_DISCONNECTED", `MCP tool ${name} failed: ${err?.message}`, { tool: name });
    }
    const text = textOf(result);
    this.lastToolText = text;
    return { text, isError: !!result.isError };
  }

  // -------------------------------------------------------------------
  // Tab/page registry (positional, best-effort — see README limitations)
  // -------------------------------------------------------------------

  private async reconcileTabs(): Promise<void> {
    const { text } = await this.callTool("browser_tabs", { action: "list" });
    const rows = parseTabList(text);
    const prevTracked = [...this.pages.values()].filter((p) => !p.info.isClosed);
    const usedPrev = new Set<string>();
    const rowAssignment = new Map<number, string>();

    // Pass 1: same index as last known position. This is the common case —
    // MCP has no stable per-tab id, only position, and a plain navigation
    // legitimately changes a tracked page's title/url without it changing
    // identity, so title/url must NOT be required to match here (that was
    // the original bug: every navigate() call made a page look "closed" and
    // minted a phantom replacement, since title/url always differs post-nav).
    for (const row of rows) {
      const match = prevTracked.find((p) => !usedPrev.has(p.info.pageId) && p.lastKnownIndex === row.index);
      if (match) {
        rowAssignment.set(row.index, match.info.pageId);
        usedPrev.add(match.info.pageId);
      }
    }
    // Pass 2: index shifted (some OTHER tab closed/opened elsewhere) but
    // title/url still match — correlate by content instead.
    for (const row of rows) {
      if (rowAssignment.has(row.index)) continue;
      const candidates = prevTracked.filter((p) => !usedPrev.has(p.info.pageId) && p.info.title === row.title && p.info.url === row.url);
      if (candidates.length === 0) continue;
      if (candidates.length > 1) this.ambiguousReconciliations++;
      candidates.sort((a, b) => Math.abs(a.lastKnownIndex - row.index) - Math.abs(b.lastKnownIndex - row.index));
      rowAssignment.set(row.index, candidates[0].info.pageId);
      usedPrev.add(candidates[0].info.pageId);
    }
    for (const row of rows) {
      if (rowAssignment.has(row.index)) continue;
      const pageId = this.mintPageIdForRow(row);
      rowAssignment.set(row.index, pageId);
    }
    for (const p of prevTracked) {
      if (!usedPrev.has(p.info.pageId) && ![...rowAssignment.values()].includes(p.info.pageId)) {
        p.info = { ...p.info, isClosed: true };
      }
    }
    for (const row of rows) {
      const pageId = rowAssignment.get(row.index)!;
      const entry = this.pages.get(pageId)!;
      entry.lastKnownIndex = row.index;
      entry.info = { ...entry.info, url: row.url, title: row.title, isClosed: false };
    }
  }

  private mintPageIdForRow(row: TabRow): string {
    const seq = this.creationSeq++;
    const pageId = `page-${seq}-${crypto.randomBytes(3).toString("hex")}`;
    let owner: PageKind = "UNKNOWN";
    const now = Date.now();
    // MCP exposes no opener/parent relationship for new tabs, so ownership
    // attribution can only use the bounded post-action time window (weaker
    // than direct Playwright's page.opener()). Documented limitation.
    if (this.lastAgentActionPageId && now - this.lastAgentActionEndTs <= OWNERSHIP_ATTRIBUTION_WINDOW_MS) {
      const actingPage = this.pages.get(this.lastAgentActionPageId);
      if (actingPage?.info.owner === "AGENT") owner = "AGENT";
    }
    const info: PageInfo = {
      pageId,
      url: row.url,
      title: row.title,
      owner,
      openerPageId: null,
      creationSeq: seq,
      isClosed: false,
    };
    this.pages.set(pageId, { info, lastKnownIndex: row.index, currentObservationId: null });
    return pageId;
  }

  private getEntry(pageId: string): TrackedPage {
    const entry = this.pages.get(pageId);
    if (!entry) throw new KernelError("TARGET_NOT_FOUND", `Unknown pageId ${pageId}`);
    if (entry.info.isClosed) throw new KernelError("PAGE_CLOSED", `Page ${pageId} is closed`);
    return entry;
  }

  private async ensureActive(pageId: string): Promise<void> {
    const entry = this.getEntry(pageId);
    const { text } = await this.callTool("browser_tabs", { action: "list" });
    const rows = parseTabList(text);
    const currentRow = rows.find((r) => r.current);
    if (currentRow && currentRow.index === entry.lastKnownIndex) return;
    await this.callTool("browser_tabs", { action: "select", index: entry.lastKnownIndex });
  }

  private markAgentActionStart(pageId: string): void {
    this.lastAgentActionPageId = pageId;
  }
  private markAgentActionEnd(pageId: string): void {
    this.lastAgentActionPageId = pageId;
    this.lastAgentActionEndTs = Date.now();
  }

  // -------------------------------------------------------------------

  async navigate(pageId: string, url: string): Promise<void> {
    await this.ensureActive(pageId);
    this.markAgentActionStart(pageId);
    const { text, isError } = await this.callTool("browser_navigate", { url }, 15000);
    this.markAgentActionEnd(pageId);
    this.getEntry(pageId).currentObservationId = null;
    if (isError) {
      if (/timeout/i.test(text)) throw new KernelError("NAVIGATION_TIMEOUT", text, { url });
      throw new KernelError("NAVIGATION_FAILED", text, { url });
    }
    await this.reconcileTabs();
  }

  async observe(pageId: string): Promise<Observation> {
    await this.ensureActive(pageId);
    const { text, isError } = await this.callTool("browser_snapshot", {});
    if (isError) {
      if (/dialog|modal/i.test(text)) throw new KernelError("DIALOG_OPEN", text);
      throw new KernelError("TARGET_NOT_ACTIONABLE", text);
    }
    if (/### Modal state/.test(text)) {
      throw new KernelError("DIALOG_OPEN", "A dialog is open and blocking normal observation", { raw: text });
    }

    const parsed = parseSnapshot(text);
    const observationId = crypto.randomUUID();
    const index = new Map<string, ObsIndexEntry>();
    const elements: ObservationElement[] = [];
    const framesSeen = new Map<string, FrameInfo>();

    for (const p of parsed) {
      index.set(p.ref, { mcpRef: p.ref, framePath: p.framePath });
      const target: Target = {
        refToken: p.ref,
        observationId,
        pageId,
        framePath: p.framePath,
        debugLabel: `${p.role}:${p.name}`.slice(0, 60),
      };
      elements.push({ target, role: p.role, name: p.name, value: p.value });
      const key = p.framePath.join(">");
      if (!framesSeen.has(key)) framesSeen.set(key, { framePath: p.framePath, url: "", name: "" });
    }

    this.observationIndex.set(observationId, index);
    const entry = this.getEntry(pageId);
    entry.currentObservationId = observationId;

    const titleMatch = text.match(/Page Title:\s*(.*)/);
    const urlMatch = text.match(/Page URL:\s*(.*)/);
    const title = titleMatch?.[1]?.trim() ?? entry.info.title;
    const url = urlMatch?.[1]?.trim() ?? entry.info.url;
    entry.info = { ...entry.info, title, url };

    return {
      observationId,
      pageId,
      url,
      title,
      elements,
      frames: [...framesSeen.values()],
      takenAtMs: Date.now(),
    };
  }

  private resolveTarget(target: Target): string {
    const entry = this.getEntry(target.pageId);
    if (entry.currentObservationId !== target.observationId) {
      throw new KernelError("TARGET_STALE", "Target belongs to a superseded observation", {
        expected: entry.currentObservationId,
        got: target.observationId,
      });
    }
    const index = this.observationIndex.get(target.observationId);
    const idx = index?.get(target.refToken);
    if (!index || !idx) {
      throw new KernelError("TARGET_NOT_FOUND", "Target ref not found in observation index", { refToken: target.refToken });
    }
    return idx.mcpRef;
  }

  private interpretActionResult(text: string, isError: boolean): void {
    if (isError) {
      if (/not found in the current page snapshot/i.test(text)) {
        throw new KernelError("TARGET_STALE", text);
      }
      if (/timed out|timeout/i.test(text)) {
        throw new KernelError("TARGET_NOT_ACTIONABLE", text);
      }
      throw new KernelError("TARGET_NOT_ACTIONABLE", text);
    }
    if (/### Modal state/.test(text)) {
      throw new KernelError("DIALOG_OPEN", "Action opened a dialog", { raw: text });
    }
  }

  async click(target: Target): Promise<void> {
    const ref = this.resolveTarget(target);
    await this.ensureActive(target.pageId);
    this.markAgentActionStart(target.pageId);
    const { text, isError } = await this.callTool("browser_click", { target: ref, element: target.debugLabel });
    this.markAgentActionEnd(target.pageId);
    this.getEntry(target.pageId).currentObservationId = null;
    this.interpretActionResult(text, isError);
    await this.reconcileTabs();
  }

  async fill(target: Target, text: string): Promise<void> {
    const ref = this.resolveTarget(target);
    await this.ensureActive(target.pageId);
    const { text: resultText, isError } = await this.callTool("browser_type", {
      target: ref,
      element: target.debugLabel,
      text,
      slowly: false,
    });
    this.getEntry(target.pageId).currentObservationId = null;
    this.interpretActionResult(resultText, isError);
  }

  async typeSequential(target: Target, text: string): Promise<void> {
    const ref = this.resolveTarget(target);
    await this.ensureActive(target.pageId);
    const { text: resultText, isError } = await this.callTool("browser_type", {
      target: ref,
      element: target.debugLabel,
      text,
      slowly: true,
    });
    this.getEntry(target.pageId).currentObservationId = null;
    this.interpretActionResult(resultText, isError);
  }

  async press(target: Target, key: string): Promise<void> {
    this.resolveTarget(target); // validate freshness even though press_key is global-focus based
    await this.ensureActive(target.pageId);
    this.markAgentActionStart(target.pageId);
    const { text, isError } = await this.callTool("browser_press_key", { key });
    this.markAgentActionEnd(target.pageId);
    this.getEntry(target.pageId).currentObservationId = null;
    this.interpretActionResult(text, isError);
    await this.reconcileTabs();
  }

  async listPages(): Promise<PageInfo[]> {
    await this.reconcileTabs();
    return [...this.pages.values()].map((p) => p.info);
  }

  async newPage(url?: string): Promise<PageInfo> {
    const { text, isError } = await this.callTool("browser_tabs", { action: "new", url });
    if (isError) throw new KernelError("RUNTIME_UNAVAILABLE", text);
    const rows = parseTabList((await this.callTool("browser_tabs", { action: "list" })).text);
    const currentRow = rows.find((r) => r.current) ?? rows[rows.length - 1];
    await this.reconcileTabs();
    // Find the pageId matching currentRow's index, then force-mark AGENT
    // (explicit creation must never be left as a time-window guess).
    for (const [, p] of this.pages) {
      // Indices get reused after a close — must not match a stale CLOSED
      // entry whose lastKnownIndex happens to coincide with the new page's
      // current index (caught via a page_ownership suite run).
      if (!p.info.isClosed && p.lastKnownIndex === currentRow.index) {
        p.info = { ...p.info, owner: "AGENT" };
        // Explicitly created pages are returned directly to this caller —
        // a later, unrelated waitForNewPage() must not also report this one
        // as newly discovered (same class of bug as the direct-Playwright
        // adapter's queue-pollution fix).
        this.lastConsumedPageSeq = Math.max(this.lastConsumedPageSeq, p.info.creationSeq);
        return p.info;
      }
    }
    throw new KernelError("AMBIGUOUS_STATE", "Could not resolve newly created page after browser_tabs new");
  }

  async switchActivePage(pageId: string): Promise<void> {
    await this.ensureActive(pageId);
  }

  async closePage(pageId: string): Promise<void> {
    const entry = this.getEntry(pageId);
    if (entry.info.owner !== "AGENT") {
      throw new KernelError("OWNERSHIP_VIOLATION", `Refusing to close non-agent-owned page ${pageId} (owner=${entry.info.owner})`);
    }
    await this.callTool("browser_tabs", { action: "close", index: entry.lastKnownIndex });
    entry.info = { ...entry.info, isClosed: true };
    await this.reconcileTabs();
  }

  async waitForDialog(timeoutMs: number): Promise<DialogInfo | null> {
    // MCP has no push notification for dialogs and any unrelated tool call
    // blocks for the full request timeout while a dialog is open (empirically
    // confirmed: scripts/explore_mcp3.ts — a plain browser_snapshot call hung
    // for 60s against an open confirm() dialog). We poll with SHORT per-call
    // timeouts instead of one long one, which lets us detect it via the
    // resulting timeout error pattern without blocking the whole budget on a
    // single attempt, and without blind sleep-and-retry of a *mutating* action.
    const deadline = Date.now() + timeoutMs;
    const perAttemptMs = 1200;
    while (Date.now() < deadline) {
      try {
        const { text, isError } = await this.callTool("browser_snapshot", {}, perAttemptMs);
        if (/### Modal state/.test(text) || (isError && /dialog|modal/i.test(text))) {
          const kindMatch = text.match(/"(alert|confirm|prompt|beforeunload)" dialog/i);
          const msgMatch = text.match(/dialog with message "([^"]*)"/);
          return {
            kind: (kindMatch?.[1]?.toLowerCase() as DialogInfo["kind"]) ?? "alert",
            message: msgMatch?.[1] ?? "",
            pageId: [...this.pages.values()].find((p) => p.lastKnownIndex === 0)?.info.pageId ?? "",
          };
        }
      } catch (err) {
        if (err instanceof KernelError && err.code === "TIMEOUT") {
          // A hung snapshot call is itself strong evidence a dialog is open,
          // but we cannot get its message text this way. Try one direct
          // browser_handle_dialog probe is unsafe (would dismiss blindly),
          // so we report a dialog of unknown message rather than guess.
          return { kind: "alert", message: "(unknown — MCP blocked the probing call)", pageId: "" };
        }
        throw err;
      }
    }
    return null;
  }

  async handleDialog(accept: boolean, promptText?: string): Promise<void> {
    const { isError, text } = await this.callTool("browser_handle_dialog", { accept, promptText });
    if (isError) throw new KernelError("AMBIGUOUS_STATE", text);
  }

  async waitForNewPage(timeoutMs: number): Promise<PageInfo | null> {
    // No push notification for new tabs (empirically confirmed): a delayed
    // popup only appears once we actively re-list tabs. Bounded polling on a
    // fixed interval for an explicit condition (tab count increase), not a
    // blind action retry. See lastConsumedPageSeq's doc comment for why this
    // uses a cursor instead of a before/after page-id set.
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      await this.reconcileTabs();
      const candidates = [...this.pages.values()]
        .filter((p) => !p.info.isClosed && p.info.creationSeq > this.lastConsumedPageSeq)
        .sort((a, b) => a.info.creationSeq - b.info.creationSeq);
      if (candidates.length > 0) {
        this.lastConsumedPageSeq = candidates[0].info.creationSeq;
        return candidates[0].info;
      }
      await new Promise((r) => setTimeout(r, 150));
    }
    return null;
  }

  async clickAndWaitForDownload(target: Target, timeoutMs: number): Promise<DownloadResult> {
    const ref = this.resolveTarget(target);
    await this.ensureActive(target.pageId);
    const before = new Set(fs.existsSync(this.outputDir) ? fs.readdirSync(this.outputDir) : []);
    const { text, isError } = await this.callTool("browser_click", { target: ref, element: target.debugLabel }, timeoutMs);
    this.getEntry(target.pageId).currentObservationId = null;

    if (/Downloaded file .* to "(.*)"/.test(text)) {
      const m = text.match(/Downloaded file (.*) to "(.*)"/);
      const suggestedFilename = m?.[1] ?? "unknown";
      const relPath = m?.[2] ?? "";
      const absPath = path.resolve(this.outputDir, relPath.replace(/^(\.\.\/)+/, ""));
      const finalPath = fs.existsSync(absPath) ? absPath : path.join(this.outputDir, path.basename(relPath));
      if (!fs.existsSync(finalPath)) {
        throw new KernelError("DOWNLOAD_FAILED", `Reported download not found on disk: ${finalPath}`, { raw: text });
      }
      const dest = path.join(this.downloadsDir, `${crypto.randomBytes(4).toString("hex")}-${path.basename(finalPath)}`);
      fs.copyFileSync(finalPath, dest);
      const buf = fs.readFileSync(dest);
      return {
        suggestedFilename,
        savedPath: dest,
        byteSize: buf.length,
        sha256: crypto.createHash("sha256").update(buf).digest("hex"),
        sourceUrl: "",
      };
    }

    if (isError || /error|fail/i.test(text)) {
      throw new KernelError("DOWNLOAD_FAILED", text);
    }

    // Fall back to diffing the output dir in case the message format differs.
    await new Promise((r) => setTimeout(r, 300));
    const after = fs.existsSync(this.outputDir) ? fs.readdirSync(this.outputDir) : [];
    const newFile = after.find((f) => !before.has(f) && !f.startsWith("page-") && !f.startsWith("console-"));
    if (!newFile) throw new KernelError("DOWNLOAD_FAILED", "No new file appeared in MCP output dir", { raw: text });
    const finalPath = path.join(this.outputDir, newFile);
    const dest = path.join(this.downloadsDir, `${crypto.randomBytes(4).toString("hex")}-${newFile}`);
    fs.copyFileSync(finalPath, dest);
    const buf = fs.readFileSync(dest);
    return {
      suggestedFilename: newFile,
      savedPath: dest,
      byteSize: buf.length,
      sha256: crypto.createHash("sha256").update(buf).digest("hex"),
      sourceUrl: "",
    };
  }

  async readStorageProbe(pageId: string, key: string): Promise<string | null> {
    await this.ensureActive(pageId);
    if (key.startsWith("cookie:")) {
      const name = key.slice("cookie:".length);
      const { text } = await this.callTool("browser_evaluate", {
        function: `() => { const m = document.cookie.match(new RegExp('(?:^|; )${name}=([^;]*)')); return m ? decodeURIComponent(m[1]) : null; }`,
      });
      return parseEvaluateResult(text);
    }
    const name = key.startsWith("local:") ? key.slice("local:".length) : key;
    const { text } = await this.callTool("browser_evaluate", { function: `() => localStorage.getItem(${JSON.stringify(name)})` });
    return parseEvaluateResult(text);
  }

  async readText(pageId: string, testId: string): Promise<string | null> {
    await this.ensureActive(pageId);
    const { text } = await this.callTool("browser_evaluate", {
      function: `() => { const el = document.querySelector('[data-testid=${JSON.stringify(testId)}]'); return el ? el.textContent : null; }`,
    });
    return parseEvaluateResult(text);
  }

  async writeStorageProbe(pageId: string, key: string, value: string): Promise<void> {
    await this.ensureActive(pageId);
    if (key.startsWith("cookie:")) {
      const name = key.slice("cookie:".length);
      await this.callTool("browser_evaluate", {
        function: `() => { document.cookie = ${JSON.stringify(`${name}=${value}; path=/`)}; }`,
      });
      return;
    }
    const name = key.startsWith("local:") ? key.slice("local:".length) : key;
    await this.callTool("browser_evaluate", {
      function: `() => localStorage.setItem(${JSON.stringify(name)}, ${JSON.stringify(value)})`,
    });
  }
}

function parseEvaluateResult(text: string): string | null {
  // browser_evaluate's response is "### Result\n<value>\n### Ran Playwright code\n..."
  // where <value> is pretty-printed JSON (confirmed via scripts/explore_mcp4.ts).
  const m = text.match(/### Result\n([\s\S]*?)\n### /);
  const raw = (m?.[1] ?? text).trim();
  if (raw === "null" || raw === "" || raw === "undefined") return null;
  try {
    const parsed = JSON.parse(raw);
    return parsed === null ? null : String(parsed);
  } catch {
    return raw.replace(/^"|"$/g, "");
  }
}

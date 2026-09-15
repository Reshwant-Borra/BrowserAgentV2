import { chromium, type BrowserContext, type Page, type Frame, type Dialog, type Download } from "playwright";
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
import { snapshotInPage } from "./snapshotScript.js";

const ACTION_TIMEOUT_MS = 5000;
const NAV_TIMEOUT_MS = 15000;
/** Bounded window during which a newly-created page is attributed to the
 * kernel action that most recently ran on its opener page. Documented
 * limitation: a popup a page spawns more than this long after the
 * triggering click is indistinguishable, from kernel-observable events
 * alone, from a spontaneous/human-initiated popup. */
const OWNERSHIP_ATTRIBUTION_WINDOW_MS = 1500;

interface TargetIndexEntry {
  frame: Frame;
  selector: string;
}

interface PageEntry {
  page: Page;
  info: PageInfo;
  currentObservationId: string | null;
  activeDialog: { info: DialogInfo; dialog: Dialog } | null;
  dialogQueue: Array<{ info: DialogInfo; dialog: Dialog }>;
}

export class DirectPlaywrightKernel implements BrowserKernel {
  readonly name = "direct_playwright" as const;

  private context: BrowserContext | null = null;
  private pages = new Map<string, PageEntry>();
  private pageIdByPage = new WeakMap<Page, string>();
  private observationIndex = new Map<string, Map<string, TargetIndexEntry>>();
  private creationSeq = 0;
  private pendingExplicitOwner: PageKind | null = null;
  private explicitCreationInFlight = false;
  private lastAgentActionByPageId = new Map<string, number>(); // pageId -> endTs (Infinity while in-flight)
  private newPageWaiters: Array<(p: PageInfo | null) => void> = [];
  private newPageQueue: PageInfo[] = [];
  private downloadsDir = "";

  async start(options: StartOptions): Promise<void> {
    fs.mkdirSync(options.userDataDir, { recursive: true });
    fs.mkdirSync(options.downloadsDir, { recursive: true });
    this.downloadsDir = options.downloadsDir;
    this.context = await chromium.launchPersistentContext(options.userDataDir, {
      headless: options.headless,
      acceptDownloads: true,
      viewport: { width: 1280, height: 900 },
    });
    this.context.on("page", (page) => void this.onNewPageDiscovered(page));
    for (const page of this.context.pages()) {
      this.registerPage(page);
    }
  }

  async stop(): Promise<void> {
    await this.context?.close().catch(() => {});
    this.context = null;
  }

  async crash(): Promise<void> {
    // Simulated at the process level by the crash/reconnect test harness
    // (which forks a separate OS process per kernel instance and SIGKILLs
    // it). This method exists to satisfy the interface for in-process usage
    // but the meaningful crash test bypasses it — see tests/suite_crash_reconnect.ts.
    await this.context?.close().catch(() => {});
    this.context = null;
  }

  async reconnect(options: StartOptions): Promise<void> {
    await this.start(options);
  }

  private registerPage(page: Page): string {
    const existing = this.pageIdByPage.get(page);
    if (existing) return existing;

    const seq = this.creationSeq++;
    const pageId = `page-${seq}-${crypto.randomBytes(3).toString("hex")}`;
    let owner: PageKind = "UNKNOWN";
    let openerPageId: string | null = null;

    if (this.pendingExplicitOwner) {
      owner = this.pendingExplicitOwner;
      this.pendingExplicitOwner = null;
    }
    // owner may be refined UNKNOWN -> AGENT shortly after, by refineOwnership(),
    // based on opener + the bounded attribution window.

    const entry: PageEntry = {
      page,
      info: {
        pageId,
        url: page.url(),
        title: "",
        owner,
        openerPageId,
        creationSeq: seq,
        isClosed: false,
      },
      currentObservationId: null,
      activeDialog: null,
      dialogQueue: [],
    };
    this.pageIdByPage.set(page, pageId);
    this.pages.set(pageId, entry);

    page.on("dialog", (dialog) => {
      const info: DialogInfo = { kind: dialog.type() as DialogInfo["kind"], message: dialog.message(), pageId };
      entry.dialogQueue.push({ info, dialog });
    });
    page.on("close", () => {
      entry.info = { ...entry.info, isClosed: true };
    });
    page.on("framenavigated", (frame) => {
      if (frame === page.mainFrame()) {
        entry.info = { ...entry.info, url: page.url() };
      }
    });

    return pageId;
  }

  /** Called for pages discovered via the context-level 'page' event (popups,
   * window.open, externally-created tabs). Ownership refinement must
   * complete BEFORE waiters are notified — notifying with the placeholder
   * UNKNOWN owner first would race waitForNewPage() callers into observing
   * a pre-refinement snapshot. */
  private async onNewPageDiscovered(page: Page): Promise<void> {
    // context.newPage() (used by our own newPage()) ALSO fires this same
    // 'page' event, and the event can arrive either before or after
    // newPage()'s own registerPage() call resolves — so checking
    // pageIdByPage here is not reliably able to tell "this is an explicitly
    // created page" apart from "this is a genuine popup/external tab" (a
    // real race, caught via scripts/debug_ownership.ts). explicitCreationInFlight
    // is set for the whole duration of newPage(), independent of ordering,
    // and is the one signal that reliably distinguishes the two cases.
    if (this.explicitCreationInFlight) return;
    const pageId = this.registerPage(page);
    const entry = this.pages.get(pageId);
    if (entry && entry.info.owner !== "AGENT") {
      await this.refineOwnership(pageId, page);
    }
    const info = this.pages.get(pageId)?.info;
    if (!info) return;
    // A popup can be created (and this handler can finish) before any test
    // code calls waitForNewPage() — e.g. a synchronous window.open() inside
    // a click handler. If no waiter is currently registered, queue the
    // discovery so a later waitForNewPage() call still finds it instead of
    // the notification being silently lost.
    const waiter = this.newPageWaiters.shift();
    if (waiter) waiter(info);
    else this.newPageQueue.push(info);
  }

  private async refineOwnership(pageId: string, page: Page): Promise<void> {
    const entry = this.pages.get(pageId);
    if (!entry) return;
    if (entry.info.owner === "AGENT") return; // explicit creation already settled

    let openerPageId: string | null = null;
    try {
      const opener = await page.opener();
      if (opener) {
        const openerId = this.pageIdByPage.get(opener) ?? null;
        openerPageId = openerId;
        if (openerId) {
          const lastActionTs = this.lastAgentActionByPageId.get(openerId);
          const now = Date.now();
          if (lastActionTs !== undefined && now - lastActionTs <= OWNERSHIP_ATTRIBUTION_WINDOW_MS) {
            const openerEntry = this.pages.get(openerId);
            const inheritedOwner: PageKind = openerEntry?.info.owner === "AGENT" ? "AGENT" : "UNKNOWN";
            entry.info = { ...entry.info, owner: inheritedOwner, openerPageId };
            return;
          }
        }
      }
    } catch {
      // opener() can throw if the page/context already closed; leave UNKNOWN.
    }
    entry.info = { ...entry.info, openerPageId };
  }

  private markAgentActionStart(pageId: string): void {
    this.lastAgentActionByPageId.set(pageId, Infinity);
  }
  private markAgentActionEnd(pageId: string): void {
    this.lastAgentActionByPageId.set(pageId, Date.now());
  }

  private getPageEntry(pageId: string): PageEntry {
    const entry = this.pages.get(pageId);
    if (!entry) throw new KernelError("TARGET_NOT_FOUND", `Unknown pageId ${pageId}`);
    if (entry.info.isClosed) throw new KernelError("PAGE_CLOSED", `Page ${pageId} is closed`);
    return entry;
  }

  async navigate(pageId: string, url: string): Promise<void> {
    const entry = this.getPageEntry(pageId);
    this.markAgentActionStart(pageId);
    try {
      await entry.page.goto(url, { waitUntil: "load", timeout: NAV_TIMEOUT_MS });
    } catch (err: any) {
      if (String(err?.message ?? "").includes("Timeout")) {
        throw new KernelError("NAVIGATION_TIMEOUT", `Navigation to ${url} timed out`, { url });
      }
      throw new KernelError("NAVIGATION_FAILED", `Navigation to ${url} failed: ${err?.message}`, { url });
    } finally {
      this.markAgentActionEnd(pageId);
      entry.currentObservationId = null;
    }
  }

  private computeFramePath(frame: Frame): Promise<string[]> {
    return (async () => {
      const chain: string[] = [];
      let f: Frame | null = frame;
      while (f) {
        const parent: Frame | null = f.parentFrame();
        if (!parent) {
          chain.unshift("main");
          break;
        }
        // Prefer the iframe's own id/name attribute (stable, human-legible).
        // Two sibling iframes can both lack one, so the fallback must still
        // distinguish them — using their position among the parent's child
        // frames does that deterministically, unlike a shared "anon" label
        // which would silently collapse distinct frames onto the same path.
        let label: string;
        try {
          const owner = await f.frameElement();
          const id = await owner.getAttribute("id");
          const name = f.name();
          if (id) label = `iframe:${id}`;
          else if (name) label = `iframe:name:${name}`;
          else label = `iframe:idx${parent.childFrames().indexOf(f)}`;
        } catch {
          label = `iframe:idx${parent.childFrames().indexOf(f)}`;
        }
        chain.unshift(label);
        f = parent;
      }
      return chain;
    })();
  }

  async observe(pageId: string): Promise<Observation> {
    const entry = this.getPageEntry(pageId);
    const observationId = crypto.randomUUID();
    const index = new Map<string, TargetIndexEntry>();
    const elements: ObservationElement[] = [];
    const frameInfos: FrameInfo[] = [];

    for (const frame of entry.page.frames()) {
      if (frame.isDetached()) continue;
      let framePath: string[];
      try {
        framePath = await this.computeFramePath(frame);
      } catch {
        continue;
      }
      frameInfos.push({ framePath, url: frame.url(), name: frame.name() });

      let raw: Array<{ refToken: string; role: string; name: string; value: string | undefined; id: string | null }>;
      try {
        raw = await frame.evaluate(snapshotInPage, observationId);
      } catch {
        continue; // cross-origin or navigating frame; skip rather than fail whole observation
      }

      for (const r of raw) {
        // r.refToken (e.g. "r1") is minted independently per frame, starting
        // over at 0 each time — it collides across frames within the same
        // observation. Scope the index key (and the Target's own refToken)
        // by frame path so a later frame's "r1" can never shadow an earlier
        // frame's "r1".
        const scopedRef = `${framePath.join(">")}::${r.refToken}`;
        const selector = `[data-bk-obs="${observationId}"][data-bk-ref="${r.refToken}"]`;
        index.set(scopedRef, { frame, selector });
        const target: Target = {
          refToken: scopedRef,
          observationId,
          pageId,
          framePath,
          debugLabel: `${r.role}:${r.name}`.slice(0, 60),
        };
        elements.push({ target, role: r.role, name: r.name, value: r.value });
      }
    }

    this.observationIndex.set(observationId, index);
    entry.currentObservationId = observationId;
    entry.info = { ...entry.info, url: entry.page.url(), title: await entry.page.title().catch(() => "") };

    return {
      observationId,
      pageId,
      url: entry.page.url(),
      title: entry.info.title,
      elements,
      frames: frameInfos,
      takenAtMs: Date.now(),
    };
  }

  private async resolveTarget(target: Target) {
    const entry = this.getPageEntry(target.pageId);
    if (entry.currentObservationId !== target.observationId) {
      throw new KernelError("TARGET_STALE", "Target belongs to a superseded observation", {
        expected: entry.currentObservationId,
        got: target.observationId,
      });
    }
    const index = this.observationIndex.get(target.observationId);
    const entryIdx = index?.get(target.refToken);
    if (!index || !entryIdx) {
      throw new KernelError("TARGET_NOT_FOUND", "Target ref not found in observation index", {
        refToken: target.refToken,
      });
    }
    if (entryIdx.frame.isDetached()) {
      throw new KernelError("TARGET_STALE", "Target's frame has been detached", { framePath: target.framePath });
    }
    const locator = entryIdx.frame.locator(entryIdx.selector);
    const count = await locator.count();
    if (count !== 1) {
      throw new KernelError("TARGET_STALE", `Target element no longer uniquely resolves (count=${count})`, {
        selector: entryIdx.selector,
      });
    }
    return locator;
  }

  /** Bounded poll for a dialog having been queued on a page (see
   * registerPage's `page.on('dialog', ...)` listener). A native
   * alert/confirm/prompt freezes the page's JS thread synchronously, so a
   * click() whose handler opens one will not resolve on its own until the
   * dialog is dismissed — see click()'s race against this. */
  private async pollDialogQueued(pageId: string, timeoutMs: number): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const entry = this.pages.get(pageId);
      if (entry && (entry.dialogQueue.length > 0 || entry.activeDialog)) return true;
      await new Promise((r) => setTimeout(r, 30));
    }
    return false;
  }

  async click(target: Target): Promise<void> {
    const locator = await this.resolveTarget(target);
    const pageId = target.pageId;
    this.markAgentActionStart(pageId);
    try {
      const clickPromise = locator.click({ timeout: ACTION_TIMEOUT_MS });
      const raceResult: "click" | "dialog" | "dialog-timeout" = await Promise.race([
        clickPromise.then((): "click" => "click"),
        this.pollDialogQueued(pageId, ACTION_TIMEOUT_MS).then((found): "dialog" | "dialog-timeout" => (found ? "dialog" : "dialog-timeout")),
      ]);
      if (raceResult === "dialog") {
        // Chromium's JS thread is blocked until the dialog is resolved, so
        // Playwright's click() call will not settle until then either — the
        // caller must use waitForDialog()/handleDialog() next. Attach a
        // no-op catch so the eventually-settling click promise can't produce
        // an unhandled rejection later.
        clickPromise.catch(() => {});
        return;
      }
      if (raceResult === "dialog-timeout") {
        await clickPromise; // neither branch resolved in time; surface click's own outcome/error
      }
    } catch (err: any) {
      throw this.mapActionError(err);
    } finally {
      this.markAgentActionEnd(pageId);
      this.getPageEntry(pageId).currentObservationId = null;
    }
  }

  async fill(target: Target, text: string): Promise<void> {
    const locator = await this.resolveTarget(target);
    try {
      await locator.fill("", { timeout: ACTION_TIMEOUT_MS });
      await locator.fill(text, { timeout: ACTION_TIMEOUT_MS });
      // Best-effort immediate readback: gives a sharper INPUT_VALUE_MISMATCH
      // classification for the common case. Per contract, fill() must not
      // retry and final verification is the caller's job via a fresh
      // observe() — so if the node can no longer be located at all (e.g. a
      // controlled-input re-render replaced it without preserving the
      // stamped attributes), that is NOT this method's failure to report;
      // silently skip the check rather than throwing an unrelated error or
      // hanging on Playwright's default 30s timeout.
      let actual: string | null = null;
      try {
        actual = await locator.inputValue({ timeout: 800 });
      } catch {
        return;
      }
      if (actual !== text) {
        throw new KernelError("INPUT_VALUE_MISMATCH", `fill() value mismatch: expected ${JSON.stringify(text)}, got ${JSON.stringify(actual)}`, {
          expected: text,
          actual,
        });
      }
    } catch (err) {
      if (err instanceof KernelError) throw err;
      throw this.mapActionError(err);
    } finally {
      this.getPageEntry(target.pageId).currentObservationId = null;
    }
  }

  async typeSequential(target: Target, text: string): Promise<void> {
    const locator = await this.resolveTarget(target);
    try {
      await locator.click({ timeout: ACTION_TIMEOUT_MS });
      await locator.fill("", { timeout: ACTION_TIMEOUT_MS });
      await locator.pressSequentially(text, { delay: 15, timeout: ACTION_TIMEOUT_MS });
    } catch (err) {
      throw this.mapActionError(err);
    } finally {
      this.getPageEntry(target.pageId).currentObservationId = null;
    }
  }

  async press(target: Target, key: string): Promise<void> {
    const locator = await this.resolveTarget(target);
    this.markAgentActionStart(target.pageId);
    try {
      await locator.press(key, { timeout: ACTION_TIMEOUT_MS });
    } catch (err) {
      throw this.mapActionError(err);
    } finally {
      this.markAgentActionEnd(target.pageId);
      this.getPageEntry(target.pageId).currentObservationId = null;
    }
  }

  private mapActionError(err: any): KernelError {
    const msg = String(err?.message ?? err);
    if (msg.includes("Timeout")) return new KernelError("TARGET_NOT_ACTIONABLE", msg);
    return new KernelError("TARGET_NOT_ACTIONABLE", msg);
  }

  async listPages(): Promise<PageInfo[]> {
    return [...this.pages.values()].map((e) => e.info);
  }

  async newPage(url?: string): Promise<PageInfo> {
    if (!this.context) throw new KernelError("RUNTIME_UNAVAILABLE", "Context not started");
    this.pendingExplicitOwner = "AGENT";
    this.explicitCreationInFlight = true;
    let page: Page;
    try {
      page = await this.context.newPage();
    } finally {
      this.explicitCreationInFlight = false;
    }
    const pageId = this.registerPage(page);
    const entry = this.pages.get(pageId)!;
    entry.info = { ...entry.info, owner: "AGENT" };
    if (url) {
      await page.goto(url, { waitUntil: "load", timeout: NAV_TIMEOUT_MS }).catch((err) => {
        throw new KernelError("NAVIGATION_FAILED", `newPage navigate failed: ${err?.message}`, { url });
      });
      entry.info = { ...entry.info, url: page.url() };
    }
    return entry.info;
  }

  async switchActivePage(pageId: string): Promise<void> {
    const entry = this.getPageEntry(pageId);
    await entry.page.bringToFront();
  }

  async closePage(pageId: string): Promise<void> {
    const entry = this.getPageEntry(pageId);
    if (entry.info.owner !== "AGENT") {
      throw new KernelError("OWNERSHIP_VIOLATION", `Refusing to close non-agent-owned page ${pageId} (owner=${entry.info.owner})`);
    }
    await entry.page.close();
  }

  async waitForDialog(timeoutMs: number): Promise<DialogInfo | null> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      for (const entry of this.pages.values()) {
        if (entry.dialogQueue.length > 0 && !entry.activeDialog) {
          entry.activeDialog = entry.dialogQueue.shift()!;
          return entry.activeDialog.info;
        }
      }
      await new Promise((r) => setTimeout(r, 40));
    }
    return null;
  }

  async handleDialog(accept: boolean, promptText?: string): Promise<void> {
    for (const entry of this.pages.values()) {
      if (entry.activeDialog) {
        const { dialog } = entry.activeDialog;
        entry.activeDialog = null;
        if (accept) await dialog.accept(promptText);
        else await dialog.dismiss();
        return;
      }
    }
    throw new KernelError("AMBIGUOUS_STATE", "handleDialog called with no active dialog captured by waitForDialog");
  }

  async waitForNewPage(timeoutMs: number): Promise<PageInfo | null> {
    const queued = this.newPageQueue.shift();
    if (queued) return queued;
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        this.newPageWaiters = this.newPageWaiters.filter((w) => w !== onPage);
        resolve(null);
      }, timeoutMs);
      const onPage = (info: PageInfo | null) => {
        clearTimeout(timer);
        resolve(info);
      };
      this.newPageWaiters.push(onPage);
    });
  }

  async clickAndWaitForDownload(target: Target, timeoutMs: number): Promise<DownloadResult> {
    const locator = await this.resolveTarget(target);
    const entry = this.getPageEntry(target.pageId);
    let download: Download;
    try {
      const [d] = await Promise.all([
        entry.page.waitForEvent("download", { timeout: timeoutMs }),
        locator.click({ timeout: ACTION_TIMEOUT_MS }),
      ]);
      download = d;
    } catch (err: any) {
      throw new KernelError("DOWNLOAD_FAILED", `Download did not start: ${err?.message}`, {});
    } finally {
      entry.currentObservationId = null;
    }

    const failure = await download.failure();
    if (failure) {
      throw new KernelError("DOWNLOAD_FAILED", `Download failed: ${failure}`, { failure });
    }

    const safeName = download.suggestedFilename().replace(/[^a-zA-Z0-9._-]/g, "_");
    const savedPath = path.join(this.downloadsDir, `${crypto.randomBytes(4).toString("hex")}-${safeName}`);
    try {
      await download.saveAs(savedPath);
    } catch (err: any) {
      throw new KernelError("DOWNLOAD_FAILED", `Failed to save download: ${err?.message}`, {});
    }

    const buf = fs.readFileSync(savedPath);
    return {
      suggestedFilename: download.suggestedFilename(),
      savedPath,
      byteSize: buf.length,
      sha256: crypto.createHash("sha256").update(buf).digest("hex"),
      sourceUrl: download.url(),
    };
  }

  async readStorageProbe(pageId: string, key: string): Promise<string | null> {
    const entry = this.getPageEntry(pageId);
    if (key.startsWith("cookie:")) {
      const name = key.slice("cookie:".length);
      const cookies = await entry.page.context().cookies();
      const c = cookies.find((c) => c.name === name);
      return c ? c.value : null;
    }
    const name = key.startsWith("local:") ? key.slice("local:".length) : key;
    return entry.page.evaluate((n) => localStorage.getItem(n), name);
  }

  async readText(pageId: string, testId: string): Promise<string | null> {
    const entry = this.getPageEntry(pageId);
    const loc = entry.page.locator(`[data-testid="${testId}"]`).first();
    if ((await loc.count()) === 0) return null;
    return loc.textContent();
  }

  async writeStorageProbe(pageId: string, key: string, value: string): Promise<void> {
    const entry = this.getPageEntry(pageId);
    if (key.startsWith("cookie:")) {
      const name = key.slice("cookie:".length);
      await entry.page.context().addCookies([
        { name, value, url: entry.page.url() },
      ]);
      return;
    }
    const name = key.startsWith("local:") ? key.slice("local:".length) : key;
    await entry.page.evaluate(([n, v]) => localStorage.setItem(n, v), [name, value] as [string, string]);
  }
}

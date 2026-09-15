// Minimal shared BrowserKernel test contract for the MCP vs direct-Playwright spike.
//
// This is NOT the production BrowserAgentV2 API. It is the smallest surface needed
// to run identical behavioral tests against both candidate runtimes. Types here are
// intentionally adapter-agnostic: no MCP "ref" string leaks in as a type name, no
// Playwright ElementHandle/Locator leaks out.

/** Opaque, observation-scoped identity for one element. Only valid against the
 * ObservationId it was produced from. Adapters implement this however they need
 * to (MCP snapshot ref, or a synthesized locator descriptor for direct Playwright)
 * but upper-level test code must treat it as opaque. */
export interface Target {
  /** Adapter-opaque token identifying the element within its observation. */
  readonly refToken: string;
  /** Observation this target was minted from. A target used against any other
   * (or a later) observation must be rejected as stale. */
  readonly observationId: string;
  /** Page this target belongs to. */
  readonly pageId: string;
  /** Frame path from main frame to the target's frame, e.g. ["main"] or
   * ["main", "iframe#comments"]. Used to prove frame-correct targeting. */
  readonly framePath: string[];
  /** Human-readable description for logs/debugging only, never for re-resolution. */
  readonly debugLabel: string;
}

export type PageKind = "AGENT" | "USER" | "UNKNOWN";

export interface PageInfo {
  /** Stable internal page identity, NOT title/URL/index. */
  readonly pageId: string;
  readonly url: string;
  readonly title: string;
  /** Ownership assigned atomically at creation/discovery time. */
  readonly owner: PageKind;
  /** pageId of the opener, if known (popup / window.open / target=_blank). */
  readonly openerPageId: string | null;
  /** Monotonically increasing creation sequence number, for ordering proofs. */
  readonly creationSeq: number;
  readonly isClosed: boolean;
}

export interface FrameInfo {
  readonly framePath: string[];
  readonly url: string;
  readonly name: string;
}

export interface ObservationElement {
  readonly target: Target;
  readonly role: string;
  readonly name: string;
  readonly value?: string;
}

export interface Observation {
  readonly observationId: string;
  readonly pageId: string;
  readonly url: string;
  readonly title: string;
  readonly elements: ObservationElement[];
  readonly frames: FrameInfo[];
  readonly takenAtMs: number;
}

export interface DialogInfo {
  readonly kind: "alert" | "confirm" | "prompt" | "beforeunload";
  readonly message: string;
  readonly pageId: string;
}

export interface DownloadResult {
  readonly suggestedFilename: string;
  readonly savedPath: string;
  readonly byteSize: number;
  readonly sha256: string;
  readonly sourceUrl: string;
}

// ---------------------------------------------------------------------------
// Typed errors
// ---------------------------------------------------------------------------

export type KernelErrorCode =
  | "RUNTIME_UNAVAILABLE"
  | "RUNTIME_DISCONNECTED"
  | "PAGE_CLOSED"
  | "TARGET_STALE"
  | "TARGET_NOT_FOUND"
  | "TARGET_NOT_ACTIONABLE"
  | "INPUT_VALUE_MISMATCH"
  | "NAVIGATION_TIMEOUT"
  | "NAVIGATION_FAILED"
  | "DIALOG_OPEN"
  | "DOWNLOAD_FAILED"
  | "WRONG_FRAME"
  | "TIMEOUT"
  | "AMBIGUOUS_STATE"
  | "OWNERSHIP_VIOLATION";

export class KernelError extends Error {
  readonly code: KernelErrorCode;
  readonly details: Record<string, unknown>;

  constructor(code: KernelErrorCode, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "KernelError";
    this.code = code;
    this.details = details;
  }
}

// ---------------------------------------------------------------------------
// BrowserKernel contract
// ---------------------------------------------------------------------------

export interface StartOptions {
  /** Directory for the persistent browser profile. */
  readonly userDataDir: string;
  readonly headless: boolean;
  /** Directory downloads are saved into. */
  readonly downloadsDir: string;
}

export interface BrowserKernel {
  readonly name: "mcp" | "direct_playwright";

  /** Launch (or attach to) the browser with a persistent profile. */
  start(options: StartOptions): Promise<void>;

  /** Cleanly stop the runtime. Does not delete the profile. */
  stop(): Promise<void>;

  /** Simulate an abrupt controller crash: kill the underlying process(es)
   * without a clean shutdown sequence, but leave the profile/browser process
   * state as realistic as possible for reconnect testing. */
  crash(): Promise<void>;

  /** Reconnect after crash() or an external process kill, reusing the same
   * userDataDir. Must rediscover pages rather than trusting old state. */
  reconnect(options: StartOptions): Promise<void>;

  navigate(pageId: string, url: string): Promise<void>;

  /** Take a fresh observation of a page. Invalidates all prior targets for
   * that observationId lineage (a new observationId is always minted). */
  observe(pageId: string): Promise<Observation>;

  click(target: Target): Promise<void>;

  /** Deterministic exact-value fill (clear + set), verified by the caller via
   * a fresh observe() — this method itself must not silently retry. */
  fill(target: Target, text: string): Promise<void>;

  /** Bounded sequential key-press typing fallback, for controlled/rerendering
   * inputs. Still requires caller verification via observe(). */
  typeSequential(target: Target, text: string): Promise<void>;

  press(target: Target, key: string): Promise<void>;

  listPages(): Promise<PageInfo[]>;

  /** Open a brand-new agent-owned page/tab. */
  newPage(url?: string): Promise<PageInfo>;

  switchActivePage(pageId: string): Promise<void>;

  closePage(pageId: string): Promise<void>;

  /** Wait for and return the next dialog event on any page, or null on timeout. */
  waitForDialog(timeoutMs: number): Promise<DialogInfo | null>;

  handleDialog(accept: boolean, promptText?: string): Promise<void>;

  /** Wait for and return the next new-page (popup/window.open) event, or null
   * on timeout. Does not switch active page. */
  waitForNewPage(timeoutMs: number): Promise<PageInfo | null>;

  /** Click a target expected to trigger a download, and wait for completion. */
  clickAndWaitForDownload(target: Target, timeoutMs: number): Promise<DownloadResult>;

  /** Read a cookie/localStorage value directly (for persistence fixtures),
   * bypassing the observation/target system. */
  readStorageProbe(pageId: string, key: string): Promise<string | null>;

  writeStorageProbe(pageId: string, key: string, value: string): Promise<void>;

  /** Reads textContent of the first element matching [data-testid=testId],
   * bypassing the observation/target system. Used only by test suites to
   * verify postconditions on non-interactive elements (result banners,
   * status text) that observe() does not surface as targets. */
  readText(pageId: string, testId: string): Promise<string | null>;
}

export type KernelFactory = () => BrowserKernel;

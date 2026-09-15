// Out-of-band control channel used to simulate events that, in production,
// would come from a human acting on the browser directly (typing into a
// login form, clicking "approve", opening a tab) — WITHOUT going through the
// BrowserKernel under test. Fixture pages long-poll for commands addressed to
// their session id and act on themselves (navigate, replace DOM, open a
// popup, mutate storage). This lets handoff/resume and out-of-band-tab
// ownership fixtures run unattended and repeatably, while still producing
// real browser-level events (real navigation, real window.open, real DOM
// mutation) that the kernel must react to like it would to a human.
//
// A genuinely-manual, human-in-the-loop run of the handoff fixture is done
// separately (see tests/suite_handoff.ts --manual) to validate the simulation
// is faithful.

import type { Request, Response, Router } from "express";
import { Router as makeRouter } from "express";

export interface ControlCommand {
  readonly seq: number;
  readonly event: string;
  readonly payload: Record<string, unknown>;
}

const queues = new Map<string, ControlCommand[]>();
const seqCounters = new Map<string, number>();

export function fireControlCommand(session: string, event: string, payload: Record<string, unknown> = {}): number {
  const seq = (seqCounters.get(session) ?? 0) + 1;
  seqCounters.set(session, seq);
  const q = queues.get(session) ?? [];
  q.push({ seq, event, payload });
  queues.set(session, q);
  return seq;
}

export function resetSession(session: string): void {
  queues.delete(session);
  seqCounters.delete(session);
}

export function controlChannelRouter(): Router {
  const router = makeRouter();

  router.get("/control/poll", (req: Request, res: Response) => {
    const session = String(req.query.sid ?? "");
    const since = Number(req.query.since ?? 0);
    const q = queues.get(session) ?? [];
    const pending = q.filter((c) => c.seq > since);
    res.json({ commands: pending });
  });

  router.post("/control/fire", (req: Request, res: Response) => {
    const { session, event, payload } = req.body as {
      session: string;
      event: string;
      payload?: Record<string, unknown>;
    };
    const seq = fireControlCommand(session, event, payload ?? {});
    res.json({ ok: true, seq });
  });

  router.post("/control/reset", (req: Request, res: Response) => {
    const { session } = req.body as { session: string };
    resetSession(session);
    res.json({ ok: true });
  });

  return router;
}

/** Client-side snippet every fixture page that supports simulated external
 * events should inline. Polls every 75ms and dispatches a CustomEvent named
 * `bk:<event>` on `window` with `.detail = payload`. */
export const CONTROL_CLIENT_SCRIPT = `
(function () {
  const params = new URLSearchParams(location.search);
  const sid = params.get('sid');
  if (!sid) return;
  let since = 0;
  async function poll() {
    try {
      const res = await fetch('/control/poll?sid=' + encodeURIComponent(sid) + '&since=' + since);
      const data = await res.json();
      for (const cmd of data.commands) {
        since = Math.max(since, cmd.seq);
        window.dispatchEvent(new CustomEvent('bk:' + cmd.event, { detail: cmd.payload }));
      }
    } catch (e) { /* fixture harness not reachable yet; keep polling */ }
    setTimeout(poll, 75);
  }
  poll();
})();
`;

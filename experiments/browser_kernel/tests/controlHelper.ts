import crypto from "node:crypto";
import { FIXTURE_BASE } from "./harness.js";

export function newSession(): string {
  return crypto.randomBytes(6).toString("hex");
}

export async function fireControl(session: string, event: string, payload: Record<string, unknown> = {}): Promise<void> {
  const res = await fetch(`${FIXTURE_BASE}/control/fire`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ session, event, payload }),
  });
  if (!res.ok) throw new Error(`control/fire failed: ${res.status}`);
}

export async function resetSession(session: string): Promise<void> {
  await fetch(`${FIXTURE_BASE}/control/reset`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ session }),
  });
}

export function withSid(url: string, sid: string): string {
  const u = new URL(url);
  u.searchParams.set("sid", sid);
  return u.toString();
}

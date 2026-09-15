// Standalone worker process used by suite_crash_reconnect.ts. Runs as a real
// child OS process so the parent can SIGKILL it abruptly (simulating a
// controller crash) without any clean-shutdown code in this file running.
import { DirectPlaywrightKernel } from "../adapters/direct_playwright/directKernel.js";
import { McpKernel } from "../adapters/mcp/mcpKernel.js";

const [, , candidate, userDataDir, downloadsDir, mode] = process.argv;
const FIXTURE_BASE = process.env.FIXTURE_BASE ?? "http://localhost:4173";

async function main() {
  const kernel = candidate === "direct_playwright" ? new DirectPlaywrightKernel() : new McpKernel();
  await kernel.start({ userDataDir, downloadsDir, headless: true });

  if (mode === "seed") {
    const page = await kernel.newPage(`${FIXTURE_BASE}/fixtures/h?seed=1`);
    const cookie = await kernel.readStorageProbe(page.pageId, "cookie:bk_session");
    const local = await kernel.readStorageProbe(page.pageId, "local:bk_local");
    process.stdout.write(`READY:${JSON.stringify({ cookie, local })}\n`);
    // Idle forever awaiting SIGKILL from the parent — no cleanup on purpose.
    await new Promise(() => {});
    return;
  }

  // mode === "check": fresh worker process reconnecting/relaunching against
  // the SAME userDataDir after the seed worker was killed without cleanup.
  const page = await kernel.newPage(`${FIXTURE_BASE}/fixtures/h`); // no seed this time
  const cookie = await kernel.readStorageProbe(page.pageId, "cookie:bk_session");
  const local = await kernel.readStorageProbe(page.pageId, "local:bk_local");
  process.stdout.write(`RESULT:${JSON.stringify({ cookie, local })}\n`);
  await kernel.stop();
  process.exit(0);
}

main().catch((err) => {
  process.stdout.write(`ERROR:${JSON.stringify({ message: String(err?.message ?? err) })}\n`);
  process.exit(1);
});

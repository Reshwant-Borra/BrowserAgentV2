import { FIXTURE_BASE, SuiteRecorder, freshDirs, kernelFactory, type CandidateName, type SuiteResult } from "./harness.js";

const REPS = 10;

export async function run(candidate: CandidateName): Promise<SuiteResult> {
  const rec = new SuiteRecorder("persistent_profile_restart", candidate);

  for (let i = 0; i < REPS; i++) {
    const name = `persistence-${i}`;
    const opts = freshDirs(`persist-${candidate}-${i}`);
    try {
      const kernel1 = kernelFactory(candidate);
      await kernel1.start(opts);
      const page1 = await kernel1.newPage(`${FIXTURE_BASE}/fixtures/h?seed=1`);
      const cookieBefore = await kernel1.readStorageProbe(page1.pageId, "cookie:bk_session");
      const localBefore = await kernel1.readStorageProbe(page1.pageId, "local:bk_local");
      if (cookieBefore !== "abc123" || localBefore !== "xyz789") {
        throw new Error(`seed did not take effect: cookie=${cookieBefore} local=${localBefore}`);
      }
      await kernel1.stop();

      const kernel2 = kernelFactory(candidate);
      await kernel2.start(opts); // same userDataDir — must restore prior profile state
      const page2 = await kernel2.newPage(`${FIXTURE_BASE}/fixtures/h`); // no seed this time
      const cookieAfter = await kernel2.readStorageProbe(page2.pageId, "cookie:bk_session");
      const localAfter = await kernel2.readStorageProbe(page2.pageId, "local:bk_local");
      await kernel2.stop();

      if (cookieAfter !== "abc123") throw new Error(`cookie did not survive restart: ${cookieAfter}`);
      if (localAfter !== "xyz789") throw new Error(`localStorage did not survive restart: ${localAfter}`);

      rec.pass(name, { cookieAfter, localAfter });
    } catch (err) {
      rec.fail(name, err);
    }
  }

  return rec.finish();
}

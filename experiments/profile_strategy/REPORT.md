# Profile strategy confirmation

**Gate:** `Browser profile strategy` (P0, was `PROVISIONAL`)
**Verdict:** `DEDICATED_PROFILE_RESOLVED`
**Evidence:** [`results/profile_strategy_raw.json`](results/profile_strategy_raw.json)
**Reproduce:** `BAV2_PORT_BASE=8850 python -m experiments.profile_strategy.run_profile --reps 6`

## Question

Does a dedicated Playwright-managed persistent profile actually deliver the
properties [ADR-003](../../03_DECISIONS/ARCHITECTURE_DECISIONS.md) assumes, and
does it stay isolated from the user's daily-driver browser?

## Results

6 cases × 6 repetitions = **36 runs, 36 PASS**.

| # | case | what it checks | result |
|---|---|---|---|
| PF-01 | cookie + localStorage survive a controller restart | both storage mechanisms, independently | 6/6 |
| PF-02 | authenticated page usable after restart | the dashboard view is restored, not the login form | 6/6 |
| PF-03 | two consecutive restarts, no drift | session stage is `app` both times | 6/6 |
| PF-04 | two agent profiles are isolated | profile B sees none of profile A's session | 6/6 |
| PF-05 | the user's real Chrome profile is untouched | no writes to the real Chrome user-data directory | 6/6 |
| PF-06 | the profile lock is exclusive | a second controller cannot silently share one profile | 6/6 |

## What each result means

**Persistence is real, on both mechanisms.** The login fixture writes its stage
to a cookie *and* to `localStorage`, deliberately, so a pass cannot come from
one of them working. After a full controller shutdown and restart against the
same `user_data_dir`, `bav2_stage=app` is present in the cookie and
`bav2_account=school` in `localStorage`, and the page renders the authenticated
dashboard rather than the sign-in form. This is the property the whole handoff
design depends on: a human logs in once and the agent can be restarted freely.

**Isolation runs in both directions.** PF-04 shows a second agent profile
inherits nothing, so concurrent tasks cannot leak sessions into each other.
PF-05 snapshots the real Chrome user-data directory before and after a full
login run and confirms nothing in it changed, while the dedicated profile
directory is populated. The agent is not reading, writing, or borrowing the
human's browser identity.

**The profile lock is enforced by Chromium, not by us.** PF-06 starts a second
controller against a profile that is already open; it fails rather than
silently attaching. That is the outcome we want — silent sharing would corrupt
both sessions — but the enforcement comes from the browser's own profile lock.
Since the failure surfaces as a launch exception rather than a typed kernel
error, the controller should still own single-instance-per-profile explicitly
rather than relying on this.

## Relationship to the other gates

This gate is what makes [Experiment 7](../human_handoff/REPORT.md) HH-09 work:
the controller can die during handoff and the human's authenticated session
survives because it lives in the profile, not in the controller's memory.

It also reinforces [Experiment 5](../page_registry/REPORT.md): because we launch
the browser ourselves, the initial page is unambiguously ours, and there are no
pre-existing human tabs to misclassify. That property disappears in the deferred
attach-to-existing-Chrome mode, which is one more reason it stays deferred.

## Verdict

```text
DEDICATED_PROFILE_RESOLVED
```

The gate moves from `PROVISIONAL` to `RESOLVED`.
[ADR-003](../../03_DECISIONS/ARCHITECTURE_DECISIONS.md) stands as written, and
the rejection of daily-driver-Chrome-via-CDP as the default stands with it.

## What this does not establish

- Real-world session expiry, token refresh and server-side session
  invalidation were not tested; the fixture's session never expires.
- No real site's authentication was exercised.
- Chromium only. Firefox and WebKit persistent contexts were not tested.
- Profile corruption and disk-full behaviour were not tested.

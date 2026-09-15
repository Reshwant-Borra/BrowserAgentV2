# Memory, Recovery, Human Handoff, and Security Research

**Status:** active research

## Separate four kinds of memory

BrowserAgentV2 should not have one giant “memory” object. Use distinct stores with distinct purposes.

### 1. Working task state

Small, mutable state required to continue the current run:

- goal;
- current subgoal;
- short plan;
- completed/failed subgoals;
- relevant facts;
- active page/tab ids;
- policy/confirmation state;
- current run status.

### 2. Append-only execution trace

Every significant step should record:

- observation id;
- chosen decision;
- browser result;
- verification result;
- timestamps;
- failure classification;
- page URL/title;
- relevant artifacts.

This is for debugging and reproducibility, not model context.

### 3. Research/fact store

Long research tasks need provenance-bearing facts, citations/URLs, contradiction tracking, and deduplication.

### 4. Long-term user/project memory

Defer broad long-term semantic memory until the browser kernel is stable. For the MVP, SQLite is enough for explicit reusable preferences/state. Do not add a vector database just because the word “memory” appears in the product vision.

## Checkpointing

Checkpoint at least:

- before a human handoff;
- before an irreversible/high-impact action;
- after a verified subgoal completion;
- after a meaningful gathered-fact batch;
- before/after runtime restart recovery.

A restarted process must be able to reconstruct “what remains to do” without replaying the entire conversation.

## Recovery policy

The old system accumulated recovery logic that could hide root causes. V2 should classify failures and use bounded recovery.

Example classes:

- `TARGET_STALE`
- `TARGET_NOT_ACTIONABLE`
- `AMBIGUOUS_TARGET`
- `NAVIGATION_TIMEOUT`
- `HYDRATION_RESET`
- `NEW_TAB_UNEXPECTED`
- `DIALOG_BLOCKED`
- `AUTH_REQUIRED`
- `CAPTCHA_REQUIRED`
- `MODEL_INVALID_DECISION`
- `POSTCONDITION_FAILED`
- `RUNTIME_DISCONNECTED`

Every class has a small explicit policy. There is no catch-all “refresh and try again.”

## Retry rule

Read-only operations may be safely retried when clearly idempotent. State-changing actions must not be blindly replayed because the first action may have succeeded even if the client did not observe the result.

For ambiguous side effects:

1. fresh observation;
2. inspect for evidence that the action occurred;
3. only retry if absence is established;
4. otherwise pause/replan.

This is one of the remaining areas that needs more research and fixture tests.

## Human intervention

`WAITING_FOR_USER` is a first-class run state, not an exception.

Use it for:

- passwords;
- MFA/2FA;
- CAPTCHA;
- ambiguous account choice;
- consent/permissions;
- high-impact final submission.

Flow:

1. save checkpoint;
2. explain the exact manual step needed;
3. stop automation while keeping browser/session available;
4. user acts manually;
5. user signals completion;
6. discard all pre-handoff refs;
7. rediscover tabs and take a fresh observation;
8. resume current subgoal.

## Prompt-injection threat model

Webpage content is **untrusted data**. Text on a page cannot grant itself authority over system/user instructions or tool permissions.

Security rules:

- do not expose arbitrary shell execution to page-derived instructions;
- do not expose arbitrary JavaScript execution to the model in the MVP;
- do not reveal secrets/cookies/tokens to page content;
- minimize cross-domain actions;
- require confirmation for high-impact external actions;
- log why a confirmation was requested;
- keep page instructions separate from trusted task instructions in the context packet.

## Secrets and profiles

Persistent browser profiles may contain sensitive authentication material. Profile directories and exported auth state must never be committed to Git. The model should not receive raw cookies or stored credentials.

## Security evaluation

Add fixtures where page text says things like “ignore previous instructions,” asks to upload local secrets, or requests unrelated cross-domain actions. The correct behavior should be to treat those strings as page content, not trusted authority.

## Principle

Reliability, security, and recoverability are coupled. A system that cannot tell whether an action happened cannot safely retry it; a system that sends the model every secret/browser artifact cannot safely browse adversarial pages.

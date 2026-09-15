# Research Status

**Snapshot date:** 2026-09-15

## Current state

The research phase is **active**. We have a coherent provisional architecture, but implementation should not be treated as fully specified until the P0 decision gates in `06_OPEN_QUESTIONS/RESEARCH_GAPS.md` are resolved.

## Strong conclusions so far

- The LLM should choose intent/actions; browser mechanics must remain deterministic.
- Use a replaceable `BrowserKernel` abstraction.
- Playwright MCP is the first browser-kernel candidate, subject to a deterministic adoption spike.
- Direct Playwright is the fallback candidate without changing upper architecture.
- Accessibility/semantic observations should be primary; DOM/CDP enrichment and vision are fallbacks.
- Targets are observation-scoped and stale targets are rejected.
- One state-changing browser action per controller step for the MVP.
- No model-callable refresh/reload in normal operation.
- Every state-changing action requires postcondition verification.
- Qwen model output must be schema-validated; free-form ReAct parsing is rejected.
- The model receives bounded current context, not full browsing history.
- SQLite is sufficient for initial task state, facts, checkpoints, and traces.
- Login/MFA/CAPTCHA/consent/high-impact actions use explicit human handoff states.
- Webpage content is untrusted data and cannot grant itself new authority.
- Site-specific architectures are rejected; generality comes from composable primitives.

## Files currently in the research knowledge base

- `README.md`
- `00_PROJECT/VISION_AND_SCOPE.md`
- `01_RESEARCH/BROWSER_RUNTIME_RESEARCH.md`
- `01_RESEARCH/ECOSYSTEM_AND_BENCHMARKS.md`
- `01_RESEARCH/GROUNDING_AND_CONTEXT.md`
- `01_RESEARCH/QWEN_MODEL_INTERFACE.md`
- `01_RESEARCH/MEMORY_RECOVERY_AND_SECURITY.md`
- `02_ARCHITECTURE/PROPOSED_ARCHITECTURE.md`
- `03_DECISIONS/ARCHITECTURE_DECISIONS.md`
- `04_TESTING/TEST_STRATEGY_AND_EXIT_GATES.md`
- `05_IMPLEMENTATION/TWO_DAY_BUILD_PLAN.md`
- `06_OPEN_QUESTIONS/RESEARCH_GAPS.md`
- `SOURCES.md`

## Next research actions

1. Audit the old BrowserAgent repository from actual code.
2. Design/run the Playwright MCP adoption spike.
3. Build frozen Qwen decision-interface evaluation cases.
4. Specify ambiguous-side-effect reconciliation.
5. Pin exact runtime/tool versions after the spike.
6. Define download/upload safety and persistence semantics.
7. Define exact observation invalidation and loop-detection rules.
8. Reconcile all findings into a final architecture spec before Codex implementation begins.

## Rule for future work

When evidence changes an assumption, update the research/ADR documents first. Do not silently mutate the architecture through implementation prompts.

# Grounding, Observation, and Context Research

**Status:** active research

## The grounding problem

Most browser-agent failures that look like “the model is dumb” can actually be failures to map a correct intention onto the correct browser target. BrowserAgentV2 must separate planning quality from grounding quality.

## Primary observation: semantic accessibility snapshot

The default model-facing representation should be compact semantic text derived from the current page's accessibility structure. Each actionable element must have an observation-scoped target identifier.

Recommended target identity concept:

```text
page_id + observation_version + element_ref
```

Example:

```text
p3:s42:e17
```

If the page has advanced to a new meaningful observation version, the executor should reject the old target rather than guessing that it still points to the same thing.

## Why not raw DOM by default

Full DOM dumps are large, noisy, and include styling/framework details that usually do not help the planner. The model should receive accessible role/name/state plus selected metadata, not arbitrary HTML.

Useful fields include:

- target/ref;
- role/tag;
- accessible/visible name;
- input type;
- current value with sensitive values redacted;
- checked/selected/disabled/expanded state;
- link domain/path when useful;
- frame/page id;
- interactability/visibility.

DOM/CDP enrichment can be requested by the runtime when accessibility alone is insufficient.

## Vision is a fallback

Screenshots matter for maps, canvases, charts, visual ordering, and custom controls that are poorly exposed semantically. Vision should be a fallback capability, not the required representation for every action.

For the two-day Qwen3 8B text-first MVP, structured observation should carry almost all normal interaction.

## Change observation

After each state-changing action, compute a compact change summary such as:

- URL/title changed;
- new tab opened;
- dialog appeared;
- target value changed;
- new controls/text appeared;
- significant subtree changed;
- no meaningful change.

This should accompany the fresh current observation. Do not make Qwen infer change by rereading the full historical transcript.

## Context packet design

Every model call should receive a bounded packet:

1. user goal;
2. current subgoal;
3. short plan;
4. compact relevant facts gathered so far;
5. previous action + verified outcome;
6. current page/tabs;
7. current structured observation;
8. allowed actions and schema;
9. policy/confirmation state.

Do **not** include the full event log or every previous page snapshot.

## Long research tasks

Research tasks need a separate fact store. Each extracted fact should carry provenance:

```text
fact_id
claim/value
source_url
page_title
retrieved_at
supporting_excerpt_or_locator
confidence/status
```

The model should receive only facts relevant to the current subgoal plus a compact task summary. Raw pages remain in traces/artifacts for audit, not prompt context.

## Deduplication and compression

Long-horizon runs should periodically:

- merge duplicate facts;
- mark contradictions rather than silently overwrite;
- summarize completed subgoals;
- discard stale observation text from model context while retaining it in the trace database.

## Context overflow is a system failure

The controller should have explicit token/character budgets for each context section. If the observation is too large, the runtime should filter, search, or request a narrower subtree. Never send an enormous DOM and hope Qwen handles it.

## Resulting rule

The model receives **current truth + relevant task memory**, not browsing history. The trace database can be exhaustive; the prompt cannot.

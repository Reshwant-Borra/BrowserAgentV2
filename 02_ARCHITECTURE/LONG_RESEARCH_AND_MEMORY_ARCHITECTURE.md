# Long Research and Memory Architecture

**Goal:** support tasks such as “research 100+ websites and synthesize a sourced answer” without expanding Qwen’s prompt until it collapses, revisiting the same pages forever, or losing evidence across restarts.

**Status:** later-phase architecture. It depends on the ordinary BrowserAgent loop being reliable first.

## Why long research is a different mode

Normal browser automation asks:

```text
What is the next action needed to complete this workflow?
```

Long research asks:

```text
What evidence is still missing?
Which source should be inspected next?
What new facts did it add?
Does it contradict existing evidence?
When is coverage sufficient to stop?
```

AssistantBench, WorkArena++, WebLINX, and WebChoreArena all support the conclusion that planning, memory, information transfer, retrieval, and completeness are major bottlenecks in long web tasks.

Therefore long research is a separate controller mode over the same BrowserKernel, not just a bigger prompt.

---

# 1. ResearchTask state

```json
{
  "research_id":"...",
  "goal":"Find and compare the 10 best ...",
  "questions":[
    {
      "id":"q1",
      "question":"What candidates meet the user's constraints?",
      "status":"OPEN",
      "minimum_evidence":3
    }
  ],
  "candidate_entities":[],
  "coverage_requirements":[],
  "visited_sources":{},
  "remaining_gaps":[],
  "stop_reason":null
}
```

The model never receives this entire database. The ContextBuilder selects the active question/gap and relevant evidence.

---

# 2. Research loop

```text
Initialize research questions/criteria
          |
          v
Choose highest-value evidence gap
          |
          v
Generate/search/select source candidate
          |
          v
BrowserKernel visits source
          |
          v
Extract candidate claims/facts + provenance
          |
          v
Normalize / deduplicate / contradiction check
          |
          v
Update coverage + candidate ranking
          |
          +--> enough evidence? ---- yes --> synthesize
          |
          no
          |
          +--------------------------------> next gap
```

The unit of progress is **new useful evidence**, not page count.

---

# 3. Fact/evidence model

Use relational/JSON-backed records initially.

```json
{
  "fact_id":"...",
  "subject_key":"place.kyoto",
  "predicate":"recommended_duration_days",
  "value":3,
  "unit":"days",
  "source_id":"src_...",
  "source_url":"https://...",
  "source_title":"...",
  "quote_or_supporting_text":"...",
  "retrieved_at":"...",
  "published_at":null,
  "source_type":"official|editorial|community|other",
  "confidence":0.84,
  "freshness":"current",
  "sensitivity":"normal"
}
```

For non-tabular claims, `predicate/value` can be replaced by a normalized claim key + concise claim text.

## Required provenance

Every fact used in a final research output must be traceable to:
- URL;
- source title;
- retrieval timestamp;
- supporting text/structured field;
- optional publication date;
- browser observation/artifact ID.

---

# 4. Source model

```json
{
  "source_id":"src_...",
  "canonical_url":"...",
  "domain":"...",
  "title":"...",
  "source_type":"official",
  "retrieved_at":"...",
  "content_fingerprint":"...",
  "robots_or_access_notes":null,
  "status":"VISITED",
  "facts_added":12,
  "questions_supported":["q1","q3"]
}
```

Canonicalization prevents trivial duplicate URLs from appearing as source diversity.

---

# 5. Deduplication

Deduplication happens at several levels.

## URL-level
Normalize:
- fragment removal;
- tracking query removal when safe;
- canonical tag if trusted/available;
- redirects to final URL.

## Content-level
Hash normalized substantial content/text blocks to identify mirrors or duplicate pages.

## Claim-level
Normalize subject/predicate/value or semantic claim key.

When two sources repeat the same claim, store separate evidence links rather than duplicate working-memory text.

---

# 6. Contradiction handling

Do not overwrite old facts silently.

Example:

```text
claim_key: museum.entry_price
source A: $20, retrieved today
source B: $25, retrieved today
```

Create a contradiction group:

```json
{
  "group_id":"cg_...",
  "claim_key":"museum.entry_price",
  "members":["fact_A","fact_B"],
  "resolution":"UNRESOLVED"
}
```

Resolution policy can consider:
- official vs third-party source;
- publication/freshness;
- directness of evidence;
- independent corroboration.

If unresolved and material, the final answer should represent uncertainty rather than inventing consensus.

---

# 7. Source quality and diversity

Source ranking should not be a universal numeric truth score. Use task-dependent signals:

```text
PRIMARY/OFFICIAL
HIGH-QUALITY SECONDARY
COMMUNITY/EXPERIENCE
AGGREGATOR
UNKNOWN
```

Research planner can request diversity constraints such as:
- at least one official source for rules/schedules/prices;
- multiple independent sources for recommendations;
- community sources when subjective experience matters;
- recent sources for changing topics.

The exact rule depends on user intent.

---

# 8. Search/source discovery

BrowserAgent can discover sources through:
- ordinary web search pages;
- site search;
- links from trusted sources;
- later, direct search connector/API if available.

The planner maintains candidate source URLs separately from visited sources.

Source candidate scoring signals:
- relevance to current evidence gap;
- novelty/domain diversity;
- expected authority;
- freshness;
- previously visited/canonical duplicate;
- access cost/auth/CAPTCHA risk.

Do not let Qwen repeatedly search the same query because it forgot prior results.

---

# 9. Context construction for long research

Per model call include only:

```text
research goal
active evidence gap/question
current candidate/source context
small relevant evidence summary
important contradictions
remaining coverage requirements
current page observation
allowed action/decision schema
```

Never include:
- every visited URL;
- every extracted passage;
- entire event trace;
- entire final draft in every browser action call.

---

# 10. Fact retrieval

Begin with deterministic structured retrieval:
- exact keys;
- subject/entity;
- active question IDs;
- source/domain;
- FTS over concise fact text.

Only introduce embeddings if a measured query set shows that structured + FTS retrieval misses important relevant facts.

This prevents premature vector-memory complexity.

---

# 11. Coverage and stopping

A 100-page target is not a good stopping condition by itself. The agent should stop when research requirements are satisfied.

Example coverage state:

```json
{
  "q1":{"required":3,"independent_sources":4,"status":"SATISFIED"},
  "q2":{"required":2,"independent_sources":1,"status":"GAP"},
  "q3":{"required":1,"official_sources":1,"status":"SATISFIED"}
}
```

Stop when:
- required questions are satisfied;
- material contradictions are resolved or explicitly recorded;
- new source marginal utility stays below threshold;
- user-imposed page/time/token budget reached;
- access barriers make further research unproductive.

If stopped by budget, return remaining gaps rather than pretending completeness.

---

# 12. Marginal-utility / loop control

Track per source:
- new facts added;
- new questions supported;
- contradictions introduced/resolved;
- unique domain/source type;
- duplicate content ratio.

Detect research stagnation when the last N sources add no material evidence.

Then:
- broaden/alter search strategy;
- move to next evidence gap;
- stop if coverage is adequate.

---

# 13. Checkpointing and resume

Long research must survive restarts without re-reading everything.

Checkpoint:
- research plan/questions;
- coverage state;
- candidate source queue;
- visited canonical URLs/fingerprints;
- facts/evidence;
- contradictions;
- active page/subgoal;
- artifact references.

On resume:
- reconnect/start browser;
- current page may be discarded;
- facts/source queue remain authoritative;
- select next gap/source from database.

Browser page state is ephemeral; evidence state is durable.

---

# 14. Calculation and structured analysis

Tasks may require:
- sorting/ranking;
- totals/averages;
- date normalization;
- deduplication;
- filtering constraints;
- unit/currency normalization.

These should be deterministic code operations over extracted facts, not mental arithmetic hidden inside Qwen when precision matters.

This does **not** mean exposing arbitrary code execution to webpages. A narrow analysis engine can operate only on BrowserAgent's own structured data.

---

# 15. Synthesis separation

Do not continuously rewrite the final answer after every page.

Stages:

```text
collect evidence
-> coverage check
-> structured comparison/ranking
-> outline final response
-> synthesis model call(s)
-> citation/provenance validation
```

Before final output, validator checks every factual claim that should be sourced has linked evidence records.

---

# 16. Reliability metrics for long research

Measure:
- unique sources visited;
- duplicate-source ratio;
- facts/source;
- unsupported final-claim rate;
- contradiction-resolution rate;
- average context tokens/call;
- model calls/source;
- pages with zero useful facts;
- source diversity;
- resume success;
- coverage requirements satisfied;
- final-answer provenance completeness.

These are more informative than raw page count.

---

# 17. Security/privacy in long research

Research mode increases prompt-injection exposure because the agent consumes many untrusted pages.

Therefore:
- extracted text never changes authority/policy;
- no research page can authorize writes/uploads/filesystem access;
- sensitive task facts carry labels/origin;
- unexpected cross-origin transmission is blocked/gated;
- research mode should default read-only unless the user explicitly requests a write workflow.

Prompt-injection fixtures must include malicious content hidden in articles/reviews/search results.

---

# 18. Research-mode implementation phases

## R1 — Medium evidence task
- 5-10 sources;
- structured facts;
- canonical URL dedupe;
- simple coverage requirements.

## R2 — 20-50 sources
- FTS fact retrieval;
- contradiction groups;
- source scoring/diversity;
- stagnation detection.

## R3 — 100+ sources
- durable source queue;
- robust resume;
- source/content fingerprints;
- bounded context proven over long run;
- periodic research-plan revision.

## R4 — External evaluation
- AssistantBench-like tasks;
- WebChoreArena-style long-memory tasks;
- custom 100-site research benchmark with deterministic evidence checks.

Do not jump to R3 until R1/R2 evidence storage and completeness metrics work.

---

# 19. Example: “Find the 10 best places to visit in Japan”

Possible research plan:

```text
q1: gather candidate places from diverse reputable travel sources
q2: collect location/region and core attractions
q3: collect recommended season/timing
q4: collect travel/logistics considerations
q5: collect evidence of popularity/uniqueness
q6: apply user constraints/preferences
q7: ensure geographic/category diversity
q8: rank with explicit criteria
```

The browser layer simply visits/searches/extracts. The research state prevents the model from treating each page as a fresh standalone conversation.

---

# 20. Example: Canvas assignments -> Calendar

This is **not primarily a long-research problem** once authentication works.

Better architecture:

```text
BrowserKernel
 -> inspect each Canvas account/course
 -> persist Assignment facts
 -> normalize/deduplicate due dates
 -> show planned calendar writes
 -> user confirmation
 -> deterministic Calendar connector/API when available
 -> verify event coverage
```

This illustrates the larger BrowserAgent design: browser for arbitrary/authenticated discovery; structured state for transfer; deterministic integration for structured writes when possible.

---

# Completion definition for research mode

Long research is ready when the system can run a large source set while:

1. model context remains bounded;
2. visited-source duplication remains controlled;
3. facts survive browser/process restart;
4. every material final claim maps to provenance;
5. contradictions are visible rather than silently overwritten;
6. stopping is based on evidence coverage/budget, not a fixed loop count;
7. prompt injection from one source cannot alter capabilities;
8. the final output is reproducible from stored evidence without replaying the entire browsing session.

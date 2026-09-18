# Local Visual Grounding Research

## Decision
**Do not make a general VLM the mandatory visual fallback. Benchmark a small dedicated GUI grounder first; UI-TARS-2B is the leading first candidate, with ZonUI-3B and UGround-V1-2B as challengers. Confidence: 82%.**

This is a benchmark shortlist, not a production-model freeze. The architecture should permit zero learned visual model on actions that resolve semantically.

## Why a dedicated grounder is plausible
BrowserAgentV2 does not need its fallback model to plan the whole task. It needs a narrower primitive: given a screenshot and semantic target description, return candidate region/point plus enough evidence to abstain when ambiguous. A 2-3B GUI-specific model can therefore be evaluated independently of the planner.

## Candidate shortlist

### 1. UI-TARS-2B — first benchmark candidate
Public UI-TARS results show strong desktop grounding for a 2B model, including 90.7% Desktop-Text and 68.6% Desktop-Icon on ScreenSpot in published comparison tables; UI-TARS family results also show strong end-to-end computer-use performance relative to earlier open systems. A recent independent local wrapper reports roughly 4.1 GB VRAM and ~1.2 s element-find latency on an NVIDIA GPU, but those runtime numbers are anecdotal and must be reproduced locally.

**Why first:** small enough for RTX 4070 12 GB, purpose-built for GUI grounding, direct coordinate output, stronger public grounding evidence than older 2B-class alternatives.

**Risk:** benchmark grounding accuracy does not establish calibrated abstention, BrowserAgentV2-specific UI accuracy, or Apple Silicon runtime quality.

### 2. ZonUI-3B — accuracy challenger
ZonUI-3B reports 86.4 average on ScreenSpot-v2, with 93.8 Desktop-Text and 75.0 Desktop-Icon, exceeding the cited UI-TARS-2B average in its comparison. It is lightweight and resolution-aware, making it especially relevant to cross-resolution desktop use.

**Why challenger:** excellent reported grounding accuracy at only 3B parameters.

**Risk:** much smaller ecosystem/adoption and runtime/integration evidence; reported numbers require reproduction under our exact preprocessing/action contract.

### 3. UGround-V1-2B — second 2B challenger
UGround publishes a Qwen2-VL-based 2B variant with strong ScreenSpot results (reported 81.5 average in its agent-setting table, including 92.8 Desktop-Text and 63.6 Desktop-Icon).

**Why challenger:** same rough parameter class as UI-TARS-2B and a clean grounding-specific role.

**Risk:** lower reported aggregate accuracy than newer candidates and unknown local abstention behavior.

## Candidates not first-line
- **OS-Atlas 4B/7B:** useful research reference and broader action-model candidate, but heavier and public end-to-end OSWorld numbers do not justify it as the first narrow fallback grounder.
- **ShowUI-2B:** historically useful lightweight baseline, but newer 2-3B grounding candidates report materially stronger ScreenSpot-v2 results.
- **OmniParser:** useful as a screen parser / candidate generator, especially for OCR/icons, but its parsing pipeline is not equivalent to a semantic target grounder. It may later complement a grounder rather than replace one.
- **Large general VLM as mandatory fallback:** rejected until evidence shows it beats a dedicated small grounder enough to justify memory/latency cost.

## Required BrowserAgentV2 benchmark
Leaderboard accuracy is insufficient. Build one common fixture corpus with:
- desktop text targets
- unlabeled icons
- duplicate labels
- tiny targets
- disabled controls
- menus/popovers
- reflow between observation/action
- overlays obscuring the intended target
- multiple monitors / scaling if available
- intentionally absent target
- visually similar distractors

Measure:
1. hit accuracy (point inside true actionable region)
2. wrong-target rate
3. abstention precision/recall for absent/ambiguous targets
4. latency p50/p95
5. peak VRAM/RAM
6. cold-start/warm latency
7. resolution sensitivity
8. deterministic repeatability
9. verifier-confirmed action success after grounding

For this system, **wrong confident clicks matter more than raw benchmark accuracy**. The winning model should minimize unsafe wrong-target rate at an acceptable abstention level.

## Hardware hypothesis
- **RTX 4070 12 GB:** 2-3B GUI grounders are plausible resident or on-demand components. UI-TARS-2B has third-party evidence of ~4.1 GB VRAM; reproduce rather than trust it.
- **Apple Silicon 24 GB:** capacity is likely sufficient for quantized 2-3B models, but backend compatibility and latency are unresolved. Do not promise MLX/MPS parity without direct measurement.

## Model architecture implication
Do not couple planner and grounder lifetimes. Define a narrow grounding service/interface so the planner can be Qwen/generalist while the fallback grounder can be swapped or omitted. The grounder produces observation-local candidates only; it never owns task state or declares task success.

## Cheapest falsification experiment
Run UI-TARS-2B, ZonUI-3B, UGround-V1-2B, and the current generalist baseline on 100-200 labeled BrowserAgentV2 screenshots. If no dedicated model materially improves wrong-target/abstention performance at acceptable latency, remove the dedicated grounder from v1 and use the generalist visual route. If one wins, keep it only behind semantic-route failure/ambiguity.

## Provisional ranking
1. UI-TARS-2B — best first implementation candidate due to size + ecosystem + strong grounding evidence.
2. ZonUI-3B — strongest accuracy challenger; could become #1 after local runtime testing.
3. UGround-V1-2B — useful same-size control.

No production choice should be made until the BrowserAgentV2 fixture benchmark measures abstention and wrong-target behavior.
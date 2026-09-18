# Universal Computer-Use Research — Phase 0

**Research snapshot:** 2026-09-17

## Purpose

This memo asks a narrow question before ComputerAgent commits to a visual fallback architecture:

> How do current high-performing computer-use systems achieve broad or "universal" application coverage, and which parts can ComputerAgent reproduce locally on consumer hardware?

This is research/evidence, not a frozen architecture decision. `docs/BUILD_SPEC.md`, measured Phase 0 evidence, and `docs/DECISIONS.md` remain authoritative over this memo.

## Executive conclusion

The strongest public evidence does **not** support a one-mechanism design.

The important pattern is a **hybrid interaction system**:

1. use direct tools/APIs when available;
2. use browser semantics/code when that is more reliable and efficient;
3. use accessibility/semantic desktop control where the app exposes it;
4. fall back to screenshot-based visual grounding plus mouse/keyboard-style actions when semantics are insufficient;
5. independently observe and verify what actually changed;
6. isolate or hand off when the only available route would interfere with the user or cross a security boundary.

OpenAI's public trajectory strongly supports this. The original Computer-Using Agent (CUA) established a universal pixel/mouse/keyboard interface. ChatGPT agent then exposed multiple complementary routes — visual browser, text browser, terminal, APIs/connectors — instead of forcing every task through pixels. GPT-5.4 later explicitly combined both patterns: it can write Playwright code to operate software and can issue mouse/keyboard actions in response to screenshots.

For ComputerAgent, the likely target is therefore **not** "a local model that controls the mouse for everything." It is a deterministic controller that selects between semantic and visual routes, with a universal visual route available when necessary.

---

## 1. What OpenAI has publicly disclosed

### 1.1 Original CUA: universal GUI interface

OpenAI introduced Computer-Using Agent in January 2025 as a model trained to interact with graphical user interfaces without requiring OS- or website-specific APIs. Publicly described ingredients include:

- GPT-4o-class vision;
- advanced reasoning;
- reinforcement learning for GUI interaction;
- perception of raw screen pixels;
- action through mouse/keyboard-style computer commands;
- multi-step planning and self-correction.

This is the central reason CUA could generalize across unfamiliar interfaces: the interaction contract resembles a human's — observe pixels, choose an action, receive the changed screen, repeat.

This should be understood as **interface universality**, not guaranteed task reliability. A screenshot-and-coordinate interface can in principle address almost any visible software, while still failing because of grounding errors, hidden state, planning mistakes, timing, security boundaries, or long-horizon state loss.

Source:
- https://openai.com/index/computer-using-agent/

### 1.2 The computer-use action loop is explicit

OpenAI's current Responses API exposes computer actions such as click, double-click, drag, scroll, typing, waiting, and screenshots. The application executes the requested action and returns a screenshot/state result to the model for the next decision.

This reinforces a simple universal loop:

```text
screenshot/state
    -> model decision
    -> bounded computer action
    -> new screenshot/state
    -> repeat
```

Sources:
- https://developers.openai.com/api/reference/cli/resources/beta/subresources/responses
- https://platform.openai.com/docs/api-reference/responses-streaming/response/mcp_call_arguments

### 1.3 ChatGPT agent: universality comes from multiple routes, not vision alone

OpenAI's ChatGPT agent announcement describes a tool suite containing:

- a visual browser;
- a text-based browser;
- a terminal;
- direct API access;
- connectors;
- a virtual computer that preserves the task environment across tools.

The model can choose the path that best fits the subtask. This is a much stronger architectural lesson for ComputerAgent than simply copying the original screenshot loop.

Example:

```text
calendar data        -> API/connector
large text research  -> text/browser route
web form             -> browser/visual route
file transformation  -> terminal/code
GUI-only surface     -> visual computer use
```

Source:
- https://openai.com/index/introducing-chatgpt-agent/

### 1.4 GPT-5.4: code-based operation and visual operation in one model

OpenAI's March 2026 GPT-5.4 release is especially relevant. OpenAI says GPT-5.4 is capable of both:

- writing code to operate computers through libraries such as Playwright; and
- issuing mouse/keyboard commands in response to screenshots.

OpenAI reported:

- 75.0% on OSWorld-Verified;
- 67.3% on WebArena-Verified using DOM + screenshot interaction;
- 92.8% on Online-Mind2Web using screenshot observations alone.

These are model/provider-reported evaluation results, but they demonstrate the direction clearly: **semantic/code routes and visual routes are complementary**.

Source:
- https://openai.com/index/introducing-gpt-5-4/

### 1.5 What is *not* public

OpenAI does not publicly document the complete internal routing architecture used by current ChatGPT computer-use products. We should not claim to know:

- the exact router implementation;
- internal prompts;
- proprietary visual encoders/training data;
- exact recovery/state systems;
- how every ChatGPT product maps actions into host/VM input;
- every model or subsystem used internally.

The conclusions in this memo are limited to publicly documented behavior and reasonable architecture implications.

---

## 2. Independent evidence from Anthropic

Anthropic's computer-use research independently validates the pixel-action abstraction.

Claude's computer-use system was trained to:

- inspect screenshots;
- estimate screen coordinates;
- move a cursor;
- click;
- type through a virtual keyboard;
- sequence these actions from natural-language goals.

Anthropic specifically describes pixel/coordinate accuracy as a major training challenge. It also reports that computer-use training on a relatively small set of simple applications generalized to unseen software.

This is strong evidence that visual computer use can provide broad interface coverage without a per-application API.

Anthropic also documents important weaknesses:

- screenshot interaction can be slow and error-prone;
- screenshot observations are effectively a "flipbook," so short-lived UI changes can be missed;
- some seemingly simple operations remain difficult.

Implication: universal pixels are a valuable **fallback interface**, but not necessarily the optimal route for every action.

Sources:
- https://www.anthropic.com/news/3-5-models-and-computer-use
- https://www.anthropic.com/news/developing-computer-use

---

## 3. Three major visual-computer-use architectures

### Architecture A — End-to-end GUI model

```text
Screenshot
  -> GUI-native VLM
  -> thought/action
  -> coordinate/key action
```

Example: UI-TARS.

Strengths:
- minimal intermediate machinery;
- direct grounding and action generation;
- broad cross-application coverage;
- can reason about custom/canvas UIs that expose little accessibility metadata.

Weaknesses:
- model must solve perception, grounding, planning and action formatting together;
- every visual action can be comparatively expensive;
- grounding mistakes become real clicks unless the controller verifies/abstains;
- local quantization may hurt small-target grounding disproportionately.

### Architecture B — Screen parser + planner

```text
Screenshot
  -> screen parser
  -> structured interactable elements
  -> smaller planner
  -> selected element/action
```

Example: OmniParser V2.

Microsoft describes OmniParser as converting screenshots from raw pixel space into structured UI elements interpretable by general models. This separates visual parsing/grounding from task reasoning.

Strengths:
- compact observations;
- potentially cheaper planner prompts;
- explicit interactable regions;
- planner can reason over element IDs instead of raw coordinates;
- easier to inspect/debug than opaque direct grounding.

Weaknesses:
- parser can miss controls;
- additional inference stage;
- parser/model licenses must be audited before product redistribution;
- the parser still needs a fallback for unusual visual regions.

Sources:
- https://www.microsoft.com/en-us/research/articles/omniparser-v2-turning-any-llm-into-a-computer-use-agent/
- https://github.com/microsoft/OmniParser

### Architecture C — Hybrid semantic + visual

```text
requested action
      |
      v
semantic route available?
  | yes              | no
  v                  v
API / Playwright / AX     visual grounding
  |                  |
  +------- execute --+
           |
         observe
           |
         verify
```

This is the strongest current candidate for ComputerAgent.

It combines:

- speed and precision of semantics where available;
- broad coverage of pixels where semantics fail;
- deterministic policy/routing outside the model;
- explicit verification after state-changing actions.

OpenAI's public computer-use evolution, Cua Driver, Trope CUA, UI-TARS Desktop, and ComputerAgent's own Phase 0 results all point toward this architecture.

---

## 4. UI-TARS as a local visual specialist

ByteDance's UI-TARS project is one of the most relevant open-weight systems because it is explicitly trained for GUI grounding and computer use.

UI-TARS-1.5 supports output actions that can be post-processed into coordinates/actions. The repository reports strong GUI-specific benchmark results, including 42.5 on OSWorld (100-step setting) and 94.2 on ScreenSpot-V2. These are project-reported results and should be validated on ComputerAgent's own workload.

Sources:
- https://github.com/bytedance/UI-TARS
- https://huggingface.co/ByteDance-Seed/UI-TARS-1.5-7B

### Local fit

The official UI-TARS-1.5-7B repository is about 33.2 GB in original model files. Community GGUF Q4 variants exist and are advertised as runnable through llama.cpp, which makes a 12 GB RTX 4070-class benchmark plausible, but those community quantizations are not equivalent to an official accuracy guarantee.

ComputerAgent must therefore measure:

- actual resident VRAM/RAM;
- cold-load time;
- screenshot preprocessing time;
- time to first action;
- full grounding latency;
- coordinate/box accuracy;
- small-icon accuracy;
- duplicate-label ambiguity;
- quantization accuracy loss;
- abstention behavior.

Sources:
- https://huggingface.co/ByteDance-Seed/UI-TARS-1.5-7B/tree/main
- https://huggingface.co/mradermacher/UI-TARS-1.5-7B-GGUF

---

## 5. Qwen as a unified local comparator

Qwen3-VL explicitly advertises visual-agent and computer-use capabilities, including GUI recognition and spatial grounding. Qwen3-VL models exist in smaller 2B/4B/8B classes.

Qwen3.5 goes further by using a unified vision-language foundation. Official Qwen3.5-4B and 9B checkpoints accept images and are Apache-2.0 licensed. llama.cpp's current conversion code includes Qwen3.5/Qwen3-VL multimodal support.

This makes Qwen valuable as a second architecture:

- a unified planner/VLM can potentially perform semantic planning and visual grounding;
- UI-TARS can remain the specialized GUI-native comparator;
- OmniParser + Qwen provides a parsed-screen comparator.

Sources:
- https://github.com/QwenLM/Qwen3-VL
- https://huggingface.co/Qwen/Qwen3.5-4B
- https://huggingface.co/Qwen/Qwen3.5-9B
- https://github.com/ggml-org/llama.cpp/blob/master/conversion/qwen3vl.py

---

## 6. Agent S: orchestration matters as much as grounding

Agent S is important because its newer results show that high computer-use performance is not simply "better screenshot clicking." The framework separates orchestration/planning from grounding and recommends UI-TARS-1.5-7B as a grounding model while supporting stronger reasoning models through external providers.

Agent S reports strong OSWorld results, but this does **not** prove that a fully local 4B–9B stack will reproduce those results. It does show that:

- specialized grounding can be combined with a separate planner;
- orchestration and repeated verification materially matter;
- the GUI executor can remain swappable.

Source:
- https://github.com/simular-ai/Agent-S

---

## 7. Cua Driver and Trope CUA: execution fabric is already becoming commodity

Cua Driver is especially relevant to ComputerAgent because it implements many of the execution-layer concepts this project independently proposed:

- exact window targeting;
- screenshot + accessibility-tree snapshots;
- AX/pixel actions;
- background vs foreground delivery modes;
- action receipts;
- snapshot -> action -> verify loops;
- typed browser automation;
- platform-specific refusals when a safe route is unavailable.

Its public contract distinguishes window-level semantic/pixel actions from desktop-level foreground coordinate input. It also makes clear that background delivery is best-effort and platform/app dependent.

Sources:
- https://github.com/trycua/cua/blob/main/libs/cua-driver/rust/Skills/cua-driver/README.md
- https://github.com/trycua/cua/blob/main/docs/content/docs/reference/cua-driver/contracts.mdx

Trope CUA independently implements a similar architecture and explicitly requires action receipts to distinguish `ok` from background safety. It is MIT-licensed and uses public routes first, refusing unsafe fallbacks where appropriate.

Source:
- https://github.com/tropeai/trope-cua

### Critical macOS finding: universal *background pixel control* is not the same as universal GUI control

Cua's public macOS engineering write-up says its strongest background pixel delivery uses SkyLight `SLEventPostToPid` and other private mechanisms. That matters.

A screenshot model can universally *understand* and choose coordinates, but on macOS there is a separate execution question:

> Can those coordinates be delivered to an arbitrary background application without moving the user's real cursor or stealing focus?

Public AX semantics can do this for supported controls. Generic pixel input on the normal desktop is much harder. Cua's private-API route demonstrates technical feasibility, but private APIs introduce distribution, compatibility, maintenance and product-risk questions.

Source:
- https://github.com/trycua/cua/blob/main/blog/inside-macos-window-internals.md

This means ComputerAgent should treat these as two separate goals:

1. **Universal visual understanding / foreground control** — likely achievable through screenshot + GUI model.
2. **Universal non-interfering background control** — not guaranteed by public macOS APIs and must remain capability-gated.

---

## 8. What ComputerAgent should copy — and what it should not

### Copy the architectural pattern

ComputerAgent should strongly consider:

```text
User Goal
   |
Authoritative Controller
   |
Policy + State + Plan + Verification
   |
Route selection
   |
   +--> API / connector
   +--> Browser semantics / Playwright
   +--> OS accessibility
   +--> Parsed visual elements
   +--> GUI-native visual model
   +--> foreground/isolated pixel execution
   +--> human handoff
   |
Observe + Verify + Persist
```

### Do not copy the idea that pixels replace everything

ComputerAgent's existing Mac capability sweep already found:

- native apps can expose useful AX trees;
- browsers are better served through browser semantics than generic AX;
- VS Code/Monaco can be largely opaque to AX;
- AX calls can report success without proving the intended application effect.

Those results align with the external research. Pixels are essential for broad coverage, but semantics should remain the preferred route when they are reliable.

### Do not put route authority in the local model

The model should request an intent such as:

```text
activate control X
enter value Y
scroll region Z
```

The controller/router should determine whether that becomes:

- API call;
- Playwright locator action;
- AX semantic action;
- parsed-element action;
- visual coordinate action;
- isolated foreground action;
- handoff.

The model should not be trusted to decide that a background pixel route is safe simply because it thinks it is.

---

## 9. Recommended Phase 0 benchmark — do this before implementing the production visual layer

The next useful experiment is a **four-stack visual grounding race**, using exactly the same screenshot/action dataset.

### Stack A — semantic baseline

Use Playwright/AX where semantics exist.

Purpose: establish the speed/accuracy ceiling for structured interaction.

### Stack B — OmniParser V2 + small planner

```text
screenshot -> OmniParser -> element list/boxes -> planner selects ID
```

Candidates for planner:
- Qwen3.5-4B;
- Qwen3.5-9B if hardware permits.

### Stack C — UI-TARS-1.5-7B direct

```text
screenshot + instruction -> coordinate/action
```

Test a suitable quantization rather than assuming Q4 is accurate enough.

### Stack D — Qwen direct visual grounding

Candidates:
- Qwen3-VL-4B/8B;
- Qwen3.5-4B/9B.

Purpose: determine whether one unified model can eliminate a dedicated GUI grounder on some hardware tiers.

### Dataset

Build a deterministic screenshot suite containing both easy and adversarial GUI shapes:

- native Cocoa controls;
- Finder/system UI;
- browser page controls;
- Chrome/Safari;
- VS Code/Monaco editor targets;
- small icons;
- duplicate labels;
- icon-only buttons;
- disabled controls;
- overlapping/occluded controls;
- menus/popovers;
- scrolling content;
- custom/canvas-like regions;
- destructive-looking decoys where the correct answer is abstention.

For each screenshot/instruction pair, store an accepted target set or expected abstention.

### Metrics

Measure at minimum:

- correct target rate;
- point-inside-target rate;
- box IoU where appropriate;
- small-control accuracy;
- duplicate-label accuracy;
- abstention precision/recall;
- destructive false-positive rate;
- image preprocessing latency;
- model decision p50/p95;
- peak VRAM;
- peak RAM;
- cold-load time;
- quantization/version;
- output-schema validity.

### Hard safety rule

Do **not** begin by letting the visual model freely click real applications.

First benchmark grounding offline on screenshots. Only after a model passes grounding/abstention gates should the Phase 0 harness execute harmless fixture actions and independently verify postconditions.

---

## 10. Preliminary architecture recommendation

Based on the external research plus ComputerAgent's existing Phase 0 findings, the leading architecture is:

```text
                         COMPUTERAGENT
                              |
                   authoritative controller
                              |
                 bounded state + policy + plan
                              |
                        route request
                              |
                    InteractionRouter
         _____________|___________
        |             |           |
        v             v           v
 API/connector   Playwright/AX   Visual path
                                /           \
                               v             v
                         OmniParser       GUI VLM
                         + planner        UI-TARS/Qwen
                               \             /
                                \           /
                                  action
                                    |
                           delivery capability
                         /                     \
                        v                       v
               safe host route          foreground/isolated
                        \                       /
                         \                     /
                             observe/verify
                                   |
                                persist
```

The most important difference from a monolithic screenshot agent is that ComputerAgent's reliability/state/policy layer remains authoritative regardless of which executor is used.

---

## 11. Research decisions that are justified now

The following are supported strongly enough to guide the next experiment, but should not yet be treated as completed Phase 0 gates:

1. **Keep the hybrid execution hierarchy.** Public OpenAI architecture and independent systems support it.
2. **Treat screenshot/coordinate control as the universal compatibility fallback, not the preferred route.**
3. **Separate visual grounding quality from high-level planning quality.**
4. **Benchmark UI-TARS-1.5-7B, OmniParser V2 + Qwen, and direct Qwen visual grounding against the same dataset.**
5. **Keep verification external to the model.** A returned action or successful API call is not sufficient evidence of task completion.
6. **Keep background-safety capability-gated.** Universal visual grounding does not imply universal background pixel delivery.
7. **Audit Cua Driver/Trope CUA for selective reuse before rebuilding commodity cross-platform execution primitives from scratch.**

---

## 12. Open questions for the next research pass

Before freezing the visual architecture, answer experimentally:

- Can UI-TARS-1.5-7B Q4/Q5 maintain small-control grounding accuracy on RTX 4070 12 GB?
- Can it run acceptably on 24 GB Apple Silicon, and through which runtime?
- Does OmniParser V2 + Qwen3.5-4B beat UI-TARS on latency/VRAM while preserving grounding quality?
- Does direct Qwen3.5/Qwen3-VL grounding eliminate the need for a specialized grounder on standard hardware?
- What screenshot resolution/cropping strategy gives the best accuracy/latency tradeoff?
- Can a changed-region/crop strategy reduce visual latency after the first frame?
- Which local stack has the safest abstention behavior?
- Should ComputerAgent reuse Cua Driver/Trope for execution, or only study their contracts/tests?
- Is using private macOS input APIs acceptable for the product, or should unsupported background pixel actions explicitly require foreground/isolation/handoff?

Until those are measured, do not freeze the production `VisionAdapter` implementation.

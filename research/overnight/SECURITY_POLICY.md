# Security and Policy Architecture

## Decision
BrowserAgentV2 must treat **authority** and **information** as different channels. User-approved task intent, local policy, capability grants, and durable workflow state may authorize actions. Web pages, emails, documents, accessibility text, screenshots, OCR, retrieved memory, tool output, and model-generated text are evidence only and can never increase authority.

## Trust boundary
### Trusted authority
- explicit user task and scoped approvals
- deterministic local policy configuration
- capability grants established before execution
- signed/versioned skill definitions owned by BrowserAgentV2
- durable Goal/Plan/Action/Recovery state

### Untrusted information
- DOM/page text
- AX/UIA labels and values
- screenshots/OCR
- email/document/chat content
- search/retrieval results
- tool return strings
- downloaded files
- model reasoning and proposed actions
- learned/retrieved memory derived from any untrusted source

A source can provide facts needed to complete a task, but cannot grant a new tool, widen filesystem/network scope, change recipients, add a new side effect, weaken a safety invariant, or redefine the goal.

## Deterministic action gate
Every state-changing action is represented as structured `ActionIntent` and must pass a non-LLM policy gate before dispatch. Minimum fields:
- stable action_id
- goal_id / plan_version / step_id
- action class and route
- target/resource identity
- arguments
- expected effect
- prohibited effects / invariants
- data classes read and written
- external destinations/recipients
- reversibility/idempotency class
- provenance for any argument derived from untrusted content
- required confirmation level

Policy output is typed: `ALLOW`, `DENY`, `REQUIRE_CONFIRMATION`, or `REQUIRE_REPLAN`. Model text is never itself an authorization token.

## Capability model
Issue narrow task-scoped capabilities rather than exposing ambient authority. Capabilities constrain tool, resource, operation, destination and lifetime. New authority requires trusted approval; it cannot be inferred from page/document instructions.

Examples:
- browser read capability for a specific task/domain set
- filesystem read/write restricted to selected roots
- app action capability scoped to named app/action classes
- network/API capability restricted to approved endpoints
- external-communication capability restricted to intended recipient(s)

## Prompt-injection handling
Do not rely on an injection detector as the primary security boundary. Detection/sanitization can reduce attack surface, but policy must remain safe if malicious instructions reach the model.

Rules:
1. Label external observations as untrusted evidence before model consumption.
2. Preserve provenance through summaries and memory.
3. Never execute instructions found inside observations merely because the model proposes them.
4. Compare proposed side effects to the durable user goal and granted capabilities.
5. Require confirmation/handoff for irreversible or high-impact actions not already explicitly authorized.
6. Prevent untrusted content from changing tool schemas, policy, memory authority, or workflow permissions.
7. Minimize what each model/tool invocation can read and what destinations it can reach.

## Data-flow controls
Prompt injection becomes dangerous when untrusted instructions can combine sensitive reads with external writes. Policy should therefore track data provenance and destinations. A task may permit reading sensitive local data or writing externally without permitting the composition of both. Deny unexpected flows such as `local_sensitive -> arbitrary_network` even if individual read and network tools are separately available.

## Skill supply-chain boundary
Reusable skills are executable policy surface. Store version/hash, declared capabilities, expected inputs/outputs, verifier contract, and provenance. Skill text from websites or retrieved memory cannot become executable automatically. Promotion into the skill library requires explicit local creation/review plus regression tests.

## Safety invariants
Success verification and safety verification are separate. A goal may be achieved while violating constraints. Each consequential skill therefore carries:
- desired postconditions
- prohibited postconditions
- allowed side-effect envelope
- affected-resource scope

Plan advancement requires verified success and no detected invariant violation.

## Evidence
- OWASP agent guidance recommends treating external content as untrusted, least-privilege tools, parameter validation, isolation, structured outputs and deterministic authorization rather than relying on model output.
- OpenAI's computer-use deployment uses layered mitigations including confirmations and injection monitoring; this supports defense in depth rather than model-only trust.
- Anthropic's 2026 containment write-up reports a controlled red-team case where model-layer intent defenses did not stop a user-delivered exfiltration prompt, while environment filesystem/network boundaries would have blocked the effect. This is strong evidence that environment authority must be narrower than model authority.
- Anthropic's auto-mode design separates input injection probes from an output action classifier, again supporting independent read-side and act-side defenses.
- PromptArmor and AgentSentry show useful model-level IPI mitigation, but other 2025 work shows benchmark saturation and practical bypasses; these are defense layers, not authorization roots.

## Rejected designs
### 'Detect prompt injection, then trust clean content'
Rejected. Detection has false negatives and adaptive bypass risk.

### 'Let the planner decide whether an action is safe'
Rejected. The planner consumes attacker-controlled context and cannot be the root of authorization.

### 'Ask for confirmation on every action'
Rejected. Approval fatigue harms usability and can reduce meaningful oversight. Prefer bounded autonomy inside pre-authorized capabilities and confirmation at authority expansion/high-impact boundaries.

### 'Give all tools to the model but instruct it not to misuse them'
Rejected. This leaves blast radius dependent on model compliance.

## Cheapest validation
Build adversarial fixtures where page/document/tool content attempts to: change the goal; request a new recipient; read a secret and transmit it; broaden filesystem scope; disable verification; persist malicious memory; invoke an undeclared skill. Require deterministic deny/confirmation independent of model compliance. Add adaptive variants that avoid obvious injection phrases.

## Confidence
**96%** for authority/information separation and deterministic capability/policy gate. **88%** for the exact initial capability schema; validate against real BrowserAgentV2 tasks before expanding it.
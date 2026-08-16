# Case Studies — Five Archetypes

The modules built the components. These map them back onto real products.

Five archetypes, chosen so that together they cover nearly every company that
says *"we build AI agents for X."* Most such companies are a variant of one of
these with different domain data, different tools, and a different regulator.

| # | Archetype | Core shape | Dominant modules | The hard part |
|---|---|---|---|---|
| 1 | [Coding agent](coding-agent.md) | deep loop, few tools, long horizon | 02, 05, 06 | context management + verification |
| 2 | Deep research | orchestrator + parallel workers | 06, 04, 05 | search quality, citations, when to stop |
| 3 | Computer use | screenshot → action loop | 02, 10 | grounding, error recovery, latency |
| 4 | Support agent | RAG + tools + strict routing | 04, 08, 10 | evals, escalation, brand risk |
| 5 | Document workflow | pipeline with LLM steps + human gate | 03, 06, 08 | extraction accuracy, review UX, audit |

**Coding agent** — you describe a change, it reads the repo, edits files, runs
tests, iterates until green. The purest agent loop in production, with
surprisingly few tools. Special because the environment hands it free ground
truth: tests pass or fail without a human. *Claude Code, Cursor, Devin, Copilot
agent mode, Amp, Jules, Codex.*

**Deep research** — a question in, a cited report out, ten minutes later. A lead
agent decomposes, parallel subagents search with isolated contexts and return
findings, the lead synthesizes. Search quality dominates model quality, and
knowing when to stop is unsolved. *OpenAI/Google/Anthropic deep research modes,
Perplexity, Elicit, Hebbia, AlphaSense, Glean.*

**Computer use** — the agent sees a screen and drives a mouse. Enormous step
counts, so error recovery is the whole game, and a UI offers none of the hard
limits a tool API can enforce. Exists because of the vast tail of enterprise
software with no API. *Anthropic computer use, OpenAI Operator, Browserbase,
Browser Use, Skyvern, Manus; UiPath from the RPA side.*

**Support agent** — resolves customer conversations end to end and escalates the
rest. Shallow loops, deepest reliability engineering of the five, because many
of these companies bill per resolution — module 08's threshold sweep *is* their
pricing model. *Sierra, Decagon, Intercom Fin, Ada, Forethought, Agentforce;
Parloa and PolyAI on voice.*

**Document workflow** — the enterprise archetype: unstructured documents in, a
business decision and a money movement out. trigger → extract → enrich → rules →
confidence route → human review → irreversible action, on a durable engine. The
LLM occupies two or three steps; the rest is deterministic code, and the review
queue is the actual product. *Harvey, Legora, Robin AI (legal); EvenUp, Sixfold,
Federato (insurance); Ramp, Brex (AP); Anterior, SmarterDx (health); Rossum,
Klarity, Reducto (extraction).*

Company names are illustrative and were accurate as of writing; this space moves
fast. No company's internal architecture is public — what these documents
describe is inference from product behavior, published engineering writing, and
what the constraints force.

## What this taxonomy excludes

These five classify **agent applications built on somebody else's foundation
model**. That is the right scope for the question "what is this AI agents
company actually doing," and the wrong scope for "classify every AI company."
Deliberately outside:

- **Model labs**, including domain-specific ones. If you train the model, you're
  not an app on top of one. Harmonic (formal mathematics verified in Lean) is a
  good example — and see below, because it's instructive.
- **Infrastructure and tooling** — vector databases, eval platforms,
  observability, gateways, document parsers, browser infrastructure, inference
  serving. They *sell to* the five rather than instantiate one.
- **Generative media** — image, video, music, voice. Usually one forward pass:
  no loop, no tools, no state. Architecturally not an agent at all.
- **Inline copilots** — autocomplete, "rewrite this paragraph," summarize this
  thread. One call, no agency. A huge category that gets called "AI agents" in
  marketing and is not.
- **Robotics and embodied AI** — the action space is torque, not tool calls.

Two habits keep the taxonomy useful rather than procrustean. First, **classify
by architecture, not by vertical**: "AI for insurance" tells you nothing, while
"documents in, decision out, human gate before payment" tells you almost
everything. Second, **expect combinations**: a legal product is often a document
workflow with a deep-research feature bolted on, and a support product usually
grows a document-workflow back office.

### The instructive edge case

Harmonic doesn't fit — they train their own models — but architecturally their
system is the *coding agent taken to its limit*. Coding agents work because the
environment provides free ground truth: tests pass or fail with no human
involved. Harmonic replaces the test suite with a formal proof checker, which is
not merely a good signal but a **sound** one. Same propose → verify → correct
loop from module 02, with the oracle upgraded from "probably right" to "provably
right."

That also explains the business: a cheap, automatic, trustworthy verifier is
exactly what reinforcement learning needs. Math and code are the two domains
where you can manufacture unlimited training signal without human labelers,
which is why frontier progress has been fastest there.

For a second instance of the same move — a coding-shaped agent whose verifier is
upgraded from "probably right" to ground truth — see the curious example below.

### A curious example: the smart-contract exploit agent

Not an archetype, but the sharpest illustration in the repo of *why the
archetypes work*. Point an agent at a deployed smart contract, let it write an
exploit and run it against a forked copy of the real chain, and score it on
whether the balance went up. It's the [coding agent](coding-agent.md) with its
test suite replaced by **profit on a fork** — a verifier that can't be faked —
which is why it sits next to Harmonic rather than inside an archetype. Anthropic
open-sourced the harness (SCONE-bench), so for once the architecture is published
code rather than inference. **[Read it →](smart-contract-exploit-agent.md)**

And it demonstrates the question worth asking any company making a correctness
claim. "Hallucination-free" here is *scoped*: what's guaranteed is that the Lean
proof type-checks. The soft edges are at the boundary — autoformalizing an
informal problem into Lean (a perfect proof of the wrong theorem is still
wrong), and interpreting the result on the way out. That doesn't make the claim
false; it makes it precise. It's the same shape as module 07's server-side
guardrail: the guarantee is real, and it only covers what's actually behind the
boundary.

## How to read these

Each case study answers the same five questions:

1. What does the product actually do?
2. What is the architecture, probably?
3. Which modules does it use, and how?
4. What is hard about this archetype specifically?
5. What would you ask a company that claims to build one?

---

*Part of a [learning repo](../README.md) on how AI agents are built. Notes and code
co-authored with Claude Opus 5 via Claude Code, then run end-to-end against the real API.*

# 06 — Orchestration

Modules 00–05 built one agent. This module is about the layer above: how
companies arrange LLM calls, tools, and code into *systems* — and how they keep
those systems alive across failures, restarts, and week-long human approvals.

## The spectrum: who decides the next step?

Everything in this space sits on one axis — how much of the control flow is
decided by your code vs. by the model:

| Pattern | Next step decided by | Example |
|---|---|---|
| Single call | — | classify this email |
| **Prompt chain** | code (fixed sequence) | extract → validate → draft letter |
| **Routing** | code, after a model classification | cheap model for easy tickets, agent loop for hard ones |
| **Parallelization** | code (fan out, fan in) | run 5 extractions at once; vote or merge |
| **Orchestrator–workers** | model plans, code dispatches | lead agent assigns subtasks to specialists |
| **Evaluator–optimizer** | code loops until a model says "good" | draft → critique → redraft |
| **Agent loop** (module 02) | model, every step | open-ended tasks with tools |

Two rules of thumb the industry converged on. First: **use the least agency
that solves the problem** — deterministic chains are cheaper, faster, more
debuggable, and auditable; save the agent loop for steps that are genuinely
open-ended. Second: most production systems are *hybrids* — a deterministic
workflow backbone (the claims state machine) with small agent loops embedded
inside the open-ended steps (the coverage-check research). "Workflow vs agent"
is a per-step decision, not a product identity.

## Subagents: context isolation is the real reason

The word "multi-agent" suggests personalities collaborating. The engineering
reality is mostly about **context windows**. From module 05: context is scarce,
expensive, and rots as it fills. A subagent is a *fresh context window* that:

1. receives only its subtask and the data relevant to it,
2. burns thousands of tokens reading/searching/reasoning,
3. returns a few hundred tokens of conclusions — and is thrown away.

The orchestrator's window accumulates *findings, not process*. That's the
pattern in Claude Code (a search subagent reads 50 files so the main context
receives one paragraph) and in deep-research products (parallel workers each
chase one thread of the question). Specialization ("you are a fraud reviewer")
helps focus, but isolation is the load-bearing feature — a subagent also can't
be confused by, or leak, context it never saw.

When multi-agent *hurts*: agents that must share evolving state (two agents
editing the same code) coordinate badly — the field's hard-won lesson is that
parallel **reads** scale well, parallel **writes** don't. And every hop between
agents is a lossy, token-expensive game of telephone. Companies advertising
"12 specialized agents" often have a workflow diagram wearing costumes; ask
what any two agents actually say to each other.

## Durable execution: workflows that survive

A claims workflow runs for days: LLM steps fail with rate limits, humans take
until Thursday, servers restart mid-claim, and the payment step must never run
twice. The naive version — one long-running function — dies with its process.

The fix is old and boring: **write every step's result to a journal before
moving on**. On restart, re-run the workflow function from the top; steps
already in the journal *replay* instantly from stored results (no cost, no
side effects) until you reach the first step that hasn't run yet — then real
execution resumes. The workflow is now crash-proof, restartable, and has a
free audit log. Add "a step can also be *wait for signal X*" and week-long
human approvals become trivial: the workflow simply isn't running while it
waits; the journal holds its place.

This is exactly what **Temporal**, **Inngest**, **Trigger.dev**, and AWS Step
Functions productize (vocabulary: the journaled function is a *workflow*, the
steps are *activities*, replay is how recovery works, and workflow code must be
deterministic — all randomness and LLM calls live inside activities, whose
recorded results are what replay returns). LLM pipelines made these engines
newly popular for three reasons: LLM calls are flaky (retries per step),
expensive (never re-pay for steps 1–4 because step 5 crashed), and surrounded
by long human-in-the-loop waits. `example.py` builds the whole mechanism in
~15 lines — the point, as usual, is that the concept is small even when the
product around it is big.

## Where this shows up

- **Claims/document companies**: durable workflow backbone + LLM activities +
  human-approval signals (the architecture we sketched in the module-03 chat).
- **Deep research**: orchestrator–workers with parallel subagents, then synthesis.
- **Coding agents**: one main loop + read-only subagents for search/review.
- **Support platforms**: routing first (cheap model triages), agent loop only
  for the hard residue, escalation as a workflow signal.

## Vocabulary

| Term | Meaning |
|---|---|
| orchestrator / worker | the planner-dispatcher and the specialists it assigns |
| context isolation | subagent's window is fresh; only conclusions come back |
| fan-out / fan-in | run subtasks in parallel, merge results |
| durable execution | journaled workflows that resume after any crash |
| workflow vs activity | deterministic sequencing code vs the retryable steps it calls |
| replay | recovery by re-running with recorded step results |
| signal | external event a workflow can durably wait for (human approval) |
| idempotency | safe to attempt twice, executes once — mandatory around money |

## Run it

```bash
uv run modules/06-orchestration/example.py
```

Demo 1: an orchestrator plans questions for two specialist subagents (coverage,
consistency) that work in isolated contexts; the lead synthesizes findings it
could never have afforded to research in its own window. Demo 2: a six-step
claims workflow journals every step, **crashes** after step 3, and on rerun
replays steps 1–3 free before executing 4–6 — including an idempotent payment.

---

*Part of a [learning repo](../../README.md) on how AI agents are built. Notes and code
co-authored with Claude Opus 5 via Claude Code, then run end-to-end against the real API.*

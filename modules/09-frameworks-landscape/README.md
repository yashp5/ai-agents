# 09 — Frameworks Landscape

Every previous module used the raw API on purpose. That was not asceticism —
it was so that this module reads as *recognition* rather than magic:

> **A framework doesn't give you an agent. It gives you someone else's version
> of the loop you already wrote in module 02, plus infrastructure you'd
> otherwise build yourself.**

The question is never "should I use a framework." It's **which of these three
things am I outsourcing** — the loop, the workflow, or the integrations — and
frameworks bundle them together whether you wanted that or not.

## The three things frameworks actually sell

| Layer | What it is | Should you outsource it? |
|---|---|---|
| **The loop** | model → tool call → result → repeat (module 02) | Rarely. It's ~40 lines and it's where your product lives. |
| **The workflow** | persistence, retries, human gates, resume (module 06) | Usually yes. This is real infrastructure and it's tedious to get right. |
| **Integrations** | tool schemas, provider adapters, connectors | Often — though MCP (module 07) increasingly does this better. |

Most of the disappointment with frameworks comes from wanting layer 2 and being
forced to accept layer 1 — someone else's prompt, someone else's control flow,
in the one place you most need to iterate.

## The landscape, honestly

**LangGraph** (used in `example.py`). A graph of nodes over a typed state, with
a checkpointer. Not really an "agent framework" — a workflow engine that happens
to be good at LLMs. Its `interrupt()` + checkpointer combination is genuinely
the thing most teams would otherwise hand-build, and swapping `InMemorySaver`
for the Postgres saver is the whole reason to adopt it. Verbose, and the
LangChain lineage means abstractions can stack deep. The most common serious
choice in production Python.

**Claude Agent SDK** (`claude-agent-sdk`). The harness behind Claude Code,
packaged: the loop, plus context management, subagents, hooks, permissions, and
the filesystem/bash tooling. Highest leverage when your product resembles a
coding agent or anything that works on a repo or a machine; opinionated by
design, which is exactly why it's good at that shape.

**OpenAI Agents SDK.** Deliberately small — agents, handoffs, guardrails,
sessions, tracing. Handoffs (one agent transferring to another) map cleanly to
support-style routing. Its virtue is that it stays close to the raw API, so
there's less to unlearn.

**CrewAI / AutoGen / multi-agent frameworks.** Role-playing crews and
conversational agent societies. Excellent demos; the "researcher + writer +
critic" pattern is seductive. In production, most teams who start here end up
back at explicit workflows, for module 06's reason: multi-agent is a context
isolation technique, not a personality simulator, and unconstrained agent
conversations are hard to eval and expensive.

**Temporal / Inngest / Step Functions.** Not AI frameworks at all — durable
execution engines. If your product is really a business workflow with LLM steps
(the extract → look up → check → gate → letter → pay skeleton), this is often
the *correct* answer, with raw API calls inside the activities. Boring,
battle-tested, and the retries and versioning story is far ahead of anything
AI-native.

**Pydantic AI, Mastra, Vercel AI SDK, LlamaIndex, DSPy** — worth knowing the
shapes: typed-Python-first, TypeScript-first, streaming-UI-first,
retrieval-first, and prompt-optimization-first respectively.

## What `example.py` shows

The same task three ways. Part 1 is module 02's loop (~35 lines). Part 2 is
`create_agent` (~14 lines) doing the identical thing — same two tool
calls, same answer, and now the loop is invisible. Part 3 is the version worth
importing a dependency for: a `StateGraph` with conditional routing (payouts
≥ $1,000 need approval), a checkpointer, and an `interrupt()` that pauses the
run mid-graph. The output is the point:

```
PAUSED at the human gate: {"question": "Approve this payout?", "payout_usd": 2200.0, …}
graph.get_state() -> next=('approve',), state={'policy_number': 'HP-40122-B', …}
```

The run is now durable state rather than a Python stack frame — the process can
exit and resume next week on another machine. That's module 06's journal and
module 08's review queue, handed to you for one import. Notice also that
`price_node` contains no LLM call: money math is deterministic code, and the
graph makes that separation structural.

## The costs, which nobody puts in the README

- **The prompt becomes theirs.** Module 08 insists a prompt is code you version
  and eval. A framework's built-in prompt is code you didn't write, can't see
  without reading the source, and that changes on upgrade.
- **Debugging goes through their stack.** Your bug is a model behaviour; your
  traceback is six frames deep in a `Runnable`.
- **Abstraction churn.** These libraries have already renamed their core
  concepts more than once. Writing this module hit it live: the prebuilt agent
  moved from `langgraph.prebuilt.create_react_agent(..., prompt=)` to
  `langchain.agents.create_agent(..., system_prompt=)` — new module, new kwarg,
  with the old path emitting "removed in V2.0". Your code ages against someone
  else's roadmap.
- **They flatter you into agency.** Given a framework built for agents,
  everything looks like it needs an agent. Module 06's rule still holds: use
  the least agency that solves the problem, and most production "agents" are
  workflows with two LLM calls in them.

## What companies actually do

The pattern that keeps recurring at teams doing this seriously: **raw API calls
in a thin internal library, plus a real workflow engine.** They keep the prompt
and the loop — the parts that need daily iteration and eval — and import the
parts that are undifferentiated (durability, retries, tracing).

Frameworks earn their place at the other end: prototypes, teams new to the
space who benefit from the vocabulary, and products whose shape genuinely
matches the framework's opinion (a coding agent on the Claude Agent SDK, a
graph-shaped workflow on LangGraph).

When you're evaluating a company, "which framework?" is a weak question. The
strong versions: *what do you own versus import, and why?* And: *when the model
does something wrong, how many layers do you have to go through to find out
why?*

## Vocabulary

| Term | Meaning |
|---|---|
| ReAct agent | reason→act→observe loop; the prebuilt everyone ships |
| node / edge / state | a step, a transition, the typed dict flowing through |
| checkpointer | where graph state persists; swap it to change durability |
| interrupt / resume | pause mid-run for a human, continue later |
| handoff | one agent transferring control to another (Agents SDK) |
| crew | a set of role-playing agents (CrewAI) |
| durable execution | Temporal-style journal + replay (module 06) |

## Run it

```bash
uv run modules/09-frameworks-landscape/example.py
```

Adds `langgraph` and `langchain-anthropic` — the only modules in this repo with
a framework dependency, which is itself the point.

---

*Part of a [learning repo](../../README.md) on how AI agents are built. Notes and code
co-authored with Claude Opus 5 via Claude Code, then run end-to-end against the real API.*

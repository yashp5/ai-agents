# Case Study 1 — The Coding Agent

*Claude Code, Cursor, Devin, Copilot agent mode, Amp, Jules, Codex, Aider.*

The deepest agent loop that currently ships to real users, and the best place to
start — partly because it exercises the most modules, and partly because you can
verify almost everything in this document by watching one work.

## 1. What the product actually does

You describe an outcome in English. The agent explores an unfamiliar codebase,
forms a plan, edits files, runs the tests, reads the failures, fixes them, and
repeats until the task is done — over minutes to hours, across hundreds of model
calls, mostly unattended.

Note what that *isn't*: it isn't autocomplete, and it isn't a chatbot that emits
code for you to paste. The distinguishing feature is **agency over a real
environment** — a filesystem, a shell, a test runner — which is exactly module
02, scaled up.

## 2. The architecture, probably

```
   user prompt
        │
        ▼
 ┌──────────────────────────────────────────────────────────┐
 │  SYSTEM PROMPT (large, stable, cached)                   │
 │   tool definitions · conventions · repo context file     │
 └──────────────────────────────────────────────────────────┘
        │
        ▼
 ┌─────────────── THE LOOP (module 02) ─────────────────────┐
 │                                                          │
 │   model ──▶ tool_use ──▶ execute ──▶ result ──▶ model    │
 │     ▲                        │                           │
 │     │                    ┌───┴────────────────────┐      │
 │     │                    │ read · edit · bash     │      │
 │     │                    │ grep · glob · subagent │      │
 │     │                    └───┬────────────────────┘      │
 │     │                        │                           │
 │     │                   ┌────▼──────┐                    │
 │     │                   │ PERMISSION│  irreversible?     │
 │     │                   │   GATE    │  ask the human     │
 │     │                   └────┬──────┘                    │
 │     │                        ▼                           │
 │     │                  the filesystem / shell            │
 │     │                        │                           │
 │     └────────────────────────┘                           │
 │                                                          │
 │   when context fills ──▶ COMPACT (module 05) ──▶ continue│
 └──────────────────────────────────────────────────────────┘
        │
        ▼
   verification: tests, type checker, linter, build
        │
        └──▶ failures re-enter the loop as tool results
```

Three things about that diagram are the whole archetype: the loop is boring, the
tool list is short, and **verification closes the circuit** without a human.

## 3. The tools — and why there are so few

The surprising thing when you first look at a serious coding agent is how small
the tool set is:

| Tool | Why it exists |
|---|---|
| `read` | see a file (with line numbers, so edits can be anchored) |
| `edit` | exact string replacement, not "rewrite the file" |
| `write` | create new files |
| `bash` | the universal escape hatch: tests, git, build, anything |
| `grep` / `glob` | find code without reading the whole repo into context |
| subagent | delegate a search-heavy task and get back the conclusion |

That's roughly it. There is no `refactor_function`, no `add_import`, no
`rename_symbol`. The lesson generalizes: **a few sharp, general tools beat many
specific ones**, because the model composes them in ways you didn't anticipate,
and every extra tool is permanent tokens in every request plus one more chance
to pick wrong.

Tool *design* carries more weight here than anywhere else:

- **`edit` uses exact string matching and fails loudly** when the old text isn't
  unique or doesn't match. A fuzzy edit tool that silently patches the wrong
  place produces plausible corrupted files — the worst failure mode available.
- **Read-before-edit is enforced**, so the model can't edit a file it hasn't
  seen. That's a state machine in the harness, not an instruction in the prompt
  (module 08's rule: guardrails live where the model can't reach them).
- **Error messages are prompts.** "String not found; here are the 3 closest
  matches" recovers; "Error: edit failed" retries blindly. This is where module
  02's self-healing behavior actually lives.

## 4. Which modules it uses, and how

| Module | Where it shows up |
|---|---|
| 01 tool use | the six tools above; schemas are small and hand-tuned |
| **02 agent loop** | the entire product; hundreds of iterations per task |
| 03 structured output | tool arguments; also plan/todo state |
| 04 RAG | **often absent** — see below |
| **05 memory & context** | compaction, file re-reads, a persisted project context file |
| 06 orchestration | subagents for search; plan mode as an explicit phase |
| 07 MCP | how third-party tools (Sentry, Postgres, browsers) get attached |
| 08 reliability | SWE-bench and internal evals; permission gates as guardrail |
| 09 frameworks | rarely — the loop is the product, so nobody outsources it |
| 10 production | prompt caching, sandboxing, the injection surface |

**The RAG surprise.** You would expect embedding search over the codebase, and
most early tools did exactly that. Serious agents lean instead on `grep`, `glob`
and reading files — *agentic* retrieval (module 04's demo 4) rather than
pipeline retrieval. Reasons: code has exact identifiers, and `grep
"processPayment"` beats fuzzy semantic similarity; an index goes stale the moment
the agent edits a file; and the agent can iterate its own search, which a
one-shot top-k cannot. Embeddings still help on "where is the code that handles
refunds" when you don't know the words — hybrid, not either/or.

**Context is the real engineering.** A long session blows through any context
window, so: compaction with a structured handoff (module 05), subagents to keep
grep noise out of the main thread (module 06), tool results truncated with a way
to fetch more, and a project file (`CLAUDE.md`, `.cursorrules`) that re-injects
durable conventions every session — module 05's long-term memory, in the
simplest possible form.

## 5. What's hard about this archetype

**Verification is a gift, and it's partial.** Tests are a real oracle, but they
only cover what's tested. An agent can make everything green by weakening an
assertion or adding an early return. The mitigation is procedural — run the
tests *before* changing anything to establish a baseline, prefer failing-test
first, review diffs — and it's why "the tests pass" is necessary, not
sufficient.

**Context management over hours.** The failure isn't running out of tokens; it's
*context rot* — the agent forgets a constraint from twenty compactions ago and
undoes its own earlier fix. Module 06's lesson bites hardest here: summaries
starve downstream steps, so what survives compaction determines whether the
session stays coherent.

**Cost and latency.** Every turn re-sends the conversation, so cost grows O(N²)
across a session (module 10). Prompt caching is not an optimization here, it's
load-bearing — the system prompt and tool definitions are large, stable, and
sent on every one of hundreds of calls. Hundreds of calls also means p99 matters
more than p50.

**The blast radius is a shell.** This archetype hands a model `bash` on a
developer's machine, with credentials in the environment and network access. The
defenses are module 10's: permission prompts before irreversible or unfamiliar
commands, allowlists for the routine ones, sandboxing/containers for autonomous
runs, and no ambient credentials where avoidable.

**And therefore, the injection surface is enormous.** A coding agent reads issue
comments, dependency READMEs, test fixtures, API responses, log output — all
untrusted text arriving inside tool results. It also has private data (your repo,
your env) and the ability to act (bash, network). That is module 10's lethal
trifecta, fully assembled, which is why the permission gate is a product feature
rather than an annoyance.

**Evaluation is genuinely hard.** SWE-bench and friends measure "did the patch
resolve the issue," which is a trajectory-level eval (module 08) on tasks with
real ground truth — better than most archetypes get, and still narrow: it says
nothing about whether the change is idiomatic, whether the agent asked a
clarifying question it should have asked, or whether it burned $12 getting
there.

## 6. Why this archetype works better than the others

Worth stating plainly, because it's the load-bearing insight for the remaining
four case studies:

> The environment provides **free, automatic, honest ground truth**.

The compiler doesn't flatter the model. Tests don't hallucinate. The agent can
check its own work hundreds of times without a human, which means errors get
caught in the loop instead of in production. No other archetype has this:
support agents can't verify that an answer satisfied the customer, research
agents can't verify a synthesis is faithful, document workflows can't verify a
payout is correct — all three ultimately need a human.

This is also why coding and math are where model capability has advanced
fastest: a cheap automatic verifier is exactly what reinforcement learning
needs. When you evaluate any agent company, **"what is your verifier?"** is the
sharpest single question you can ask. Most don't have one, and their engineering
is largely about substituting for its absence.

## 7. Who builds these

- **Anthropic — Claude Code**: terminal-first, MCP-native, subagents and hooks.
- **Cursor**: the IDE-integrated version; the editor context is the advantage.
- **Cognition — Devin / Windsurf**: pushes toward long autonomous runs in a
  hosted environment.
- **GitHub Copilot agent mode**, **Google Jules**, **OpenAI Codex**: the
  platform incumbents, with distribution as the edge.
- **Sourcegraph Amp**: code-intelligence heritage, strong on large repos.
- **Aider**: open source, small, an excellent read if you want the loop with no
  ceremony.
- **Replit Agent**: build-and-deploy for people who aren't professional
  developers — a different user, same architecture.

## 8. Signals to look for when evaluating one

- **What's the verification loop?** If it writes code but never runs anything,
  it's an autocomplete with ambitions.
- **How does it handle a 2-million-token repo?** The answer reveals their whole
  context strategy — and "we embed everything" is a weaker answer than it sounds.
- **What happens at hour two?** Compaction quality is the difference between an
  impressive demo and a useful tool.
- **How many tools does it expose?** A long list often signals distrust of the
  model and a harness fighting itself.
- **What does the permission model look like?** Ungated `bash` on your laptop is
  a decision someone should have made deliberately.
- **What do they eval on, beyond SWE-bench?** Public benchmarks get optimized
  against; ask about their internal set and who curates it.
- **What's the cost per completed task?** Not per token. If they can't answer,
  they aren't tracing (module 08).

## 9. Try it yourself

You are almost certainly reading this in one. Things you can watch happen:

- it runs `grep`/`glob` before reading files — retrieval as tool use
- it re-reads a file before editing it — enforced state, not politeness
- it asks before commands with side effects — the permission gate
- it summarizes and continues when context fills — compaction
- it spawns subagents for wide searches — context isolation
- it runs your tests and reads the failure — the verification loop closing

Module 02's `example.py` is the same program with the tools removed. That's the
honest summary of this archetype: a ~120-line loop, plus five years of taste in
the tools, the context strategy, and the guardrails.

---

*Part of a [learning repo](../README.md) on how AI agents are built. Notes and code
co-authored with Claude Opus 5 via Claude Code, then run end-to-end against the real API.*

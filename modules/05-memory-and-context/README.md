# 05 — Memory & Context

Module 00 established the uncomfortable truth: the API is stateless. The model
remembers *nothing* between calls — every "conversation" is your code re-sending
the whole history every time. This module is about the engineering that grows
around that fact once conversations get long and products claim to "remember
you." The punchline to internalize:

> **An agent's memory is never in the model. It's always an engineering
> artifact: tokens your code chose to put back into the context window.**

When a product "remembers," somewhere there is a database row, a file, or a
summary being re-injected into a prompt. Always.

## The three timescales

| Timescale | Mechanism | Analogy |
|---|---|---|
| Working memory | the context window itself (~200k tokens) | what's on your desk |
| Session memory | compaction — summarize old turns, keep working | notes you take when the desk overflows |
| Long-term memory | external store (file/DB), injected or retrieved next session | the filing cabinet |

## Why you can't just let history grow

Three separate problems, and they bite in this order:

1. **Cost.** Every turn re-sends everything, so a conversation's *cumulative*
   cost grows roughly quadratically with its length. Tool-heavy agents are
   worse: every file read and search result lives in the history forever.
2. **Context rot.** Long before you hit the window limit, quality degrades —
   models attend less reliably to material buried in the middle of a huge
   context ("lost in the middle"). More context is not free accuracy.
3. **The hard limit.** Eventually the window is simply full and the next
   call errors.

The economics have one big mitigation: **prompt caching**. Providers let you
mark a prefix of the prompt as cacheable; re-reading cached tokens costs ~10%
of normal price. This only works if the prefix is *byte-identical* across calls
— which is why well-built agents treat history as **append-only** (never edit
earlier turns, add to the end) and why compaction is scheduled carefully: every
compaction rewrites the prefix and invalidates the cache.

## Session memory: trimming vs compaction

**Trimming** (drop the oldest turns) is trivial and terrible: facts from turn 1
(the claim number, the user's constraint) vanish silently. **Compaction** is
what serious products do: when the history gets long, an LLM call summarizes
the old turns — preserving identifiers, decisions, amounts, and open tasks —
and the summary *replaces* them. The conversation continues on top of the
summary plus recent turns.

You have watched this happen: Claude Code's `/compact` (and its auto-compaction)
is exactly this — the sessions building this repo have been compacted several
times, and the "summary of the earlier conversation" that survives is this
technique, live. Compaction is lossy compression; its failure mode is dropping
the one fact you need three turns later. That's why compaction prompts are
specific ("preserve every identifier, amount, decision, open item"), and why
important state gets written to *files* (code, reports, memory) rather than
trusted to the summary.

## Long-term memory: the filing cabinet

Across sessions there is no history at all — session 2 starts from zero. The
patterns, in increasing sophistication:

1. **Memory file** — extract durable facts at session end, write to a file,
   inject the file into the system prompt next session. (Claude Code's memory
   directory and `CLAUDE.md` work this way; this repo's progress notes are
   literally stored like this.)
2. **Structured extraction to a DB** — module 03's forced-tool trick pointed at
   the transcript: "extract facts worth remembering" → validated records.
3. **Memory as RAG** — when memories outgrow the prompt, embed them and
   retrieve only the relevant ones per query (module 04's machinery pointed at
   the agent's own past). This is roughly how ChatGPT-style memory scales.
4. **"Memory" that's actually the CRM** — in support products, "the agent knows
   your order history" is usually a `look_up_customer` tool call, not memory at
   all. Often the right answer: authoritative data should live in systems of
   record, not in accumulated prompt text.

The design question for any of these: *what* is worth remembering (stable
preferences and identities — yes; transient details — no), and who curates it.
Bad memory compounds: one wrong saved fact pollutes every future session.

## What to look for in products

When a company demos "our agent learns about your business over time," the
architectural questions are: where do memories live (file? DB? embeddings?),
what triggers a write, how do wrong memories get corrected, and does recall
degrade as memories accumulate? "It remembers" is a database feature wearing
an AI costume — which is not an insult; the costume is the usable interface.

## Vocabulary

| Term | Meaning |
|---|---|
| context window | max tokens per call — the model's entire working memory |
| compaction | summarizing older history to reclaim window space mid-session |
| prompt caching | provider discount (~90%) for re-sent byte-identical prefixes |
| append-only | never rewriting earlier context — the discipline caching demands |
| context rot / lost-in-the-middle | quality degradation on facts buried in long contexts |
| memory injection | putting stored facts into the system prompt at session start |
| episodic vs semantic memory | "what happened" (transcripts) vs "what's true" (extracted facts) |

## Run it

```bash
uv run modules/05-memory-and-context/example.py
```

Three demos: watching the token bill grow turn by turn; a long claims
conversation continued after trimming (fails) vs after compaction (works),
with real token counts; and "the agent remembered me" across two fresh
sessions via an extracted `memory.json`.

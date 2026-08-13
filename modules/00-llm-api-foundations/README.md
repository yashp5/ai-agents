# 00 — LLM API Foundations

Before agents make sense, you need to be precise about what **one LLM call** actually is.
Every agent product — no matter how sophisticated — bottoms out in repeated calls to an
API that looks like this.

## What one call is

You send an HTTP POST with:

- **`model`** — which model to run (`claude-opus-5` here)
- **`messages`** — a list of `{role, content}` turns: `user` and `assistant`, alternating
- **`system`** — instructions that frame the whole conversation (the "persona + rules" slot)
- **`max_tokens`** — a hard cap on how much the model may generate

You get back a response with `content` (what the model said), `stop_reason` (why it
stopped), and `usage` (tokens in / tokens out — this is what you're billed on).

That's it. Everything else in this repo is scaffolding around this call.

## The five ideas that matter

### 1. The API is stateless
The model remembers **nothing** between calls. "Conversation memory" is an illusion your
code creates by re-sending the entire history every time. This is why context management
(module 05) is a whole discipline: as conversations grow, you're re-sending — and paying
for — more and more tokens per call.

### 2. Everything is tokens
Text is chopped into tokens (~3–4 characters of English each). You pay per token, in and
out. The **context window** (1M tokens for current Claude models) is the hard ceiling on
how much the model can "see" in one call: system prompt + full history + its own answer,
all together. Agent engineering is substantially *token economics* engineering.

### 3. The system prompt is where products live
Two companies calling the same API with the same user message produce wildly different
products because of what's in `system`: persona, rules, domain knowledge, output format,
tool policies. A big fraction of "our proprietary AI" is a very good system prompt. (Try
`ANTHROPIC_LOG=debug` sometime, or look at leaked system prompts of major products —
they're thousands of words.)

### 4. `stop_reason` tells you why generation ended
- `end_turn` — model finished naturally
- `max_tokens` — hit your cap, output is truncated (a bug in your budget, usually)
- `tool_use` — model wants to call a tool ← *this one powers all of module 01+*
- `refusal` — declined for safety reasons

Production code always branches on this. Ignoring it is how you ship truncated answers.

### 5. Streaming is a UX requirement, not an optimization
A full response can take many seconds to minutes. Every chat product you've used streams
tokens as they're generated — that's Server-Sent Events under the hood. For agents,
streaming also prevents HTTP timeouts on long outputs.

## Where you see this in real products

Plenty of "AI features" are exactly one LLM call with a good system prompt — summarize
this ticket, classify this email, draft this reply. Companies often start there, and only
graduate to agents (loops + tools) when a single call can't do the job. When evaluating an
"AI company," a useful first question is: *is this one call, a fixed pipeline of calls, or
a genuine loop?* Cost, latency, and failure modes differ enormously between the three.

## Run it

```bash
uv run modules/00-llm-api-foundations/example.py
```

The example makes three calls: (1) a basic call, printing the raw response structure,
(2) the same question with a system prompt that changes the product, (3) a multi-turn
conversation showing that *you* carry the state, with streaming.

---

*Part of a [learning repo](../../README.md) on how AI agents are built. Notes and code
co-authored with Claude Opus 5 via Claude Code, then run end-to-end against the real API.*

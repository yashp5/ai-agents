# 01 — Tool Use (Function Calling)

This is **the** core agent primitive. Everything that separates an "agent" from a chatbot
is built on this one mechanism.

## The problem it solves

An LLM can only generate text. It can't check your database, send an email, run code, or
look anything up. Tool use is the bridge: a protocol that lets the model *ask your code*
to do things.

## The crucial insight: the model never executes anything

This is the part people get wrong. The flow is:

```
1. You send:    messages + a list of TOOL DEFINITIONS (name, description, JSON schema)
2. Model says:  "I want to call get_weather with {"city": "Paris"}"
                (stop_reason: "tool_use" — generation PAUSES here)
3. YOUR CODE:   actually runs get_weather("Paris")  ← the model is not involved
4. You send:    the whole history + a tool_result block with the output
5. Model says:  "It's 18°C in Paris right now."      (stop_reason: "end_turn")
```

The model only ever emits a *structured request* — a `tool_use` content block with a name
and JSON arguments. Your code is the hands; the model is the brain. This has two big
consequences:

- **Security/control lives in your code.** You can validate arguments, ask a human for
  approval, log everything, or refuse — before anything happens. This is where "human in
  the loop" is physically implemented (module 08).
- **A "tool" is anything you can wrap in a function.** Database query, API call, browser
  click, bank transfer, code execution. When a company says their agent "processes
  payments" or "files patents," they mean: they wrote tools for those actions and let the
  model decide when to call them.

## Tool definitions are prompts

The model decides *when* and *how* to call a tool purely from the `name`, `description`,
and parameter schema you provide. A vague description = wrong tool calls. Real companies
spend serious effort on tool descriptions — they are prompt engineering, and often the
highest-leverage kind. A good description says what the tool does **and when to use it**.

## Vocabulary you'll see in the wild

| Term | Meaning |
|------|---------|
| Function calling / tool calling | This mechanism (OpenAI popularized "function calling") |
| Tool schema | The JSON Schema describing a tool's parameters |
| `tool_choice` | Forcing the model to use a tool (`any`), a specific one, or none |
| Parallel tool calls | Model requests several tools in one turn; you run them all, return all results together |
| Client-side vs server-side tools | Who executes: your code, or the provider's infra (e.g. Anthropic's built-in web search runs server-side) |

## What's still missing

In this module we do **one** round-trip by hand. But real tasks need many: look something
up, act on it, check the result, act again... That's just this round-trip in a `while`
loop — and that loop *is* the agent. Next module.

## Run it

```bash
uv run modules/01-tool-use/example.py
```

The example defines two fake "company" tools (order lookup + refund issuing), prints the
raw `tool_use` block the model emits so you can see the wire format, executes the tools in
Python, and feeds results back. Watch how the model chains a lookup before deciding on the
refund — with no loop code yet, just manual steps.

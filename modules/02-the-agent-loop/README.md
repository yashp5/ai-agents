# 02 — The Agent Loop

The demystifying module. After this, "AI agent" stops being magic.

## The whole secret

```python
while True:
    response = llm(messages, tools)
    if response.stop_reason != "tool_use":
        break                          # model says it's done
    results = run_tools(response)      # your code executes the requests
    messages += [response, results]    # append both to history, go again
```

**That's an agent.** Claude Code, Cursor, Devin, every "autonomous AI employee" — their
core is this loop. The model decides, your code executes, results feed back in, repeat
until the model stops asking for tools. Nobody scripted the sequence of steps; the model
*plans implicitly* by choosing which tool to call next based on everything it's seen so far.

## Why such a dumb loop produces smart behavior

Each iteration, the model re-reads the **entire history** — the task, every tool call it
made, every result it got — and picks the single next action. Errors come back as tool
results too, so the model sees its own failures and corrects course. Planning, retrying,
and "reasoning" all emerge from *re-deciding with more information each time*, not from
any explicit planning code.

## Where products actually differ

If everyone runs the same loop, what makes Claude Code different from a weekend project?
The stuff *around* the loop — which is the rest of this repo:

| Differentiator | Module |
|---|---|
| **Tool design** — the right tools, with sharp descriptions and safe implementations | 01 |
| **The system prompt** — how the agent approaches tasks, when to stop, how to verify | 00 |
| **Context management** — what to do when history outgrows the window | 05 |
| **Domain grounding** — search/retrieval so tools see the right data | 04 |
| **Guardrails & limits** — max iterations, spend caps, human approval on risky actions | 08 |
| **Verification** — does the agent check its own work (run tests, re-read output)? | 08 |

## Workflows vs agents — the vocabulary that matters

- **Workflow**: *your code* decides the sequence (call A, then B, then C, maybe branch).
  Predictable, cheap, easy to test. Most "AI automation" in production is this.
- **Agent**: *the model* decides the sequence via the loop. Flexible, handles the
  unexpected, but costlier and harder to test.

Companies usually use workflows for the predictable 80% and reach for a real agent loop
only where open-ended judgment is needed. When a startup says "agentic," your first
question: *who decides the next step — their code or the model?* (More in module 06.)

## Production guardrails you'd add (and we include two)

Real loops are never unbounded: an iteration cap (ours: 15), a token/cost budget, timeouts,
and confirmation gates on destructive tools. The loop is 10 lines; making it safe to run
unattended is the job.

## Run it

```bash
uv run modules/02-the-agent-loop/example.py
```

An ~120-line file agent with four tools (`list_files`, `read_file`, `write_file`,
`calculate`). It gets one task — *analyze the expense files in `workspace/` and write a
summary report* — and figures out the steps itself. Watch the trace: nobody told it to
list first, read second, compute third, write last.

Run it twice and the trace may differ slightly — that's the model planning, not a script.

---

*Part of a [learning repo](../../README.md) on how AI agents are built. Notes and code
co-authored with Claude Opus 5 via Claude Code, then run end-to-end against the real API.*

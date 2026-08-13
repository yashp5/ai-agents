# 03 — Structured Output

Modules 00–02 got the model to *say* things and *do* things. This module is about
getting it to produce **data**: JSON your software can parse, validate, store,
and act on without a human reading it.

This is arguably the most commercially important module in the repo. When a
company says "AI agents for insurance / patents / invoices / contracts," the
beating heart of the product is almost always *unstructured document in →
validated JSON out*. Everything else (the UI, the workflow engine, the human
review queue) is built around that transformation.

## The problem

LLMs speak prose. Software speaks JSON. Prose doesn't compose: you can't put
"a pipe burst and the plumber quoted around $2.4k" into a database column,
total it in a report, or branch on it in code.

And "just ask for JSON" is not a solution, because the failure modes are silent
and statistical:

- the JSON arrives wrapped in markdown fences or a "Sure! Here's the JSON:" preamble
- field names drift between runs (`amount` vs `estimated_amount` vs `cost_usd`)
- fields go missing, or extra ones appear
- it works in 97% of runs — which means it *fails* on 3% of your customers

A parser that works 97% of the time is a broken parser.

## The three levels of rigor

| Level | Technique | Guarantees |
|---|---|---|
| 1. Ask nicely | "Respond with JSON" in the prompt | none — parse and pray |
| 2. Constrain | force a tool call whose `input_schema` **is** your output schema | valid JSON, right field names/types |
| 3. Validate + repair | check the values (Pydantic + business rules), send failures back for a retry | data you can actually trust |

Level 2 is the classic trick, and it's worth internalizing: **you've already
been using structured output since module 01.** Every tool call the model made
was the model filling in a JSON schema. Structured *extraction* just points that
same machinery at a document — you define a "tool" like `record_claim` that no
code ever really implements, force the model to call it (`tool_choice`), and
read the arguments. The tool call *is* the output.

## Schema-valid ≠ correct

The trap at level 2: the API guarantees the JSON matches your schema's *shape*.
It does not guarantee the *values* are right. `"incident_date": "2026-13-45"`
can be schema-valid. So production pipelines add layers:

1. **Schema** — right shape (the API enforces this at level 2)
2. **Semantic validation** — dates parse, enums make sense, totals add up (Pydantic)
3. **Business rules** — policy number exists in *your* DB, amount under auto-approve limit
4. **Confidence routing** — model unsure, or a rule fails? → human review queue

That last step is why "AI agents for insurance" companies all demo a review UI:
the product isn't "no humans," it's "humans only see the hard 5%."

The repair loop (level 3) closes the circle: when validation fails, you don't
crash — you send the error message back to the model as a failed tool result and
let it correct itself. Same self-healing move as module 02's error handling.

## Vocabulary

| Term | Meaning |
|---|---|
| JSON Schema | the standard for describing JSON shape (`type`, `properties`, `required`, `enum`, …) |
| `tool_choice` | API param that *forces* the model to call a specific tool — the constraint mechanism |
| constrained decoding | sampling only tokens that keep the output schema-valid (how providers enforce shape) |
| Pydantic | Python library for declaring + validating data models; the de-facto validation layer |
| repair loop | feed the validation error back to the model, get a corrected attempt |
| extraction | the doc-AI industry term for document → structured record |

## Run it

```bash
uv run modules/03-structured-output/example.py
```

The example extracts a structured claim record from a messy insurance email at
all three levels of rigor, printing what each level does and doesn't guarantee.

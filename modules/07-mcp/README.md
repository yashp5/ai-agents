# 07 — MCP (Model Context Protocol)

Module 01 gave the model tools by hardcoding them: a Python dict of JSON Schema,
a dict of functions, both living inside the agent. That works — and it means
every agent must ship its own integration with every system. MCP is the
industry's answer to that combinatorial mess.

> **MCP is a standard protocol for exposing tools and data to LLM applications.
> The agent stops containing integrations and starts discovering them.**

Anthropic open-sourced it in late 2024; OpenAI, Google, Microsoft and the major
IDEs adopted it through 2025. It is now the closest thing this field has to a
universal port.

## The problem: M×N becomes M+N

Say there are M agent products (Claude Code, Cursor, your claims agent, an IDE)
and N systems worth connecting (GitHub, Postgres, Slack, your claims DB).
Without a standard, someone writes **M×N** integrations — every product
re-implements every connector. With a standard, each system ships **one** server
and each product ships **one** client: **M+N**.

That's the entire pitch, and it's the same one USB, ODBC, and LSP made before
it. (LSP is the closest analogy: before it, every editor implemented every
language's tooling; after it, each language ships one server.)

## The architecture

```
   ┌──────────────── HOST (the app: Claude Desktop, an IDE, example.py) ─────┐
   │  the LLM + the agent loop + user consent                                │
   │      │                    │                        │                    │
   │   client               client                   client   (one per server)│
   └──────┼────────────────────┼────────────────────────┼────────────────────┘
          │ JSON-RPC           │                        │
     ┌────▼─────┐        ┌─────▼──────┐          ┌──────▼──────┐
     │ claims   │        │  GitHub    │          │  Postgres   │
     │ server   │        │  server    │          │  server     │
     └────┬─────┘        └─────┬──────┘          └──────┬──────┘
        claims DB          the GitHub API          your database
```

Three roles: the **host** owns the model, the loop, and the user's trust; a
**client** is the host's connection to one server; a **server** wraps one system
and owns its data and rules. Two standard transports: **stdio** (the server is a
local subprocess — what `example.py` uses) and **HTTP** (a server running
somewhere, for hosted/remote integrations).

The protocol itself is unglamorous: JSON-RPC 2.0, one message per line, with a
handful of methods — `initialize`, `tools/list`, `tools/call`, `resources/list`,
`resources/read`. `server.py` implements them in ~60 lines of logic. Nothing in
this module is mysterious once you see the wire traffic; that's why the example
prints it.

## Three primitives, and who controls each

| Primitive | Controlled by | Example |
|---|---|---|
| **Tools** | the **model** decides when to call | `open_claim`, `run_query` |
| **Resources** | the **application/user** attaches | a file, a handbook, a schema (`@`-mentioning a doc) |
| **Prompts** | the **user** invokes | a saved workflow, a slash command |

The distinction that trips people up: tools are verbs the model chooses;
resources are nouns the client pulls in. Both end up as tokens in the context —
the difference is *who decides*.

## Why this matters beyond convenience

**Discovery at runtime is a different capability, not just tidier code.**
`example.py` contains no insurance logic whatsoever; it learns about
`look_up_policy` when it connects. Add a tool to the server and every client
gains it with no client change — which is how an enterprise ships "our systems,
usable by whatever agent the customer already has."

**The server is a security boundary.** Demo 4 calls `open_claim` on a lapsed
policy directly, bypassing the model entirely — the server refuses. Rules
enforced where the data lives cannot be prompted away. This is module 02's
`_safe_path()` lesson, now across a process boundary, and it's the strongest
argument for exposing systems through a server rather than handing an agent raw
credentials.

**It reframes what a "platform" is.** A company can ship an MCP server as a
product surface — the modern equivalent of publishing an API, but consumable by
agents without anyone writing client code.

## The security caveats (real, and easy to underrate)

- **Tool results are untrusted input.** A malicious document, issue comment, or
  database row can carry instructions the model may follow — indirect prompt
  injection. Never treat tool output as trusted (module 10 goes deeper).
- **Tool poisoning.** Descriptions are prompts; a hostile server can describe a
  tool in ways that manipulate the model. Install servers as you would install
  dependencies — with an eye on the supplier.
- **Confused deputy / over-broad scope.** A server with your full DB credentials
  will happily do anything asked. Scope credentials to what the server needs.
- **Consent belongs to the host.** Approval prompts before consequential calls
  are the host's job — one reason clients ask before running unfamiliar tools.

## Practical note

Real servers use the official SDKs (`pip install mcp`, or the TypeScript one),
which handle the handshake, schema generation from type hints, transports, and
lifecycle. This module implements the protocol by hand for exactly one reason:
so you know there is no magic underneath the SDK. Also worth knowing: hundreds
of servers already exist (filesystem, GitHub, Postgres, Slack, Sentry…), so
"integrate with X" is often "point at an existing server."

## Vocabulary

| Term | Meaning |
|---|---|
| host / client / server | the app; its per-server connection; the system wrapper |
| JSON-RPC 2.0 | the request/response format MCP speaks |
| stdio / HTTP transport | local subprocess vs remote server |
| `tools/list` | runtime discovery — the reason MCP exists |
| resource | data the client attaches, addressed by URI |
| prompt (MCP) | a user-invoked saved workflow the server exposes |
| indirect prompt injection | attack instructions arriving inside tool results |

## Run it

```bash
uv run modules/07-mcp/example.py
```

`server.py` is a real MCP server for HomeShield's claims systems; `example.py`
is a from-scratch client that handshakes, discovers tools, reads a resource,
runs module 02's agent loop over the discovered tools (opening a claim for the
active policy, declining the lapsed one), and finally proves the server refuses
the illegal call even when the model is bypassed entirely.

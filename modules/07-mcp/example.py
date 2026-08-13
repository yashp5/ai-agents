"""Module 07 — MCP (Model Context Protocol).

A complete MCP client, from scratch, talking to the server next door:
  1. Handshake + discovery — the raw JSON-RPC on the wire
  2. Resources — context that is data, not a tool call
  3. The agent loop from module 02, with tools it learned about at RUNTIME

The punchline: this file contains ZERO insurance knowledge. Point it at a
different server and it becomes a different product.

Run from the repo root:  uv run modules/07-mcp/example.py
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from anthropic import Anthropic
from anthropic.types import MessageParam, ToolParam, ToolResultBlockParam
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-5"
SERVER = Path(__file__).parent / "server.py"
client = Anthropic()


class MCPClient:
    """~30 lines. Launch the server, speak JSON-RPC over its stdin/stdout."""

    def __init__(self, server_path: Path, verbose: bool = False):
        self.verbose = verbose
        self._id = 0
        # The transport: a subprocess. (The other standard transport is HTTP,
        # for servers that live on a machine somewhere instead of locally.)
        self.proc = subprocess.Popen(
            [sys.executable, str(server_path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
        )

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        message = {"jsonrpc": "2.0", "id": self._id, "method": method,
                   "params": params or {}}
        if self.verbose:
            print(f"  --> {json.dumps(message)}")
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        response = json.loads(self.proc.stdout.readline())
        if self.verbose:
            wire = json.dumps(response)
            print(f"  <-- {wire[:300]}{'…' if len(wire) > 300 else ''}\n")
        return response["result"]

    def notify(self, method: str) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def initialize(self) -> dict:
        info = self.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "module-07-example", "version": "0.1.0"},
        })
        self.notify("notifications/initialized")
        return info

    def close(self) -> None:
        assert self.proc.stdin
        self.proc.stdin.close()
        self.proc.wait(timeout=5)


def to_anthropic_tools(mcp_tools: list[dict]) -> list[ToolParam]:
    """The adapter — MCP's inputSchema is the Anthropic input_schema, renamed.
    Every MCP-supporting product has this ~4-line function somewhere."""
    return [
        cast(ToolParam, {"name": t["name"], "description": t["description"],
                         "input_schema": t["inputSchema"]})
        for t in mcp_tools
    ]


def get_text(response) -> str:
    text = "".join(b.text for b in response.content if b.type == "text")
    return text or f"(no text — stop_reason={response.stop_reason!r})"


# ---------------------------------------------------------------------------
# DEMO 1 + 2: discovery and resources
# ---------------------------------------------------------------------------


def demo_1_discovery(mcp: MCPClient) -> list[dict]:
    print("=" * 70)
    print("DEMO 1: handshake + discovery — the actual bytes on the wire")
    print("=" * 70 + "\n")

    info = mcp.initialize()
    print(f"Connected to: {info['serverInfo']['name']} "
          f"(protocol {info['protocolVersion']})\n")

    tools = mcp.request("tools/list")["tools"]
    print(f"The server offered {len(tools)} tools. We hardcoded NONE of them:")
    for t in tools:
        print(f"  - {t['name']}: {t['description'][:60]}…")
    print("\nThis is the whole point: tools arrive at runtime. Add a tool to the\n"
          "server and every MCP client — Claude Desktop, an IDE, this file —\n"
          "gains it with no code change.")
    return tools


def demo_2_resources(mcp: MCPClient) -> None:
    print("\n" + "=" * 70)
    print("DEMO 2: resources — context as DATA, not as a tool call")
    print("=" * 70 + "\n")

    resources = mcp.request("resources/list")["resources"]
    for r in resources:
        print(f"  {r['uri']}  ({r['name']})")
    body = mcp.request("resources/read", {"uri": resources[0]["uri"]})["contents"][0]
    print(f"\nRead {resources[0]['uri']}:\n{body['text']}")
    print("Tools are verbs the model chooses to invoke; resources are nouns the\n"
          "CLIENT can pull in (often user-selected, like @-mentioning a file).")


# ---------------------------------------------------------------------------
# DEMO 3: module 02's loop, unchanged in shape — but domain-blind
# ---------------------------------------------------------------------------

TASK = (
    "Two customers want to file water-damage claims: Raj Mehta on policy "
    "HP-40122-B for $1,800, and Ana Duarte on policy HP-88913-C for $900. "
    "Open whatever claims you can, then tell me exactly what happened with each."
)


def demo_3_agent_loop(mcp: MCPClient, mcp_tools: list[dict]) -> None:
    print("\n" + "=" * 70)
    print("DEMO 3: the agent loop — same as module 02, tools from the server")
    print("=" * 70)
    print(f"\nTASK: {TASK}\n")

    tools = to_anthropic_tools(mcp_tools)
    messages: list[MessageParam] = [{"role": "user", "content": TASK}]

    for iteration in range(1, 10):
        response = client.messages.create(
            model=MODEL, max_tokens=4000, tools=tools,
            system="You are a claims intake agent. Use the available tools.",
            messages=messages,
        )
        if response.stop_reason != "tool_use":
            print(f"\nagent: {get_text(response)}")
            print(f"\n--- done after {iteration} rounds ---")
            return

        messages.append({"role": "assistant", "content": response.content})
        results: list[ToolResultBlockParam] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            args = cast(dict[str, Any], block.input)
            # Every tool call is a JSON-RPC round trip to the other process.
            out = mcp.request("tools/call", {"name": block.name, "arguments": args})
            text = out["content"][0]["text"]
            flag = "  <- SERVER REFUSED" if out.get("isError") else ""
            print(f"[{iteration}] {block.name}({json.dumps(args)})")
            print(f"      -> {text[:90]}{'…' if len(text) > 90 else ''}{flag}")
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": text, "is_error": bool(out.get("isError"))})
        messages.append({"role": "user", "content": results})


def demo_4_server_side_guardrail(mcp: MCPClient) -> None:
    """The model above was sensible and never tried the lapsed policy. Good —
    but safety must not depend on that. Here we bypass the model entirely and
    call the tool the way a jailbroken or buggy agent would."""
    print("\n" + "=" * 70)
    print("DEMO 4: the guardrail lives in the SERVER, not in the prompt")
    print("=" * 70 + "\n")

    out = mcp.request("tools/call", {
        "name": "open_claim",
        "arguments": {"policy_number": "HP-88913-C", "peril": "water_damage",
                      "amount_usd": 900},
    })
    print(f"  direct tools/call on the LAPSED policy -> isError={out.get('isError')}")
    print(f"  {out['content'][0]['text']}")
    print("\nNo prompt could have talked past that: the rule is enforced where\n"
          "the data lives. Same lesson as module 02's _safe_path(), now across\n"
          "a process boundary — which is exactly why teams like shipping their\n"
          "systems to agents as an MCP server rather than as loose credentials.")


if __name__ == "__main__":
    mcp = MCPClient(SERVER, verbose=True)
    try:
        mcp_tools = demo_1_discovery(mcp)
        demo_2_resources(mcp)
        mcp.verbose = False  # wire traffic shown; now just the agent's story
        demo_3_agent_loop(mcp, mcp_tools)
        demo_4_server_side_guardrail(mcp)
    finally:
        mcp.close()
    print(
        "\nNotice what this file never contained: policy numbers, deductibles,\n"
        "any insurance logic. The server owns the domain, the data, and the\n"
        "rules; the client owns the model and the loop. That separation is\n"
        "what turns an M×N integration problem into M+N."
    )

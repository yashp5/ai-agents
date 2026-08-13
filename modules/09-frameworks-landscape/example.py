"""Module 09 — Frameworks.

The same HomeShield task, three ways, so you can see exactly what a framework
adds and what it hides:

  1. RAW            — module 02's loop, ~35 lines, nothing hidden
  2. create_agent   — the same loop as a 3-line call
  3. StateGraph     — where a framework actually earns its keep: an explicit
                      graph, conditional routing, a checkpointer, and a
                      human-approval interrupt you can resume days later

Modules 00–08 used the raw API on purpose. Now that you've hand-built the loop,
the durable journal, and the review gate, the frameworks stop looking like magic
and start looking like *someone else's version of the code you already wrote*.

Run from the repo root:  uv run modules/09-frameworks-landscape/example.py
"""

import inspect
import json
from typing import Any, TypedDict, cast

from anthropic import Anthropic
from anthropic.types import MessageParam, ToolParam, ToolResultBlockParam
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

load_dotenv()

MODEL = "claude-opus-5"
TASK = ("Raj Mehta had $2,700 of water damage on policy HP-40122-B. "
        "Look up the policy and tell me what HomeShield would pay him.")

POLICIES = {
    "HP-40122-B": {"holder": "Raj Mehta", "status": "active",
                   "deductible_usd": 500, "coverage_cap_usd": 5000},
}


# The domain logic — identical in all three versions. This is the part that is
# actually your product; everything else in this file is plumbing.
def _look_up_policy(policy_number: str) -> str:
    policy = POLICIES.get(policy_number.upper())
    return json.dumps(policy) if policy else f"No policy {policy_number}"


def _estimate_payout(damage_usd: float, deductible_usd: float) -> str:
    return json.dumps({"payout_usd": max(0.0, damage_usd - deductible_usd)})


# ---------------------------------------------------------------------------
# 1. RAW — module 02, condensed. Every byte is yours.
# ---------------------------------------------------------------------------

RAW_TOOLS: list[ToolParam] = [
    {
        "name": "look_up_policy",
        "description": "Look up a HomeShield policy by number.",
        "input_schema": {"type": "object",
                         "properties": {"policy_number": {"type": "string"}},
                         "required": ["policy_number"]},
    },
    {
        "name": "estimate_payout",
        "description": "Compute the payout after the deductible.",
        "input_schema": {"type": "object",
                         "properties": {"damage_usd": {"type": "number"},
                                        "deductible_usd": {"type": "number"}},
                         "required": ["damage_usd", "deductible_usd"]},
    },
]
DISPATCH = {"look_up_policy": _look_up_policy, "estimate_payout": _estimate_payout}
client = Anthropic()


def part_1_raw() -> None:
    messages: list[MessageParam] = [{"role": "user", "content": TASK}]
    while True:
        response = client.messages.create(model=MODEL, max_tokens=2000,
                                          tools=RAW_TOOLS, messages=messages)
        if response.stop_reason != "tool_use":
            text = "".join(b.text for b in response.content if b.type == "text")
            print(f"\n  agent: {text.strip()}")
            return
        messages.append({"role": "assistant", "content": response.content})
        results: list[ToolResultBlockParam] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            args = cast(dict[str, Any], block.input)
            print(f"  [tool] {block.name}({json.dumps(args)})")
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": DISPATCH[block.name](**args)})
        messages.append({"role": "user", "content": results})


# ---------------------------------------------------------------------------
# 2. create_react_agent — the identical loop, as somebody else's abstraction.
# ---------------------------------------------------------------------------


@tool
def look_up_policy(policy_number: str) -> str:
    """Look up a HomeShield policy by number."""
    return _look_up_policy(policy_number)


@tool
def estimate_payout(damage_usd: float, deductible_usd: float) -> str:
    """Compute the payout after the deductible."""
    return _estimate_payout(damage_usd, deductible_usd)


def part_2_prebuilt() -> None:
    # Docstrings became descriptions; type hints became the JSON Schema. That
    # is genuinely the nicest thing frameworks do for you.
    #
    # Churn, live: one major version ago this was
    #     from langgraph.prebuilt import create_react_agent
    #     create_react_agent(model, tools, prompt=...)
    # Same function, new module, new kwarg name. Import the old path today and
    # you get a deprecation warning that says "removed in V2.0".
    agent = create_agent(
        ChatAnthropic(model=MODEL, max_tokens=2000),
        tools=[look_up_policy, estimate_payout],
        system_prompt="You are a HomeShield claims adjuster.",
    )
    result = agent.invoke({"messages": [{"role": "user", "content": TASK}]})

    for message in result["messages"]:
        for call in getattr(message, "tool_calls", []) or []:
            print(f"  [tool] {call['name']}({json.dumps(call['args'])})")
    print(f"\n  agent: {_text(result['messages'][-1]).strip()}")


def _text(message: Any) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


# ---------------------------------------------------------------------------
# 3. StateGraph — the version worth importing a dependency for.
#
# Note what this is NOT: it is not an agent loop. It's a workflow (module 06)
# with a typed state, conditional routing, a checkpointer, and a human gate.
# The LLM is one node among several.
# ---------------------------------------------------------------------------

CLAIM_EMAIL = ("Hi — pipe burst behind the washing machine on policy hp-40122-b, "
               "plumber quoted $2.4k and we lost a $300 rug. — Raj Mehta")


class Extracted(BaseModel):
    policy_number: str = Field(description="Normalized, e.g. 'HP-40122-B'")
    damage_usd: float = Field(description="Total damage in USD")


class ClaimState(TypedDict):
    # The graph's typed state. Nodes return partial updates and LangGraph
    # merges them in — so the initial input is a partial dict too (see below).
    email: str
    policy_number: str
    damage_usd: float
    payout_usd: float
    decision: str
    outcome: str


def extract_node(state: ClaimState) -> dict:
    llm = ChatAnthropic(model=MODEL, max_tokens=2000)
    out = cast(Extracted, llm.with_structured_output(Extracted).invoke(
        f"Extract the claim:\n\n{state['email']}"))
    print(f"  [extract] {out.policy_number}  ${out.damage_usd:,.0f}")
    return {"policy_number": out.policy_number, "damage_usd": out.damage_usd}


def price_node(state: ClaimState) -> dict:
    """No LLM here. Money math is deterministic code — module 06's lesson."""
    policy = POLICIES[state["policy_number"].upper()]
    payout = min(max(0.0, state["damage_usd"] - policy["deductible_usd"]),
                 policy["coverage_cap_usd"])
    print(f"  [price  ] payout ${payout:,.0f} after ${policy['deductible_usd']} deductible")
    return {"payout_usd": payout}


def needs_approval(state: ClaimState) -> str:
    """Module 08's threshold, expressed as an edge."""
    return "approve" if state["payout_usd"] >= 1000 else "pay"


def approve_node(state: ClaimState) -> dict:
    # interrupt() stops the graph mid-run and persists everything. The process
    # can exit here; a human answers tomorrow. This is module 06's journal and
    # module 08's review queue, handed to you.
    decision = interrupt({"question": "Approve this payout?",
                          "payout_usd": state["payout_usd"],
                          "policy_number": state["policy_number"]})
    return {"decision": decision}


def pay_node(state: ClaimState) -> dict:
    if state.get("decision", "approved") != "approved":
        return {"outcome": "declined by reviewer"}
    return {"outcome": f"ACH ${state['payout_usd']:,.0f} to "
                       f"{POLICIES[state['policy_number']]['holder']}"}


def build_graph():
    g = StateGraph(ClaimState)
    g.add_node("extract", extract_node)
    g.add_node("price", price_node)
    g.add_node("approve", approve_node)
    g.add_node("pay", pay_node)
    g.add_edge(START, "extract")
    g.add_edge("extract", "price")
    g.add_conditional_edges("price", needs_approval, {"approve": "approve", "pay": "pay"})
    g.add_edge("approve", "pay")
    g.add_edge("pay", END)
    # Swap InMemorySaver for the Postgres saver and the same graph survives a
    # deploy. That swap is the actual reason teams adopt this.
    return g.compile(checkpointer=InMemorySaver())


def part_3_stategraph() -> None:
    graph = build_graph()
    config = cast(Any, {"configurable": {"thread_id": "claim-2214"}})

    for chunk in graph.stream(cast(ClaimState, {"email": CLAIM_EMAIL}), config):
        if "__interrupt__" in chunk:
            payload = chunk["__interrupt__"][0].value
            print(f"\n  PAUSED at the human gate: {json.dumps(payload)}")

    snapshot = graph.get_state(config)
    print(f"  graph.get_state() -> next={snapshot.next}, "
          f"state={ {k: v for k, v in snapshot.values.items() if k != 'email'} }")
    print("  The run is now durable state, not a Python stack frame. The process\n"
          "  could exit here and resume next week from another machine.\n")

    print("  …reviewer approves…")
    for chunk in graph.stream(Command(resume="approved"), config):
        for update in chunk.values():
            if update and "outcome" in update:
                print(f"  [pay    ] {update['outcome']}")


# ---------------------------------------------------------------------------


def part_4_the_tradeoff() -> None:
    raw = len(inspect.getsourcelines(part_1_raw)[0]) + len(RAW_TOOLS) * 8
    prebuilt = len(inspect.getsourcelines(part_2_prebuilt)[0])
    print(f"  Loop implementation:  raw ≈{raw} lines   framework ≈{prebuilt} lines")
    print("""
  What the framework gave you
    - schemas from type hints + docstrings; no hand-written JSON Schema
    - persistence, interrupts and resume that you'd otherwise build (module 06)
    - streaming, tracing hooks, retries, and provider swapping for free
    - a shared vocabulary — new hires already know what a "node" is

  What it cost you
    - the prompt is now THEIRS. Module 08 says a prompt is code you eval and
      version; a framework's built-in prompt is code you didn't write and
      can't see without reading its source.
    - debugging goes through their stack: your bug is 6 frames down in a
      Runnable, and the failure mode you care about is a model behaviour
    - churn: the API you learn today gets renamed in the next major version
    - it flatters you into agentic designs when a for-loop would do

  The split that holds up in practice
    - the agent LOOP is ~40 lines. Owning it is cheap; own it.
    - the WORKFLOW around it — durability, retries, human gates, audit —
      is real infrastructure. Import that, or use Temporal for it.
  """)


if __name__ == "__main__":
    for n, (title, fn) in enumerate([
        ("RAW — the loop you already wrote in module 02", part_1_raw),
        ("create_agent — the same loop, three lines", part_2_prebuilt),
        ("StateGraph — routing, checkpoints, and a human gate", part_3_stategraph),
        ("The trade-off, stated honestly", part_4_the_tradeoff),
    ], start=1):
        print(f"\n{'=' * 74}\nPART {n}: {title}\n{'=' * 74}\n")
        fn()

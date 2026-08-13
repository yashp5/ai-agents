"""Module 01 — Tool Use (Function Calling).

A refunds assistant with two fake "company" tools. We print the raw tool_use
blocks the model emits so you can see the wire format, execute the tools in
plain Python, and feed results back.

Run from the repo root:  uv run modules/01-tool-use/example.py
"""

import json

from anthropic import Anthropic
from anthropic.types import MessageParam, ToolParam, ToolResultBlockParam
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-5"
client = Anthropic()

# ---------------------------------------------------------------------------
# 1. The tools' IMPLEMENTATIONS — plain Python. The model never runs these;
#    it can only *ask* for them by name. (Here they're fakes; in a real
#    company they'd hit the orders DB and the payments API.)
# ---------------------------------------------------------------------------

FAKE_ORDERS_DB = {
    "A-1001": {"item": "Espresso machine", "price_usd": 249.00, "status": "delivered", "days_since_delivery": 12},
    "A-1002": {"item": "Coffee grinder", "price_usd": 89.00, "status": "in_transit", "days_since_delivery": None},
}


def look_up_order(order_id: str) -> str:
    order = FAKE_ORDERS_DB.get(order_id)
    return json.dumps(order) if order else f"No order found with id {order_id!r}"


def issue_refund(order_id: str, reason: str) -> str:
    # In production, THIS is where you'd validate, log, and maybe require
    # human approval — the model can't reach past this function.
    return json.dumps({"refund_id": f"R-{order_id}", "status": "issued", "reason": reason})


PYTHON_FUNCTIONS = {"look_up_order": look_up_order, "issue_refund": issue_refund}

# ---------------------------------------------------------------------------
# 2. The tools' DEFINITIONS — what the model sees. Name + description +
#    JSON Schema. The descriptions are doing real work: they're how the
#    model decides when to call what.
# ---------------------------------------------------------------------------

TOOLS: list[ToolParam] = [
    {
        "name": "look_up_order",
        "description": (
            "Look up an order by its ID. Returns item, price, and delivery status. "
            "Always call this before making any decision about an order."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Order ID, e.g. 'A-1001'"},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "issue_refund",
        "description": (
            "Issue a full refund for an order. Only for orders that were delivered "
            "within the last 30 days. Do not call this without looking the order up first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "reason": {"type": "string", "description": "Short reason for the refund"},
            },
            "required": ["order_id", "reason"],
        },
    },
]

# ---------------------------------------------------------------------------
# 3. The round-trips. Watch stop_reason: "tool_use" means "generation is
#    paused — the model is waiting for YOUR code to act".
# ---------------------------------------------------------------------------


def main() -> None:
    messages: list[MessageParam] = [
        {
            "role": "user",
            "content": "Hi — order A-1001 arrived with a cracked water tank. I'd like a refund.",
        }
    ]
    print(f"USER: {messages[0]['content']}\n")

    round_num = 0
    while True:
        print("CONTEXT: ", messages)
        round_num += 1
        # Generous cap: thinking + text + tool calls all share this budget
        response = client.messages.create(
            model=MODEL, max_tokens=4000, tools=TOOLS, messages=messages
        )

        print(f"--- round trip {round_num}: stop_reason = {response.stop_reason!r} ---")

        # Any text the model wrote alongside its tool calls
        for block in response.content:
            if block.type == "text" and block.text.strip():
                print(f"MODEL (text): {block.text}")

        if response.stop_reason != "tool_use":
            break  # model is done — no more tool requests

        # Append the model's turn (INCLUDING its tool_use blocks) to history.
        # If you drop these, the API rejects the next request.
        messages.append({"role": "assistant", "content": response.content})

        # Execute every tool call and answer each with a tool_result,
        # matched by tool_use_id — all in ONE user message.
        tool_results: list[ToolResultBlockParam] = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"\nMODEL wants a tool call (the raw wire format):")
                print(f"  name : {block.name}")
                print(f"  input: {json.dumps(block.input)}")
                print(f"  id   : {block.id}")

                output = PYTHON_FUNCTIONS[block.name](**block.input)
                print(f"YOUR CODE ran it and got: {output}\n")

                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": output}
                )

        messages.append({"role": "user", "content": tool_results})

    print(
        "\nNotice: the model looked the order up BEFORE refunding (the tool "
        "descriptions told it to), and your Python did all the real work.\n"
        "Also notice we secretly wrote a while-loop around the round-trip — "
        "that loop has a name: it's the agent loop. Module 02 makes it official."
    )


if __name__ == "__main__":
    main()

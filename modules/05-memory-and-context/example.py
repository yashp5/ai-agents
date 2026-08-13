"""Module 05 — Memory & Context.

The API remembers nothing; "memory" is tokens your code re-sends. Three demos:
  1. The growing bill — input tokens climb every turn of a conversation
  2. Session memory — trim (loses facts) vs compact (keeps them), with counts
  3. Long-term memory — facts extracted to memory.json survive a fresh session

Run from the repo root:  uv run modules/05-memory-and-context/example.py
"""

import json
from pathlib import Path
from typing import cast

from anthropic import Anthropic
from anthropic.types import MessageParam, ToolParam
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-5"
MEMORY_FILE = Path(__file__).parent / "memory.json"
client = Anthropic()


def get_text(response) -> str:
    text = "".join(b.text for b in response.content if b.type == "text")
    return text or f"(no text — stop_reason={response.stop_reason!r})"


def count_tokens(messages: list[MessageParam]) -> int:
    """The API counts tokens for us without generating anything (free)."""
    return client.messages.count_tokens(model=MODEL, messages=messages).input_tokens


# ---------------------------------------------------------------------------
# DEMO 1: the bill grows every turn — cumulative cost is roughly quadratic
# ---------------------------------------------------------------------------


def demo_1_growing_bill() -> None:
    print("=" * 70)
    print("DEMO 1: statelessness has a price — watch input tokens climb")
    print("=" * 70)

    history: list[MessageParam] = []
    turns = [
        "I'm comparing homeowners insurance. In ONE sentence: what does a "
        "standard policy cover?",
        "In ONE sentence: what's a deductible?",
        "In ONE sentence: what did I say I was comparing?",  # needs turn 1!
    ]

    print()
    for i, user_text in enumerate(turns, 1):
        history.append({"role": "user", "content": user_text})
        response = client.messages.create(model=MODEL, max_tokens=2500, messages=history)
        history.append({"role": "assistant", "content": get_text(response)})
        print(f"turn {i}: input={response.usage.input_tokens:>4} tokens   "
              f"(the ENTIRE history was re-sent)")
        print(f"        A: {get_text(response)}\n")

    print(
        "Each turn re-sends everything before it, so turn N costs O(N) and the\n"
        "whole conversation costs O(N^2). Tool-heavy agents are worse: every\n"
        "file read stays in history forever. Mitigations: prompt caching\n"
        "(cached prefix tokens cost ~10%) — and, eventually, compaction."
    )


# ---------------------------------------------------------------------------
# DEMO 2: session memory — a long conversation hits the wall. Trim or compact?
# ---------------------------------------------------------------------------

# A claims support session with load-bearing facts in the EARLIEST turns.
LONG_HISTORY: list[MessageParam] = [
    {"role": "user", "content": "Hi, I was told my burst-pipe claim is now open — claim CLM-2214. Who is handling it?"},
    {"role": "assistant", "content": "Your claim CLM-2214 is assigned to adjuster Dana Whitfield, who will contact you within 2 business days."},
    {"role": "user", "content": "Great. I set up ACH on the account ending 7714 for the payout — is that confirmed?"},
    {"role": "assistant", "content": "Confirmed — ACH ending 7714 is on file. Approved payments arrive within 5 business days."},
    {"role": "user", "content": "The plumber can only come Thursday to write the final invoice. Does that delay anything?"},
    {"role": "assistant", "content": "No problem — adjudication simply waits for the written invoice. Thursday keeps you well within your notice window."},
    {"role": "user", "content": "We couldn't use the house for two nights, so we have hotel receipts. Can I claim those?"},
    {"role": "assistant", "content": "Possibly, under loss-of-use coverage. Send the receipts to your adjuster for review."},
    {"role": "user", "content": "I'm a bit worried about mold behind the baseboards."},
    {"role": "assistant", "content": "Since you dried the area within 72 hours, resulting mold remediation is covered up to $2,500. Mention it to the adjuster on your call."},
    {"role": "user", "content": "One more thing: my email changes to raj@newmail.example next month."},
    {"role": "assistant", "content": "Noted — I've flagged the upcoming email change on your file."},
]

# Both facts this question needs live in the FIRST two messages.
QUESTION = "Remind me — what's my claim number, and who's my adjuster?"


def answer(messages: list[MessageParam], label: str) -> None:
    response = client.messages.create(
        model=MODEL, max_tokens=2500,
        system="You are a HomeShield claims support agent. Answer in one sentence.",
        messages=messages,
    )
    print(f"--- {label} ({count_tokens(messages)} tokens sent) ---")
    print(f"{get_text(response)}\n")


def compact(history: list[MessageParam]) -> str:
    """The /compact operation: one LLM call turns old turns into a summary."""
    transcript = "\n".join(
        f"{m['role']}: {m['content']}" for m in history
    )
    response = client.messages.create(
        model=MODEL, max_tokens=2500,
        messages=[{
            "role": "user",
            "content": "Compress this support conversation into a short handoff "
            "note. Preserve EVERY identifier, name, amount, decision, and open "
            "item — a colleague must be able to take over seamlessly.\n\n"
            + transcript,
        }],
    )
    return get_text(response)


def demo_2_trim_vs_compact() -> None:
    print("\n" + "=" * 70)
    print("DEMO 2: the window fills up — trim vs compact")
    print("=" * 70)
    print(f"\nA 12-message session; full history = {count_tokens(LONG_HISTORY)} tokens.")
    print(f'Continuing with: "{QUESTION}"\n')

    # Strategy A: trim — keep only the last 4 messages. Cheap, and silently
    # amnesiac: the claim number and adjuster were in messages 1-2.
    trimmed = LONG_HISTORY[-4:] + [cast(MessageParam, {"role": "user", "content": QUESTION})]
    answer(trimmed, "A: TRIMMED to last 4 messages")

    # Strategy B: compact — summarize the whole session, continue on top of it.
    summary = compact(LONG_HISTORY)
    print(f"--- the compaction summary itself ---\n{summary}\n")
    compacted: list[MessageParam] = [
        {"role": "user", "content": f"[Summary of the conversation so far]\n{summary}\n\n{QUESTION}"},
    ]
    answer(compacted, "B: COMPACTED")

    print(
        "Trimming forgot silently; compaction kept every fact. (Note: on this\n"
        "toy session the summary is BIGGER than the original — compaction only\n"
        "pays off when history is tens of thousands of tokens, which is why\n"
        "it's triggered by a threshold, not run constantly.) This is exactly\n"
        "what Claude Code's /compact does — the sessions building THIS repo\n"
        "were compacted the same way. And compaction is lossy: real state\n"
        "(code, reports, memories) belongs in files, not in the summary."
    )


# ---------------------------------------------------------------------------
# DEMO 3: long-term memory — a fresh session that still "remembers" you.
# Module 03's forced-tool extraction, pointed at the transcript.
# ---------------------------------------------------------------------------

SAVE_MEMORIES: ToolParam = {
    "name": "save_memories",
    "description": "Store durable facts about this customer for future sessions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "memories": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Stable facts worth knowing NEXT session (identity, "
                "preferences, standing decisions). Not transient details.",
            }
        },
        "required": ["memories"],
    },
}


def demo_3_long_term_memory() -> None:
    print("\n" + "=" * 70)
    print("DEMO 3: long-term memory — extract facts now, inject them next session")
    print("=" * 70)

    # SESSION 1 ends: extract what's worth keeping from its transcript.
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in LONG_HISTORY)
    response = client.messages.create(
        model=MODEL, max_tokens=2500,
        tools=[SAVE_MEMORIES],
        tool_choice={"type": "tool", "name": "save_memories"},
        messages=[{
            "role": "user",
            "content": f"This support session is ending. Save the facts worth "
            f"remembering about this customer:\n\n{transcript}",
        }],
    )
    block = next(b for b in response.content if b.type == "tool_use")
    memories = cast(dict, block.input)["memories"]
    MEMORY_FILE.write_text(json.dumps(memories, indent=2))
    print(f"\nSession 1 ended. Extracted to {MEMORY_FILE.name}:")
    for m in memories:
        print(f"  - {m}")

    # SESSION 2: brand-new messages list — the model has NEVER seen session 1.
    # The only bridge is the file we inject into the system prompt.
    session_2: list[MessageParam] = [{
        "role": "user",
        "content": "Hi, me again. Which account are you paying my claim into, "
        "and is there anything on my file I should update?",
    }]
    response = client.messages.create(
        model=MODEL, max_tokens=2500,
        system="You are a HomeShield claims support agent. Be brief. Known facts "
        "about this customer from previous sessions:\n"
        + "\n".join(f"- {m}" for m in json.loads(MEMORY_FILE.read_text())),
        messages=session_2,
    )
    print(f"\nSession 2 (history is EMPTY — only memory.json bridges the gap):")
    print(f"agent: {get_text(response)}")
    print(
        "\n'The agent remembered me' = a file + a system prompt. At scale,\n"
        "memories get embedded and retrieved per-query (module 04's RAG,\n"
        "pointed at the agent's own past) — or live in the CRM behind a tool."
    )


if __name__ == "__main__":
    demo_1_growing_bill()
    demo_2_trim_vs_compact()
    demo_3_long_term_memory()

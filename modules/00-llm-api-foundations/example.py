"""Module 00 — LLM API Foundations.

Three demos of the primitive everything else is built on:
  1. One basic call, with the raw response structure printed
  2. The same question + a system prompt = a different "product"
  3. Multi-turn conversation (you carry the state) with streaming

Run from the repo root:  uv run modules/00-llm-api-foundations/example.py
"""

from anthropic import Anthropic
from anthropic.types import MessageParam
from dotenv import load_dotenv

load_dotenv()  # reads ANTHROPIC_API_KEY from .env

MODEL = "claude-opus-5"
client = Anthropic()  # picks up the key from the environment


def get_text(response) -> str:
    """Join the text blocks of a response.

    content can also hold "thinking" blocks (Claude thinks before answering,
    and that thinking counts against max_tokens). If the budget is too small
    the model can run out of tokens before writing any text — so never assume
    a text block exists.
    """

    text = "".join(b.text for b in response.content if b.type == "text")
    if not text:
        return f"(no text — stop_reason={response.stop_reason!r}; raise max_tokens)"
    return text


def demo_1_basic_call() -> None:
    """The primitive: messages in, content + stop_reason + usage out."""
    print("=" * 70)
    print("DEMO 1: one call, and what actually comes back")
    print("=" * 70)

    # max_tokens caps EVERYTHING the model generates — its internal thinking
    # AND the visible answer. Too small a cap = the answer gets cut off.
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": "In one sentence: what is an AI agent?"}],
    )

    # response.content is a LIST of blocks (text, thinking, tool_use...).
    # Never assume content[0] is text — check the type.
    print(f"\nAnswer: {get_text(response)}")

    print(f"\nstop_reason : {response.stop_reason}   <- why generation ended")
    print(f"input tokens : {response.usage.input_tokens}   <- what you paid to send")
    print(f"output tokens: {response.usage.output_tokens}   <- what you paid to receive")


def demo_2_system_prompt() -> None:
    """Same user message, different system prompt => different product."""
    print("\n" + "=" * 70)
    print("DEMO 2: the system prompt is where products live")
    print("=" * 70)

    user_message = "My package hasn't arrived and I'm frustrated."

    system_prompts = {
        "(no system prompt)": None,
        "support-agent product": (
            "You are a support agent for ShipFast Logistics. Be warm and brief "
            "(2 sentences max). Always: apologize once, then ask for the order "
            "number so you can look up the shipment."
        ),
    }

    for label, system in system_prompts.items():
        kwargs = {"system": system} if system else {}
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": user_message}],
            **kwargs,
        )
        print(f"\n--- {label} ---\n{get_text(response)}")


def demo_3_stateless_multiturn_streaming() -> None:
    """The API remembers nothing — your code re-sends history every call."""
    print("\n" + "=" * 70)
    print("DEMO 3: statelessness + streaming")
    print("=" * 70)

    history: list[MessageParam] = []

    def send(user_text: str) -> None:
        history.append({"role": "user", "content": user_text})
        print(f"\nUSER: {user_text}")
        print("ASSISTANT: ", end="", flush=True)

        # Streaming: tokens print as they're generated (this is what chat UIs do)
        with client.messages.stream(
            model=MODEL, max_tokens=2000, messages=history
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
            final = stream.get_final_message()

        # WE append the reply to history — the API won't remember it for us
        history.append({"role": "assistant", "content": get_text(final)})
        print(f"\n  (this call sent {final.usage.input_tokens} input tokens)")

    send("My name is Yash. Reply with just 'Noted.'")
    send("What's my name?")  # works ONLY because we re-sent turn 1 above

    print(
        "\nNote how input tokens GREW on the second call — the whole history was "
        "re-sent. This is why long agent sessions get expensive (see module 05)."
    )


if __name__ == "__main__":
    demo_1_basic_call()
    demo_2_system_prompt()
    demo_3_stateless_multiturn_streaming()

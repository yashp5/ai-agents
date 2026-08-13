"""Module 03 — Structured Output.

One messy insurance-claim email, extracted at three levels of rigor:
  1. Just ask for JSON        -> parse and pray
  2. Force a tool call        -> the schema-constrained workhorse pattern
  3. Validate + repair loop   -> what production extraction pipelines add

Run from the repo root:  uv run modules/03-structured-output/example.py
"""

import json
from datetime import date

from anthropic import Anthropic
from anthropic.types import MessageParam, ToolParam
from dotenv import load_dotenv

# Pydantic ships as a dependency of the anthropic SDK — no new installs.
from pydantic import BaseModel, Field, ValidationError, model_validator

load_dotenv()

MODEL = "claude-opus-5"
client = Anthropic()

# The input every document-AI company starts from: messy, human, incomplete.
CLAIM_EMAIL = """\
From: raj.mehta82@gmail.com
Subject: water damage!!

Hi, filing a claim on my homeowners policy (I think the number is
hp-40122-b?). A pipe burst behind the washing machine on the 3rd of last
month and soaked the laundry room floor. A plumber quoted me around $2.4k
for the repair, plus we lost a rug we paid about $300 for. Please help,
we're traveling until Friday so email is best.
 - Raj Mehta
"""

TODAY = "2026-08-11"  # the model needs this to resolve "the 3rd of last month"


def get_text(response) -> str:
    text = "".join(b.text for b in response.content if b.type == "text")
    if not text:
        return f"(no text — stop_reason={response.stop_reason!r}; raise max_tokens)"
    return text


# ---------------------------------------------------------------------------
# LEVEL 1: just ask. Note everything that is NOT guaranteed here.
# ---------------------------------------------------------------------------


def level_1_just_ask() -> None:
    print("=" * 70)
    print("LEVEL 1: 'respond with JSON' in the prompt")
    print("=" * 70)

    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,  # thinking shares this budget (module 00's lesson)
        system="You are the claims-intake assistant at HomeShield Insurance.",
        messages=[
            {
                "role": "user",
                "content": f"A customer emailed our claims inbox. Extract the "
                f"claim details as JSON (today is {TODAY}):\n\n{CLAIM_EMAIL}",
            }
        ],
    )
    text = get_text(response)
    print(f"\nRaw model output:\n{text}\n")

    try:
        json.loads(text)
        print("json.loads on the raw text: worked — THIS TIME.")
    except json.JSONDecodeError as e:
        print(f"json.loads on the raw text: FAILED ({e})")
    print(
        "Even when it parses: you didn't specify field names, so they can\n"
        "drift between runs — and downstream code breaks on the 3% day."
    )


# ---------------------------------------------------------------------------
# LEVEL 2: the tool-call trick. Define a "tool" whose input_schema IS your
# output schema, force the model to call it, read the arguments. No code
# ever implements record_claim — the call itself is the output.
# ---------------------------------------------------------------------------

RECORD_CLAIM: ToolParam = {
    "name": "record_claim",
    "description": "Record a structured insurance claim extracted from a customer message.",
    "input_schema": {
        "type": "object",
        "properties": {
            "claimant_name": {"type": "string"},
            "contact_email": {"type": "string"},
            "policy_number": {
                "type": "string",
                "description": "Normalize to uppercase, e.g. 'HP-40122-B'",
            },
            "incident_date": {
                "type": "string",
                "description": "YYYY-MM-DD. Resolve relative dates using today's date.",
            },
            "claim_type": {
                "type": "string",
                "enum": ["water_damage", "fire", "theft", "other"],
            },
            "damaged_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "estimated_cost_usd": {"type": "number"},
                    },
                    "required": ["description", "estimated_cost_usd"],
                },
            },
            "total_estimated_cost_usd": {"type": "number"},
        },
        "required": [
            "claimant_name", "contact_email", "policy_number", "incident_date",
            "claim_type", "damaged_items", "total_estimated_cost_usd",
        ],
    },
}


def extract_claim(extra_messages: list[MessageParam] | None = None) -> dict:
    """One forced-tool-call extraction; extra_messages carries repair context."""
    messages: list[MessageParam] = [
        {
            "role": "user",
            "content": f"A customer emailed our claims inbox. Extract the claim "
            f"(today is {TODAY}):\n\n{CLAIM_EMAIL}",
        }
    ]
    if extra_messages:
        messages.extend(extra_messages)
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        tools=[RECORD_CLAIM],
        # This is the constraint: the model MUST call this tool, and its
        # arguments MUST match the input_schema. No prose, no fences.
        tool_choice={"type": "tool", "name": "record_claim"},
        messages=messages,
    )
    block = next(b for b in response.content if b.type == "tool_use")
    # Stash the raw response so a repair turn can reference the tool_use id
    extract_claim.last = (response, block)  # type: ignore[attr-defined]
    return block.input


def level_2_forced_tool() -> dict:
    print("\n" + "=" * 70)
    print("LEVEL 2: force a tool call — the schema IS the output format")
    print("=" * 70)

    claim = extract_claim()
    print(f"\nblock.input is already a Python dict:\n{json.dumps(claim, indent=2)}")
    print(
        "\nGuaranteed: parses, right field names, right types, enum respected.\n"
        "NOT guaranteed: the VALUES are correct. '2026-13-45' fits a string field."
    )
    return claim


# ---------------------------------------------------------------------------
# LEVEL 3: validate the VALUES, and repair on failure.
# ---------------------------------------------------------------------------


class DamagedItem(BaseModel):
    description: str
    estimated_cost_usd: float = Field(gt=0)


class Claim(BaseModel):
    claimant_name: str
    contact_email: str
    policy_number: str = Field(pattern=r"^HP-\d{5}-[A-Z]$")
    incident_date: date  # "2026-13-45" dies here
    claim_type: str
    damaged_items: list[DamagedItem]
    total_estimated_cost_usd: float

    @model_validator(mode="after")
    def total_matches_items(self) -> "Claim":
        items_sum = sum(i.estimated_cost_usd for i in self.damaged_items)
        if abs(items_sum - self.total_estimated_cost_usd) > 0.01:
            raise ValueError(
                f"total_estimated_cost_usd ({self.total_estimated_cost_usd}) "
                f"!= sum of damaged_items ({items_sum})"
            )
        return self


def level_3_validate_and_repair(claim_dict: dict) -> None:
    print("\n" + "=" * 70)
    print("LEVEL 3: semantic validation (Pydantic) + repair loop")
    print("=" * 70)

    # First, PROOF that schema-valid != correct: a record the API would have
    # happily let through, shredded by the validation layer.
    corrupted = {**claim_dict, "incident_date": "2026-13-45", "total_estimated_cost_usd": 9999.0}
    try:
        Claim.model_validate(corrupted)
    except ValidationError as e:
        print(f"\nA schema-valid but WRONG record fails validation:\n{e}\n")

    # Now the real extraction, with up to 2 repair attempts.
    for attempt in range(1, 3):
        try:
            claim = Claim.model_validate(claim_dict)
            print(f"Attempt {attempt}: extraction VALID.")
            print(f"  {claim.claimant_name} | {claim.policy_number} | "
                  f"{claim.incident_date} | ${claim.total_estimated_cost_usd:,.2f}")
            break
        except ValidationError as e:
            print(f"Attempt {attempt}: validation failed, sending error back for repair…")
            response, block = extract_claim.last  # type: ignore[attr-defined]
            claim_dict = extract_claim(
                extra_messages=[
                    {"role": "assistant", "content": response.content},
                    {
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Validation failed, fix and re-record:\n{e}",
                            "is_error": True,
                        }],
                    },
                ]
            )
    else:
        print("Still invalid after repairs -> in production: human review queue.")

    print(
        "\nProduction adds two more layers this demo can't: business rules\n"
        "(does HP-40122-B exist in OUR database?) and confidence routing\n"
        "(uncertain or rule-failing records go to a human review queue).\n"
        "That review queue IS the product at most document-AI companies."
    )


if __name__ == "__main__":
    level_1_just_ask()
    claim_dict = level_2_forced_tool()
    level_3_validate_and_repair(claim_dict)

"""Module 06 — Orchestration.

Two demos of arranging LLM calls into systems:
  1. Orchestrator + subagents — context isolation is the point
  2. Durable execution — a journaled claims workflow that crashes after
     step 3 and resumes exactly where it died (Temporal's trick, in ~15 lines)

Run from the repo root:  uv run modules/06-orchestration/example.py
"""

import json
from pathlib import Path
from typing import Callable, cast

from anthropic import Anthropic
from anthropic.types import ToolParam
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-5"
JOURNAL_FILE = Path(__file__).parent / "workflow_state.json"
client = Anthropic()


def get_text(response) -> str:
    text = "".join(b.text for b in response.content if b.type == "text")
    return text or f"(no text — stop_reason={response.stop_reason!r})"


def tool_input(response) -> dict:
    return cast(dict, next(b for b in response.content if b.type == "tool_use").input)


def count_tokens(system: str, user: str) -> int:
    return client.messages.count_tokens(
        model=MODEL, system=system, messages=[{"role": "user", "content": user}]
    ).input_tokens


# ===========================================================================
# DEMO 1: orchestrator + subagents. Each worker gets a FRESH context with
# only its own materials; the lead's window accumulates findings, not process.
# ===========================================================================

POLICY_EXCERPTS = """\
- Sudden and accidental discharge of water from plumbing (incl. burst pipes) is
  a covered peril; resulting damage to floors/walls covered under Coverage A.
- Water escaping continuously for 14+ days is excluded regardless of discovery date.
- Personal property (rugs, furniture) covered under Coverage C up to $5,000,
  at actual cash value; items over $250 need proof of ownership/value.
- Deductible: $500 per claim, applied once to the whole claim.
- Losses must be reported within 60 days of discovery (late notice may deny).
- Homes vacant over 60 consecutive days at time of loss: excluded.
"""

CLAIM_FILE = """\
Claim CLM-2214 | Policy HP-40122-B (active since 2019, no prior claims)
Incident: burst pipe behind washing machine, laundry room — 2026-07-03
Reported: 2026-08-11 (customer was traveling; email contact preferred)
Damages claimed: plumber's WRITTEN estimate $2,400 (licensed contractor);
  area rug $300 (no receipt provided yet)
Home occupancy: owner-occupied, no vacancy on record
Customer notes: dried the area with fans within 72 hours; worried about mold
"""

PLAN_TOOL: ToolParam = {
    "name": "assign_subtasks",
    "description": "Assign one focused question to each specialist worker.",
    "input_schema": {
        "type": "object",
        "properties": {
            "coverage_question": {
                "type": "string",
                "description": "Question for the policy-coverage specialist (they have the policy terms)",
            },
            "consistency_question": {
                "type": "string",
                "description": "Question for the claim-consistency specialist (they have the claim file)",
            },
        },
        "required": ["coverage_question", "consistency_question"],
    },
}

CASE_BRIEF = (
    "Case: burst-pipe water damage claim CLM-2214, ~$2,700 claimed, reported "
    "about 5 weeks after the incident."
)


def run_worker(role: str, materials: str, question: str) -> str:
    """A subagent = a FRESH context. It reads its materials (tokens the
    orchestrator never pays for) and returns only conclusions."""
    system = (
        f"You are a {role} at HomeShield Insurance. Answer the lead adjuster's "
        "question from your materials in at most 120 words of findings."
    )
    user = f"MATERIALS:\n{materials}\n\nLEAD ADJUSTER ASKS: {question}"
    response = client.messages.create(
        model=MODEL, max_tokens=2500, system=system,
        messages=[{"role": "user", "content": user}],
    )
    print(f"    (worker context: {count_tokens(system, user)} tokens — "
          f"isolated, then thrown away)")
    return get_text(response)


def demo_1_subagents() -> None:
    print("=" * 70)
    print("DEMO 1: orchestrator-workers — findings flow up, contexts stay apart")
    print("=" * 70)

    # Step 1: the LEAD plans. It has only a 2-line brief — not the documents.
    response = client.messages.create(
        model=MODEL, max_tokens=2500,
        tools=[PLAN_TOOL], tool_choice={"type": "tool", "name": "assign_subtasks"},
        messages=[{
            "role": "user",
            "content": f"{CASE_BRIEF}\nAssign one question to each specialist "
            "to decide whether to approve this claim.",
        }],
    )
    plan = tool_input(response)
    print(f"\nLEAD assigns:\n  coverage    -> {plan['coverage_question']}\n"
          f"  consistency -> {plan['consistency_question']}\n")

    # Step 2: workers run in isolated contexts (in production: in parallel).
    print("COVERAGE WORKER:")
    coverage = run_worker("policy-coverage specialist", POLICY_EXCERPTS,
                          plan["coverage_question"])
    print(f"    {coverage}\n")
    print("CONSISTENCY WORKER:")
    consistency = run_worker("claim-consistency and fraud-signals specialist",
                             CLAIM_FILE, plan["consistency_question"])
    print(f"    {consistency}\n")

    # Step 3: the LEAD synthesizes — it sees findings, never the raw documents.
    synth_system = "You are the lead adjuster. Give a recommendation in 3 sentences."
    synth_user = (
        f"{CASE_BRIEF}\n\nCoverage specialist reports:\n{coverage}\n\n"
        f"Consistency specialist reports:\n{consistency}\n\nRecommend: approve, "
        "deny, or escalate — and what's still needed."
    )
    response = client.messages.create(
        model=MODEL, max_tokens=2500, system=synth_system,
        messages=[{"role": "user", "content": synth_user}],
    )
    print(f"LEAD synthesis (context: {count_tokens(synth_system, synth_user)} "
          f"tokens — the raw documents never entered its window):")
    print(f"  {get_text(response)}")


# ===========================================================================
# DEMO 2: durable execution. The whole trick: journal every step's result;
# on restart, replay journaled steps instantly and resume at the first
# un-run step. This is Temporal/Inngest's core, in miniature.
# ===========================================================================

CLAIM_EMAIL = (
    "Hi, filing a claim on my homeowners policy (I think the number is "
    "hp-40122-b?). A pipe burst behind the washing machine on July 3rd and "
    "soaked the laundry room floor. A plumber quoted $2,400 for repairs, plus "
    "we lost a rug worth about $300. - Raj Mehta"
)

POLICY_DB = {
    "HP-40122-B": {"status": "active", "deductible_usd": 500,
                   "auto_approve_limit_usd": 3000, "holder": "Raj Mehta"},
}

EXTRACT_TOOL: ToolParam = {
    "name": "record_claim",
    "description": "Record the extracted claim.",
    "input_schema": {
        "type": "object",
        "properties": {
            "policy_number": {"type": "string", "description": "uppercase"},
            "incident_date": {"type": "string", "description": "YYYY-MM-DD, year 2026"},
            "total_claimed_usd": {"type": "number"},
        },
        "required": ["policy_number", "incident_date", "total_claimed_usd"],
    },
}

VERDICT_TOOL: ToolParam = {
    "name": "record_verdict",
    "description": "Record the coverage verdict.",
    "input_schema": {
        "type": "object",
        "properties": {"covered": {"type": "boolean"}, "reason": {"type": "string"}},
        "required": ["covered", "reason"],
    },
}


def llm_extract() -> dict:
    response = client.messages.create(
        model=MODEL, max_tokens=2500, tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "record_claim"},
        messages=[{"role": "user", "content":
                   f"A customer emailed our claims inbox:\n\n{CLAIM_EMAIL}"}],
    )
    return tool_input(response)


def llm_check_coverage(claim: dict) -> dict:
    # The verdict step gets the ORIGINAL email, not just the extracted fields —
    # pipelines that pass only their own summaries starve downstream steps
    # of the facts they need (first run of this demo proved it).
    response = client.messages.create(
        model=MODEL, max_tokens=2500, tools=[VERDICT_TOOL],
        tool_choice={"type": "tool", "name": "record_verdict"},
        messages=[{"role": "user", "content":
                   f"Policy terms:\n{POLICY_EXCERPTS}\n"
                   f"Customer's email (assume truthful; verification of documents "
                   f"happens at a later step):\n{CLAIM_EMAIL}\n"
                   f"Extracted claim: {json.dumps(claim)}\n"
                   f"Intake notes: reported 2026-08-11; home owner-occupied; "
                   f"pipe failure was sudden per customer.\n"
                   "Is the described loss a covered peril under these terms?"}],
    )
    return tool_input(response)


def llm_draft_letter(claim: dict, decision: dict) -> str:
    response = client.messages.create(
        model=MODEL, max_tokens=2500,
        messages=[{"role": "user", "content":
                   f"Write a 3-sentence approval letter to {POLICY_DB[claim['policy_number']]['holder']}: "
                   f"claim approved, payout ${decision['payout_usd']} "
                   f"(after ${decision['deductible_usd']} deductible), paid by ACH within 5 business days."}],
    )
    return get_text(response)


class SimulatedCrash(RuntimeError):
    pass


def run_claims_workflow(crash_after: str | None = None) -> dict | None:
    """The workflow function. Deterministic sequencing; all real work
    (LLM calls, DB lookups, payments) happens inside journaled steps."""
    journal: dict = (
        json.loads(JOURNAL_FILE.read_text()) if JOURNAL_FILE.exists() else {}
    )

    def step(name: str, fn: Callable[[], dict | str]):
        if name in journal:  # already ran in a previous life — replay for free
            print(f"  [replay ] {name}  <- from journal: no LLM call, no cost, no side effect")
            return journal[name]
        result = fn()
        journal[name] = result
        JOURNAL_FILE.write_text(json.dumps(journal, indent=2))  # durable BEFORE moving on
        print(f"  [execute] {name}")
        if name == crash_after:
            raise SimulatedCrash(f"power failure right after '{name}'")
        return result

    claim = cast(dict, step("extract_claim", llm_extract))
    policy = cast(dict, step("look_up_policy",
                             lambda: POLICY_DB[claim["policy_number"]]))
    verdict = cast(dict, step("check_coverage", lambda: llm_check_coverage(claim)))
    decision = cast(dict, step("rules_gate", lambda: {
        "approved": bool(verdict["covered"]) and policy["status"] == "active",
        "payout_usd": claim["total_claimed_usd"] - policy["deductible_usd"],
        "deductible_usd": policy["deductible_usd"],
        "route": ("auto_approve"
                  if claim["total_claimed_usd"] < policy["auto_approve_limit_usd"]
                  else "human_review"),
    }))
    if not decision["approved"] or decision["route"] != "auto_approve":
        print("  -> routed to human review queue (workflow would now WAIT for a signal)")
        return None
    letter = step("draft_letter", lambda: llm_draft_letter(claim, decision))
    # Money moves in a journaled step -> replay can NEVER pay twice.
    payment = step("issue_payment", lambda: {
        "payment_id": "PAY-CLM-2214", "amount_usd": decision["payout_usd"],
    })
    return {"decision": decision, "letter": letter, "payment": payment}


def demo_2_durable_workflow() -> None:
    print("\n" + "=" * 70)
    print("DEMO 2: durable execution — journal, crash, replay, resume")
    print("=" * 70)

    JOURNAL_FILE.unlink(missing_ok=True)  # fresh journal each demo run

    print("\nRUN 1 (the process will die mid-workflow):")
    try:
        run_claims_workflow(crash_after="check_coverage")
    except SimulatedCrash as e:
        print(f"  *** CRASH: {e} ***")

    print(f"\nThe journal survived on disk ({JOURNAL_FILE.name}):")
    print("  steps saved:", ", ".join(json.loads(JOURNAL_FILE.read_text())))

    print("\nRUN 2 (restart — same function, from the top):")
    result = run_claims_workflow()

    if result:
        print(f"\nPayout: ${result['payment']['amount_usd']} "
              f"({result['payment']['payment_id']})")
        print(f"Letter:\n{result['letter']}")
    print(
        "\nSteps 1-3 replayed from the journal (free, instant, no double side\n"
        "effects); the rest executed for the first time. That's the secret of\n"
        "Temporal/Inngest: journal + replay = workflows that survive anything,\n"
        "wait weeks for human approvals, and never pay a claim twice."
    )


if __name__ == "__main__":
    demo_1_subagents()
    demo_2_durable_workflow()

"""Module 08 — Reliability.

Module 03 built a claim extractor. This is what you do before letting it near
real money:

  1. EVALS      — run it against a labeled golden set, score it per field
  2. JUDGE      — grade free-form output (a customer letter) with a rubric
  3. ROUTING    — sweep the confidence threshold: coverage vs precision
  4. TRACING    — what every model call cost, in tokens and milliseconds

Nothing here is exotic. That's the point: reliability is unglamorous plumbing,
and it's most of the engineering at a serious AI company.

Run from the repo root:  uv run modules/08-reliability/example.py
"""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, cast

from anthropic import Anthropic
from anthropic.types import ToolParam
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-5"
TODAY = "2026-08-13"  # a Thursday — cases below lean on relative dates
client = Anthropic()

# Rough, for the cost column. Check the current pricing page before quoting it.
PRICE_IN, PRICE_OUT = 15.0, 75.0  # $ per million tokens


# ---------------------------------------------------------------------------
# TRACING — 20 lines that answer "what did that run cost, and where did the
# time go?". Every observability product is this idea plus a UI.
# ---------------------------------------------------------------------------


@dataclass
class Span:
    name: str
    seconds: float
    tokens_in: int
    tokens_out: int
    stop_reason: str | None


TRACE: list[Span] = []


def traced(name: str, **kwargs) -> Any:
    """client.messages.create, wrapped. In production this also records the
    prompt, the tools offered, and a trace_id linking spans into one tree."""
    start = time.perf_counter()
    response = client.messages.create(model=MODEL, **kwargs)
    TRACE.append(Span(name, time.perf_counter() - start, response.usage.input_tokens,
                      response.usage.output_tokens, response.stop_reason))
    return response


def print_trace() -> None:
    print("\n" + "=" * 74)
    print("TRACE: every model call this script made")
    print("=" * 74 + "\n")
    print(f"  {'span':<22} {'calls':>5} {'tok in':>8} {'tok out':>8} "
          f"{'avg s':>7} {'est $':>8}")
    names = sorted({s.name for s in TRACE}, key=lambda n: -sum(
        s.tokens_in for s in TRACE if s.name == n))
    total_cost = 0.0
    for name in names:
        spans = [s for s in TRACE if s.name == name]
        t_in = sum(s.tokens_in for s in spans)
        t_out = sum(s.tokens_out for s in spans)
        cost = (t_in * PRICE_IN + t_out * PRICE_OUT) / 1_000_000
        total_cost += cost
        print(f"  {name:<22} {len(spans):>5} {t_in:>8,} {t_out:>8,} "
              f"{sum(s.seconds for s in spans) / len(spans):>7.1f} {cost:>8.4f}")
    print(f"\n  {len(TRACE)} calls, ~${total_cost:.4f} total.")
    print("  Cost per unit of work is the number that decides whether the\n"
          "  product has a business model. You cannot know it without this.")


# ---------------------------------------------------------------------------
# THE GOLDEN SET — the actual asset. Six cases here; a real one is 50–500,
# curated by someone who knows the domain, and grown from production failures.
# ---------------------------------------------------------------------------

GOLDEN_SET: list[dict] = [
    {
        "id": "baseline",
        "email": "Hi, filing a claim on my homeowners policy (I think the number is "
                 "hp-40122-b?). A pipe burst behind the washing machine on the 3rd of "
                 "last month and soaked the laundry room floor. A plumber quoted me "
                 "around $2.4k for the repair, plus we lost a rug we paid about $300 "
                 "for. — Raj Mehta",
        "expected": {"policy_number": "HP-40122-B", "incident_date": "2026-07-03",
                     "claim_type": "water_damage", "total_usd": 2700},
    },
    {
        "id": "no-policy-number",  # the honest-null test: does it invent one?
        "email": "Hello — my kitchen ceiling collapsed yesterday after the upstairs "
                 "unit's dishwasher leaked. I can't find my policy paperwork right "
                 "now, sorry. Damage looks like about $3,100. — Priya Raman",
        "expected": {"policy_number": None, "incident_date": "2026-08-12",
                     "claim_type": "water_damage", "total_usd": 3100},
    },
    {
        "id": "relative-date",
        "email": "Policy HP-55210-D. There was a small kitchen fire last Friday "
                 "morning — grease pan. Cabinets and the range hood are ruined, "
                 "$1,850 per the contractor. — T. Okafor",
        "expected": {"policy_number": "HP-55210-D", "incident_date": "2026-08-07",
                     "claim_type": "fire", "total_usd": 1850},
    },
    {
        "id": "superseded-quote",  # two numbers, only one is current
        "email": "Re: policy hp 71004 a. Storm took out a window on 2026-08-01. The "
                 "first company quoted $4,000 which felt insane, so I got a second "
                 "opinion and they'll do it for $1,750. Going with the second one. "
                 "— Marcus Feld",
        "expected": {"policy_number": "HP-71004-A", "incident_date": "2026-08-01",
                     "claim_type": "other", "total_usd": 1750},
    },
    {
        "id": "peril-with-distractor",  # water words, but the peril is theft
        "email": "HP-33871-K — we were burgled while away. They took a laptop "
                 "($1,400) and my wife's jewellery ($2,200), and left the bathroom "
                 "tap running which flooded the hallway. Happened sometime on "
                 "2026-08-09. — Dan Whitfield",
        "expected": {"policy_number": "HP-33871-K", "incident_date": "2026-08-09",
                     "claim_type": "theft", "total_usd": 3600},
    },
    {
        "id": "customer-bad-math",  # stated total is wrong; items are the truth
        "email": "Claim on HP-40988-M please. Roof leak on 2026-07-28 after the hail. "
                 "Ruined the mattress ($600) and a bookcase ($300). Total damage "
                 "$1,200 as far as I'm concerned. — S. Ortega",
        "expected": {"policy_number": "HP-40988-M", "incident_date": "2026-07-28",
                     "claim_type": "water_damage", "total_usd": 900},
    },
    {
        "id": "already-reimbursed",  # not every listed number is a claimable one
        "email": "HP-62550-J. Fire in the garage on 2026-08-05 from a faulty charger. "
                 "Lost the TV that was stored there ($900) — the retailer has already "
                 "refunded that one — and the epoxy flooring, $2,000 to redo. "
                 "— Lena Brandt",
        "expected": {"policy_number": "HP-62550-J", "incident_date": "2026-08-05",
                     "claim_type": "fire", "total_usd": 2000},
    },
    {
        "id": "house-rule-gradual",  # a rule that lives in OUR handbook, not in the email
        "email": "Policy HP-19045-T. We finally called someone about the damp patch "
                 "under the kitchen sink — turns out the joint has been weeping since "
                 "at least March and the cabinet base and subfloor are rotten. "
                 "Discovered 2026-08-11, quote is $3,400. — Yusuf Aydin",
        # HomeShield's handbook (module 04) excludes gradual leaks over 14 days from
        # water_damage and codes them 'other'. The extractor was never told that.
        "expected": {"policy_number": "HP-19045-T", "incident_date": "2026-08-11",
                     "claim_type": "other", "total_usd": 3400},
    },
]

SCORED_FIELDS = ["policy_number", "incident_date", "claim_type", "total_usd"]

RECORD_CLAIM: ToolParam = {
    "name": "record_claim",
    "description": "Record a structured claim extracted from a customer message.",
    "input_schema": {
        "type": "object",
        "properties": {
            "policy_number": {"type": ["string", "null"],
                              "description": "Normalized 'HP-#####-X'. null if the "
                                             "message does not contain one — never guess."},
            "incident_date": {"type": "string",
                              "description": "YYYY-MM-DD. Resolve relative dates from today."},
            "claim_type": {"type": "string",
                           "enum": ["water_damage", "fire", "theft", "other"],
                           "description": "The primary peril that caused the loss."},
            "total_usd": {"type": "number",
                          "description": "Sum of the current cost of damaged items."},
            "confidence": {"type": "number",
                           "description": "0-1. Your confidence that every field above "
                                          "is correct. Be honest; low is fine."},
            "review_reason": {"type": "string",
                              "description": "If anything was ambiguous or missing, say "
                                             "what. Empty string if fully clear."},
        },
        "required": ["policy_number", "incident_date", "claim_type", "total_usd",
                     "confidence", "review_reason"],
    },
}


def extract(email: str) -> dict:
    response = traced(
        "extract", max_tokens=2000, tools=[RECORD_CLAIM],
        tool_choice={"type": "tool", "name": "record_claim"},
        system=f"You are the claims-intake extractor at HomeShield Insurance. "
               f"Today is {TODAY}.",
        messages=[{"role": "user", "content": f"Extract the claim:\n\n{email}"}],
    )
    block = next(b for b in response.content if b.type == "tool_use")
    return cast(dict, block.input)


def grade(actual: dict, expected: dict) -> dict[str, bool]:
    """The scorer. Normalize first — 'hp-40122-b' and 'HP-40122-B' are the same
    answer, and marking that wrong teaches you nothing."""
    def norm(k: str, v: Any) -> Any:
        if v is None or v == "":
            return None
        if k == "policy_number":
            return str(v).upper().replace(" ", "")
        if k == "total_usd":
            return round(float(v), 2)
        return str(v).strip()

    return {k: norm(k, actual.get(k)) == norm(k, expected[k]) for k in SCORED_FIELDS}


# ---------------------------------------------------------------------------
# DEMO 1: run the eval
# ---------------------------------------------------------------------------


@dataclass
class Result:
    case: dict
    actual: dict = field(default_factory=dict)
    scores: dict[str, bool] = field(default_factory=dict)

    @property
    def correct(self) -> bool:
        return all(self.scores.values())

    @property
    def confidence(self) -> float:
        return float(self.actual.get("confidence", 0.0))


def demo_1_evals() -> list[Result]:
    print("=" * 74)
    print(f"DEMO 1: the eval — {len(GOLDEN_SET)} labeled cases, scored per field")
    print("=" * 74 + "\n")

    def run(case: dict) -> Result:
        actual = extract(case["email"])
        return Result(case, actual, grade(actual, case["expected"]))

    with ThreadPoolExecutor(max_workers=8) as pool:  # evals are embarrassingly parallel
        results = list(pool.map(run, GOLDEN_SET))

    header = "  ".join(f"{f[:9]:>9}" for f in SCORED_FIELDS)
    print(f"  {'case':<22} {header}   conf")
    for r in results:
        marks = "  ".join(f"{'   ok' if r.scores[f] else ' FAIL':>9}" for f in SCORED_FIELDS)
        print(f"  {r.case['id']:<22} {marks}   {r.confidence:.2f}")

    for r in results:
        if r.correct:
            continue
        print(f"\n  {r.case['id']} — what it got wrong:")
        for f in SCORED_FIELDS:
            if not r.scores[f]:
                print(f"      {f}: got {r.actual.get(f)!r}, expected "
                      f"{r.case['expected'][f]!r}")
        if r.actual.get("review_reason"):
            print(f"      (model said: {r.actual['review_reason']})")

    n = len(results)
    print(f"\n  Case-level pass rate: {sum(r.correct for r in results)}/{n} "
          f"({sum(r.correct for r in results) / n:.0%})")
    print("  Per field:")
    for f in SCORED_FIELDS:
        hits = sum(r.scores[f] for r in results)
        print(f"      {f:<16} {hits}/{n}  {hits / n:>4.0%}")
    if all(r.correct for r in results):
        print("\n  Everything passed — which is a warning, not a victory. A golden set\n"
              "  nothing fails has stopped measuring anything; you grow it from real\n"
              "  production failures until it hurts again.")
    else:
        print("\n  Never report just the average: it hides WHICH field is broken, and\n"
              "  these fields do not cost the same when wrong. Note also what kind of\n"
              "  failure this is — where the label encodes a rule that lives in our\n"
              "  handbook and never reached the prompt, the fix is context (module 04),\n"
              "  not a better model. Evals tell you which of those you have.")
    return results


# ---------------------------------------------------------------------------
# DEMO 2: LLM-as-judge. There is no string to diff a customer letter against,
# so you grade against a rubric — and you check the judge can tell bad from good.
# ---------------------------------------------------------------------------

LETTER_BRIEF = (
    "Write the coverage decision letter to Raj Mehta for claim CLM-2214 on policy "
    "HP-40122-B: sudden burst pipe on 2026-07-03, $2,700 of damage, covered under "
    "his homeowners policy, $500 deductible applies once per claim, so we pay "
    "$2,200. Payment issues within 5 business days by ACH."
)

BAD_LETTER = """\
Dear Customer, your claim has been processed. After review we have determined an
amount will be paid to you shortly. Some deductions may apply per the terms of
your agreement. Please contact us with any questions.
Regards, Claims
"""

SCORE_LETTER: ToolParam = {
    "name": "score_letter",
    "description": "Score a customer-facing claims letter against the rubric.",
    "input_schema": {
        "type": "object",
        "properties": {
            # Reasoning FIRST: a score written before its justification is a vibe.
            "reasoning": {"type": "string", "description": "Assess each criterion "
                                                           "before scoring. 2-4 sentences."},
            "factual_accuracy": {"type": "integer", "description": "1-5. Are the amounts, "
                                 "dates and IDs present and consistent with the facts? "
                                 "Invented or vague figures score 1-2."},
            "cites_basis": {"type": "integer", "description": "1-5. Does it explain the "
                            "coverage decision and the deductible arithmetic?"},
            "next_steps": {"type": "integer", "description": "1-5. Does the customer know "
                           "what happens next and when?"},
            "tone": {"type": "integer", "description": "1-5. Clear, warm, non-evasive. "
                     "Length is NOT quality."},
        },
        "required": ["reasoning", "factual_accuracy", "cites_basis", "next_steps", "tone"],
    },
}
CRITERIA = ["factual_accuracy", "cites_basis", "next_steps", "tone"]


def judge(letter: str) -> dict:
    response = traced(
        "judge", max_tokens=1500, tools=[SCORE_LETTER],
        tool_choice={"type": "tool", "name": "score_letter"},
        system="You are a strict claims-quality reviewer. Score honestly; most "
               "letters are not 5s. Judge against the FACTS below, not eloquence.\n"
               + LETTER_BRIEF,
        messages=[{"role": "user", "content": f"Score this letter:\n\n{letter}"}],
    )
    return cast(dict, next(b for b in response.content if b.type == "tool_use").input)


def demo_2_llm_as_judge() -> None:
    print("\n" + "=" * 74)
    print("DEMO 2: LLM-as-judge — grading output with no right answer")
    print("=" * 74 + "\n")

    written = traced(
        "write_letter", max_tokens=2000,
        system="You are a HomeShield claims adjuster writing to a customer.",
        messages=[{"role": "user", "content": LETTER_BRIEF}],
    )
    good = "".join(b.text for b in written.content if b.type == "text")
    print(f"The letter our pipeline produced:\n{'-' * 60}\n{good.strip()}\n{'-' * 60}\n")

    for label, letter in [("our letter", good), ("a deliberately vague one", BAD_LETTER)]:
        scores = judge(letter)
        line = "  ".join(f"{c.replace('_', ' ')}: {scores[c]}/5" for c in CRITERIA)
        print(f"  {label:<26} {line}")
        print(f"  {'':<26} \"{scores['reasoning'][:150]}…\"\n")

    print("  The judge separates them — that's the minimum bar, and it is exactly\n"
          "  what people skip. Before trusting a judge in CI you hand-label ~30\n"
          "  items and measure agreement with it; an uncalibrated judge produces\n"
          "  numbers that move while quality doesn't.")


# ---------------------------------------------------------------------------
# DEMO 3: routing. The threshold is a business decision, not an ML one.
# ---------------------------------------------------------------------------


def demo_3_routing(results: list[Result]) -> None:
    print("\n" + "=" * 74)
    print("DEMO 3: confidence routing — coverage vs precision")
    print("=" * 74 + "\n")

    print(f"  {'threshold':>9} {'auto-approved':>14} {'coverage':>9} "
          f"{'precision':>10}   wrong claims auto-paid")
    for t in (0.50, 0.70, 0.80, 0.90, 0.95, 0.99):
        auto = [r for r in results if r.confidence >= t]
        if not auto:
            print(f"  {t:>9.2f} {'0':>14} {'0%':>9} {'—':>10}")
            continue
        bad = [r for r in auto if not r.correct]
        print(f"  {t:>9.2f} {len(auto):>14} {len(auto) / len(results):>8.0%} "
              f"{1 - len(bad) / len(auto):>10.0%}   "
              f"{', '.join(r.case['id'] for r in bad) or 'none'}")

    print("\n  Read the last column as money. Every row is a real choice:")
    print("    - review everything      -> 100% precise, 0% automated, no product")
    print("    - auto-approve all       -> 100% automated, and you pay wrong claims")
    print("  Nobody can pick the row for you: it depends on what an error costs\n"
          "  versus what a reviewer costs. At $6/review vs $2,200/bad payout, you\n"
          "  review a lot. In a support-chat product the trade is far cheaper.")

    if all(r.correct for r in results):
        print("\n  (Precision is 100% at every row only because nothing failed this\n"
              "   run. Add the cases that break it — that's what a golden set is for.)")

    conf = sorted({round(r.confidence, 2) for r in results})
    if len(conf) <= 2:
        print(f"\n  Note this run's confidences: {conf} — self-reported scores cluster.")
        print("  That's the standard finding, and why real systems compute confidence\n"
              "  from validation failures, business-rule violations, retrieval scores\n"
              "  and run-to-run disagreement, using the model's number as ONE signal.")

    queue = [r for r in results if not r.correct or r.confidence < 0.9]
    print(f"\n  Review queue for this batch ({len(queue)} of {len(results)}):")
    for r in queue:
        reason = r.actual.get("review_reason") or "low confidence"
        print(f"    - {r.case['id']:<22} conf {r.confidence:.2f}  |  {reason[:70]}")
    print("\n  Each item a human corrects becomes a new golden-set case. That loop\n"
          "  — corrections -> evals -> higher automation rate — is the whole moat.")


if __name__ == "__main__":
    results = demo_1_evals()
    demo_2_llm_as_judge()
    demo_3_routing(results)
    print_trace()

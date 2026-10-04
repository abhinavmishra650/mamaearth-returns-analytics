"""
generate_narrative.py
Turns the verified findings in narrator/findings.json (written by
analysis/clean_and_eda.py) into a Situation-Complication-Resolution business
narrative for Mamaearth's regional ops and finance heads.

Two paths, same return shape ({"status", "narrative", "tokens"} or
{"status": "error", "narrative": None, "message"}):
  - Online:  uses the free-tier Gemini API via the google-genai client.
  - Offline: a fully deterministic f-string template, zero network/API key.

generate_scr_narrative() is the single entry point most callers want: it
tries the online path and falls back to the offline path automatically
whenever no API key is configured or the online call itself fails, so it
always returns a usable narrative with zero required setup.

Run directly:  python narrator/generate_narrative.py
  - With GEMINI_API_KEY (or GOOGLE_API_KEY) set in the environment: calls
    the live Gemini API.
  - With no key set: runs the offline path only -- no network call is even
    attempted.
"""

import calendar
import json
import os


def _findings_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "findings.json")


def load_findings() -> dict:
    with open(_findings_path()) as f:
        return json.load(f)


def _money(x: float) -> str:
    return f"{x:,.2f}"


def _month_name(year_month: str) -> str:
    """'2026-03' -> 'March 2026' (human-readable, for the narrative text)."""
    year, month = year_month.split("-")
    return f"{calendar.month_name[int(month)]} {year}"


SYSTEM_INSTRUCTION = (
    "You are a senior data analyst writing for Mamaearth's regional ops and finance heads. "
    "Structure your entire response into exactly three labeled sections, in this exact order: "
    "'Situation', 'Complication', 'Resolution'. Every number you state must come from the findings "
    "given in the user message and must appear with the exact same value given there -- never invent, "
    "re-round, or estimate a statistic that was not supplied. Refer to months by name (e.g. 'March "
    "2026'), not by their raw YYYY-MM code. Write in plain business language a non-technical "
    "operations or finance leader can act on without reading a notebook or a SQL query. Keep the "
    "whole narrative to roughly 200-300 words."
)


def _build_user_prompt(findings: dict) -> str:
    """Built entirely from the findings dict -- a different findings.json produces a different
    prompt (and therefore a different narrative) without touching this function."""
    true_peak = findings["true_peak_month"]
    inflated = findings["outlier_inflated_month"]
    risk = findings["highest_risk_segment"]
    rates = findings["return_rate_by_payment"]

    return (
        "Write the SCR narrative using only these verified figures -- do not use any other numbers:\n"
        f"- Cleaned total revenue: Rs.{_money(findings['cleaned_total_revenue_inr'])}\n"
        f"- Raw (pre-cleaning) total revenue: Rs.{_money(findings['raw_total_revenue_inr'])}\n"
        f"- Duplicate-order reconciliation delta: Rs.{_money(findings['duplicate_reconciliation_delta_inr'])}\n"
        f"- Return rate by payment method: COD {rates['COD']}%, CARD {rates['CARD']}%, UPI {rates['UPI']}%\n"
        f"- Highest-risk segment: {risk['payment_method']} orders in city_tier {risk['city_tier']} "
        f"cities, {risk['return_rate_pct']}% returned\n"
        f"- True peak month once bulk-order outliers are excluded: {_month_name(true_peak['month'])} "
        f"at Rs.{_money(true_peak['revenue_inr'])}\n"
        f"- Outlier-inflated month: {_month_name(inflated['month'])} looked like "
        f"Rs.{_money(inflated['apparent_revenue_inr'])} but is actually Rs.{_money(inflated['corrected_revenue_inr'])} "
        "once the two bulk-order outliers are excluded\n\n"
        "Situation: summarize the business context and the overall revenue picture. "
        "Complication: explain the returns problem, which exact segment concentrates the risk, and the "
        "duplicate-order data-quality issue behind the reconciliation delta. "
        "Resolution: recommend concrete next steps regional ops and finance can act on this week."
    )


# ---------------------------------------------------------------------------
# Task 2 / Task 3 (online) + Task 4 (offline fallback), combined into one
# public entry point -- see module docstring for why.
# ---------------------------------------------------------------------------
def generate_scr_narrative(findings: dict) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if not api_key:
        print("[generate_narrative] No GEMINI_API_KEY/GOOGLE_API_KEY set -- using the offline path.")
        return generate_scr_narrative_offline(findings)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=api_key,
            # timeout is in milliseconds; 15000ms = 15s, comfortably over the taught >=10s minimum.
            http_options=types.HttpOptions(timeout=15000),
        )
        response = client.models.generate_content(
            # A Google-maintained "latest" alias (not a dated string like gemini-2.5-flash) so this
            # keeps working as Google rotates the specific model behind it, and it stays on the
            # free-tier-eligible Flash line -- see README for how to override it.
            model="gemini-flash-latest",
            contents=_build_user_prompt(findings),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                # Deterministic on purpose: this is a factual business report restating numbers
                # already verified in Parts 1-2, not creative writing, so we want the least sampling
                # variance generate_content allows, not creative diversity.
                temperature=0.0,
                # Must be explicit per the brief; >=300 and enough for a ~250-word, 3-section narrative.
                max_output_tokens=500,
            ),
        )
        text = (response.text or "").strip()
        if not text:
            raise ValueError("Gemini API returned an empty response.")

        tokens = None
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            tokens = getattr(usage, "total_token_count", None)

        online_result = {"status": "success", "narrative": text, "tokens": tokens}

    except Exception as err:  # noqa: BLE001 -- the caller must never receive a raw exception
        online_result = {"status": "error", "narrative": None, "message": str(err)}

    if online_result["status"] == "error":
        print(f"[generate_narrative] Online Gemini call failed ({online_result['message']}) -- "
              "using the offline path.")
        return generate_scr_narrative_offline(findings)

    return online_result


# ---------------------------------------------------------------------------
# Task 4: fully deterministic, zero-network, zero-API-key offline path.
# ---------------------------------------------------------------------------
def generate_scr_narrative_offline(findings: dict) -> dict:
    f = findings
    true_peak = f["true_peak_month"]
    inflated = f["outlier_inflated_month"]
    risk = f["highest_risk_segment"]
    rates = f["return_rate_by_payment"]

    narrative = (
        "Situation\n"
        f"Mamaearth's Growth Analytics team closed the books on this order set at Rs.{_money(f['cleaned_total_revenue_inr'])} "
        f"in verified, cleaned revenue, after removing data-entry noise from the raw Rs.{_money(f['raw_total_revenue_inr'])} extract.\n\n"

        "Complication\n"
        f"Two issues are eating into that number. First, a batch of duplicate order submissions inflated the raw "
        f"revenue figure by Rs.{_money(f['duplicate_reconciliation_delta_inr'])} -- a data-quality gap, not real demand -- "
        f"which is why the cleaned total sits below the raw one. Second, and commercially more urgent: returns are "
        f"concentrated, not evenly spread. Cash-on-Delivery (COD) orders return at {rates['COD']}%, versus {rates['CARD']}% "
        f"for Card and {rates['UPI']}% for UPI -- and within COD the risk is not uniform either: {risk['payment_method']} "
        f"orders in city_tier {risk['city_tier']} cities return at {risk['return_rate_pct']}%, the single highest-risk "
        f"segment in the business. Separately, one month that looked like the revenue peak was an artifact: "
        f"{_month_name(inflated['month'])} appeared to lead at Rs.{_money(inflated['apparent_revenue_inr'])}, but once "
        f"two outsized bulk orders are excluded it falls to Rs.{_money(inflated['corrected_revenue_inr'])}, revealing "
        f"{_month_name(true_peak['month'])} as the true peak month at Rs.{_money(true_peak['revenue_inr'])}.\n\n"

        "Resolution\n"
        f"Regional ops should prioritize tightening COD acceptance in city_tier {risk['city_tier']} markets first -- "
        f"that segment alone returns at {risk['return_rate_pct']}%, well above the {rates['COD']}% blended COD rate, so "
        f"a targeted fix (partial prepayment, delivery-time verification, or COD caps on high-return SKUs) will move "
        f"the number further than a blanket COD policy change. Finance should treat the Rs.{_money(f['duplicate_reconciliation_delta_inr'])} "
        f"duplicate-order gap as a checkout/submission bug to fix at the source, not a revenue loss to absorb, and "
        f"should re-baseline monthly targets on {_month_name(true_peak['month'])}'s Rs.{_money(true_peak['revenue_inr'])} "
        f"rather than the outlier-inflated {_month_name(inflated['month'])} figure, so future forecasts are not "
        "anchored to a one-off spike."
    )
    return {"status": "success", "narrative": narrative, "tokens": None}


# ---------------------------------------------------------------------------
# Task 5: numeric accuracy checklist.
# ---------------------------------------------------------------------------
def check_numeric_accuracy(narrative: str) -> bool:
    """Prints a PASS/FAIL line for each of the 5 required figures from the brief and
    returns True only if all 5 are present (verbatim or with equivalent rounding)."""
    normalized = narrative.replace(",", "")
    lower = narrative.lower()

    checks = [
        ("Cleaned total revenue (97,358.30)", ("97358.30" in normalized) or ("97358.3" in normalized)),
        ("COD return rate (44.4)", "44.4" in normalized),
        ("COD + Tier-2 highest-risk segment (54.5)", "54.5" in normalized),
        ("Duplicate reconciliation delta (2,501.90)", ("2501.90" in normalized) or ("2501.9" in normalized)),
        ("True peak month: March + 20,318.90", ("march" in lower) and (("20318.90" in normalized) or ("20318.9" in normalized))),
    ]

    all_pass = True
    for label, passed in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {label}")
    return all_pass


if __name__ == "__main__":
    findings = load_findings()

    print("=" * 78)
    print("Generating SCR narrative (online Gemini if an API key is set, else offline)")
    print("=" * 78)
    result = generate_scr_narrative(findings)
    print(f"status: {result['status']}")
    print(f"tokens: {result.get('tokens')}")
    print("\n--- narrative ---\n")
    print(result["narrative"])

    print("\n" + "=" * 78)
    print("Task 5: numeric accuracy checklist -- this run's narrative")
    print("=" * 78)
    check_numeric_accuracy(result["narrative"])

    sample_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_output.txt")
    if os.path.exists(sample_path):
        print("\n" + "=" * 78)
        print("Task 5: numeric accuracy checklist -- saved narrator/sample_output.txt")
        print("=" * 78)
        with open(sample_path) as f:
            saved_text = f.read()
        passed = check_numeric_accuracy(saved_text)
        print(f"\nOverall: {'PASS' if passed else 'FAIL'}")

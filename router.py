"""
Router: classifies an incoming failed transaction against the decline
code taxonomy, checks the AFA (RBI) constraint, and pulls supporting
context from the RAG layer. This module does NOT decide the final
recovery action or enforce stopping rules — that's the decision agent
(next step). The router's job is purely: "what kind of failure is this,
and what do we know about handling it."
"""

import json
from pathlib import Path

from rag import retrieve

BASE_DIR = Path(__file__).parent
DECLINE_CODES_PATH = BASE_DIR / "decline_codes.json"

_decline_lookup = None


def _load_decline_codes():
    global _decline_lookup
    if _decline_lookup is None:
        data = json.loads(DECLINE_CODES_PATH.read_text())
        _decline_lookup = {c["code"]: c for c in data["decline_codes"]}
    return _decline_lookup


def classify(transaction: dict) -> dict:
    """
    transaction: dict with at least
        decline_code (str), amount (float), attempt_number (int)

    Returns a classification dict:
        category, retry_delay_hours, requires_customer_action,
        afa_required, retrieved_context (list of RAG chunks)
    """
    lookup = _load_decline_codes()
    code = transaction["decline_code"]
    entry = lookup.get(code)

    if entry is None:
        # Unknown/unmapped code — default to a cautious technical_retry
        # with a short delay rather than silently failing. Flagged so
        # it's visible in the audit trail that this was a fallback.
        entry = {
            "code": code,
            "category": "technical_retry",
            "retry_delay_hours": 2,
            "requires_customer_action": False,
            "notes": "Unmapped decline code — defaulted to cautious technical_retry.",
        }

    amount = transaction.get("amount", 0)
    afa_required = amount > 15000  # general recurring-payment AFA-free threshold (RBI, 2026 framework)

    query = f"decline code {code} category {entry['category']} recovery action"
    context = retrieve(query, k=3)

    return {
        "decline_code": code,
        "category": entry["category"],
        "retry_delay_hours": entry.get("retry_delay_hours"),
        "requires_customer_action": entry.get("requires_customer_action", False),
        "afa_required": afa_required,
        "router_path": f"{code} -> {entry['category']}",
        "retrieved_context": context,
        "notes": entry.get("notes", ""),
    }


if __name__ == "__main__":
    # quick manual test against a few sample transactions
    samples = [
        {"decline_code": "card_expired", "amount": 1499, "attempt_number": 1},
        {"decline_code": "insufficient_funds", "amount": 4999, "attempt_number": 1},
        {"decline_code": "bank_technical_error", "amount": 499, "attempt_number": 1},
        {"decline_code": "debit_instrument_blocked", "amount": 14999, "attempt_number": 1},
        {"decline_code": "insufficient_funds", "amount": 49999, "attempt_number": 1},  # AFA case
    ]
    for txn in samples:
        result = classify(txn)
        print(f"\n{txn['decline_code']} (amount={txn['amount']})")
        print(f"  category: {result['category']}")
        print(f"  retry_delay_hours: {result['retry_delay_hours']}")
        print(f"  requires_customer_action: {result['requires_customer_action']}")
        print(f"  afa_required: {result['afa_required']}")
        print(f"  router_path: {result['router_path']}")
        print(f"  top context: [{result['retrieved_context'][0]['source']}/{result['retrieved_context'][0]['title']}]")

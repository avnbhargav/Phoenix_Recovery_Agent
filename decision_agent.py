"""
Decision agent: takes the router's classification of a transaction and
decides the final recovery action, enforcing stopping rules.

This is the layer that actually encodes the "compliant escalation,
stopping rules" requirement from the track brief. It does NOT talk to
the LLM or the database directly — it's a pure decision function so the
logic is easy to test and easy to defend in a panel interview ("here's
exactly why the agent stopped on this transaction").

Rules (rule_version "v1"):
  1. AFA override: if the transaction requires Additional Factor
     Authentication (amount > RBI's AFA-free threshold), NEVER retry
     silently, regardless of decline category. Always notify the
     customer to re-authenticate. This overrides everything else below.
  2. Hard stop: decline categories in HARD_STOP_CATEGORIES are never
     retried, at any attempt number. Escalate immediately.
  3. Customer-action-required: no point retrying (e.g. expired card).
     Action is "notify" — send a comms flow, not a retry.
  4. Retryable categories (technical_retry, customer_retry_delay,
     customer_retry_immediate, limit_based_retry): retry as long as
     attempt_number and elapsed days are within the configured cap.
     Once exceeded, soft-stop and switch to "notify".
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

RULE_VERSION = "v1"

STOPPING_RULES = {
    "max_retries": 4,
    "max_window_days": 14,
}

HARD_STOP_CATEGORIES = {"hard_stop_compliance"}
NOTIFY_ONLY_CATEGORIES = {"customer_action_required"}
RETRYABLE_CATEGORIES = {
    "technical_retry", "customer_retry_delay",
    "customer_retry_immediate", "limit_based_retry",
}


@dataclass
class Decision:
    txn_id: int
    final_action: str            # retry / notify / notify_reauth / escalate / stop
    stopping_reason: str | None
    escalation_flag: bool
    scheduled_at: datetime | None
    reasoning: str
    rule_version: str = RULE_VERSION
    rag_sources_used: list = field(default_factory=list)


def decide(transaction: dict, classification: dict) -> Decision:
    """
    transaction: dict with txn_id, attempt_number, created_at (datetime)
    classification: the dict returned by router.classify()
    """
    txn_id = transaction["txn_id"]
    attempt_number = transaction.get("attempt_number", 1)
    created_at = transaction.get("created_at", datetime.now())
    category = classification["category"]
    afa_required = classification["afa_required"]
    rag_sources = [c["title"] for c in classification.get("retrieved_context", [])]

    # Rule 1: AFA override — always wins, regardless of category
    if afa_required:
        return Decision(
            txn_id=txn_id,
            final_action="notify_reauth",
            stopping_reason=None,
            escalation_flag=False,
            scheduled_at=None,
            reasoning=(
                "Transaction amount exceeds the RBI AFA-free threshold for recurring "
                "payments. Per the 2026 e-mandate framework, this requires fresh "
                "Additional Factor Authentication and cannot be retried silently. "
                "Routing to a re-authentication notification instead of an automatic retry."
            ),
            rag_sources_used=rag_sources,
        )

    # Rule 2: hard stop — fraud/compliance/blocked instrument, never retry
    if category in HARD_STOP_CATEGORIES:
        return Decision(
            txn_id=txn_id,
            final_action="escalate",
            stopping_reason=f"hard_stop:{category}",
            escalation_flag=True,
            scheduled_at=None,
            reasoning=(
                f"Decline category '{category}' indicates a risk/compliance/blocked-instrument "
                "failure. These are never retried automatically — escalating for manual review."
            ),
            rag_sources_used=rag_sources,
        )

    # Rule 3: customer must act — retrying is pointless
    if category in NOTIFY_ONLY_CATEGORIES:
        return Decision(
            txn_id=txn_id,
            final_action="notify",
            stopping_reason=None,
            escalation_flag=False,
            scheduled_at=None,
            reasoning=(
                f"Decline category '{category}' requires the customer to take action "
                "(e.g. update card details). Retrying the same instrument would fail "
                "again, so routing straight to a comms flow instead of a retry."
            ),
            rag_sources_used=rag_sources,
        )

    # Rule 4: retryable categories — check stopping rules before scheduling another retry
    if category in RETRYABLE_CATEGORIES:
        days_elapsed = (datetime.now() - created_at).days
        exceeded_attempts = attempt_number > STOPPING_RULES["max_retries"]
        exceeded_window = days_elapsed > STOPPING_RULES["max_window_days"]

        if exceeded_attempts or exceeded_window:
            reason = "max_retries_exceeded" if exceeded_attempts else "max_window_exceeded"
            return Decision(
                txn_id=txn_id,
                final_action="notify",
                stopping_reason=reason,
                escalation_flag=False,
                scheduled_at=None,
                reasoning=(
                    f"Retry cap reached ({STOPPING_RULES['max_retries']} attempts / "
                    f"{STOPPING_RULES['max_window_days']} days) without recovery. Repeated "
                    "retries beyond this point raise decline rates with the card network "
                    "without materially improving recovery odds. Switching to a customer "
                    "notification instead of continuing to retry."
                ),
                rag_sources_used=rag_sources,
            )

        retry_delay_hours = classification.get("retry_delay_hours") or 1
        scheduled_at = datetime.now() + timedelta(hours=retry_delay_hours)
        return Decision(
            txn_id=txn_id,
            final_action="retry",
            stopping_reason=None,
            escalation_flag=False,
            scheduled_at=scheduled_at,
            reasoning=(
                f"Category '{category}', attempt {attempt_number} of "
                f"{STOPPING_RULES['max_retries']}. Scheduling retry in "
                f"{retry_delay_hours}h per decline-code timing guidance."
            ),
            rag_sources_used=rag_sources,
        )

    # Fallback — shouldn't be reached if router categories are exhaustive, but
    # fail safe rather than fail silent.
    return Decision(
        txn_id=txn_id,
        final_action="escalate",
        stopping_reason="unrecognized_category",
        escalation_flag=True,
        scheduled_at=None,
        reasoning=f"Unrecognized category '{category}' — escalating for manual review rather than guessing.",
        rag_sources_used=rag_sources,
    )


if __name__ == "__main__":
    from router import classify

    test_transactions = [
        {"txn_id": 1, "decline_code": "card_expired", "amount": 1499, "attempt_number": 1, "created_at": datetime.now()},
        {"txn_id": 2, "decline_code": "insufficient_funds", "amount": 4999, "attempt_number": 1, "created_at": datetime.now()},
        {"txn_id": 3, "decline_code": "insufficient_funds", "amount": 4999, "attempt_number": 5, "created_at": datetime.now() - timedelta(days=10)},
        {"txn_id": 4, "decline_code": "debit_instrument_blocked", "amount": 999, "attempt_number": 1, "created_at": datetime.now()},
        {"txn_id": 5, "decline_code": "insufficient_funds", "amount": 49999, "attempt_number": 1, "created_at": datetime.now()},
        {"txn_id": 6, "decline_code": "bank_technical_error", "amount": 499, "attempt_number": 1, "created_at": datetime.now()},
    ]

    for txn in test_transactions:
        classification = classify(txn)
        decision = decide(txn, classification)
        print(f"\ntxn {txn['txn_id']} ({txn['decline_code']}, attempt {txn['attempt_number']}, amount {txn['amount']})")
        print(f"  final_action: {decision.final_action}")
        print(f"  stopping_reason: {decision.stopping_reason}")
        print(f"  escalation_flag: {decision.escalation_flag}")
        print(f"  scheduled_at: {decision.scheduled_at}")
        print(f"  reasoning: {decision.reasoning}")

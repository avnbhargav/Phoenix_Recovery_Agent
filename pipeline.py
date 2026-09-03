"""
Glues router -> decision_agent -> message_drafter -> persistence into one
function for a single transaction. This is what Day 9-10's batch runner
will call in a loop.
"""

from router import classify
from decision_agent import decide
from message_drafter import draft_message
from persistence import record_decision, record_audit_event, record_recovery_action


def process_transaction(transaction: dict, customer: dict) -> dict:
    classification = classify(transaction)
    record_audit_event(transaction["txn_id"], "classified", classification)

    decision = decide(transaction, classification)
    decision_id = record_decision(decision, classification)
    record_audit_event(transaction["txn_id"], "decided", {
        "final_action": decision.final_action,
        "stopping_reason": decision.stopping_reason,
        "escalation_flag": decision.escalation_flag,
    })

    message = None
    if decision.final_action in ("notify", "notify_reauth"):
        message = draft_message(customer, decision, transaction["decline_code"])
        record_audit_event(transaction["txn_id"], "message_drafted", message)

    if decision.final_action == "retry" and decision.scheduled_at:
        record_recovery_action(transaction["txn_id"], "retry", decision.scheduled_at)
    elif decision.final_action in ("notify", "notify_reauth"):
        record_recovery_action(transaction["txn_id"], "email", decision.scheduled_at)

    return {
        "txn_id": transaction["txn_id"],
        "decision_id": decision_id,
        "final_action": decision.final_action,
        "message": message,
    }


if __name__ == "__main__":
    sample_txn = {"txn_id": 101, "decline_code": "card_expired", "amount": 1499, "attempt_number": 1, "created_at": __import__("datetime").datetime.now()}
    sample_customer = {"name": "Rohan", "plan": "Starter"}
    result = process_transaction(sample_txn, sample_customer)
    print("\nPipeline result:", result)

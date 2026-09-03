"""
Persistence layer for Phoenix. Writes to agent_decisions, audit_log, and
recovery_actions per the schema in schema.sql.

If DATABASE_URL isn't set, falls back to a dry-run mode that just prints
what would have been written — lets you test the full pipeline before
a Postgres instance is wired up, and lets a demo keep running even if
the DB connection drops mid-pitch.
"""

import json
import os
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")

_conn = None


def _get_conn():
    global _conn
    if DATABASE_URL is None:
        return None
    if _conn is None:
        import psycopg2
        _conn = psycopg2.connect(DATABASE_URL)
    return _conn


def record_decision(decision, classification: dict) -> int:
    """Writes one row to agent_decisions. Returns the decision_id (or -1 in dry-run)."""
    conn = _get_conn()
    payload = (
        decision.txn_id,
        classification["router_path"],
        json.dumps(decision.rag_sources_used),
        None,  # confidence — reserved for future use if you add a confidence score
        decision.final_action,
        decision.reasoning,
        decision.stopping_reason,
        decision.escalation_flag,
        decision.rule_version,
    )

    if conn is None:
        print(f"[DRY RUN] agent_decisions <- txn={decision.txn_id} action={decision.final_action} "
              f"stopping_reason={decision.stopping_reason} escalation={decision.escalation_flag}")
        return -1

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agent_decisions
                (txn_id, router_path, rag_sources_used, confidence, final_action,
                 reasoning, stopping_reason, escalation_flag, rule_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING decision_id
            """,
            payload,
        )
        decision_id = cur.fetchone()[0]
    conn.commit()
    return decision_id


def record_audit_event(txn_id: int, event_type: str, payload: dict):
    """Writes one immutable row to audit_log."""
    conn = _get_conn()
    if conn is None:
        print(f"[DRY RUN] audit_log <- txn={txn_id} event={event_type} payload={payload}")
        return

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO audit_log (txn_id, event_type, payload_snapshot) VALUES (%s, %s, %s)",
            (txn_id, event_type, json.dumps(payload, default=str)),
        )
    conn.commit()


def record_recovery_action(txn_id: int, action_type: str, scheduled_at: datetime):
    """Writes one row to recovery_actions."""
    conn = _get_conn()
    if conn is None:
        print(f"[DRY RUN] recovery_actions <- txn={txn_id} type={action_type} scheduled_at={scheduled_at}")
        return

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO recovery_actions (txn_id, action_type, scheduled_at) VALUES (%s, %s, %s)",
            (txn_id, action_type, scheduled_at),
        )
    conn.commit()


if __name__ == "__main__":
    from decision_agent import Decision

    fake_decision = Decision(
        txn_id=1, final_action="notify", stopping_reason=None, escalation_flag=False,
        scheduled_at=None, reasoning="test", rag_sources_used=["card_expired"],
    )
    fake_classification = {"router_path": "card_expired -> customer_action_required"}

    record_decision(fake_decision, fake_classification)
    record_audit_event(1, "classified", {"category": "customer_action_required"})
    record_recovery_action(1, "email", datetime.now())

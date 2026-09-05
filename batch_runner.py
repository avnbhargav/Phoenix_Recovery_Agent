"""
Standalone batch runner for submission purposes. Deliberately does NOT
depend on a live database — runs entirely against the CSVs from
generate_data.py, so it works right now regardless of the Supabase auth
issue. Produces:

  - data/batch_results.csv   (per-transaction outcome)
  - data/audit_trail.jsonl   (one JSON line per event, tangible audit artifact)
  - console summary          (the headline recovery-rate number for your pitch)

Outcome simulation is intentionally simple and clearly documented as a
simulation (not a real payment gateway) — grounded in the recovery-rate
benchmarks compiled in best_practices.md, not invented numbers. This is
an honest simplification: it lets you demonstrate the DECISION logic's
value end-to-end without needing real payment rails, which no one
building this in two weeks would have anyway.

Usage:
    python batch_runner.py
"""

import csv
import json
import random
from datetime import datetime
from pathlib import Path

from router import classify
from decision_agent import decide

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# Simulated recovery probability by final_action, grounded in the
# recovery-rate benchmarks in best_practices.md / Stripe dunning research.
# These are SIMULATED outcomes for demo purposes, not real gateway results.
OUTCOME_PROBABILITIES = {
    "retry": 0.60,          # technical/soft declines retried with good timing
    "notify": 0.40,         # customer must act (card update, etc.) — lower but real conversion
    "notify_reauth": 0.50,  # AFA re-authentication flow
    "escalate": 0.0,        # hard stop — never auto-recovered
}


def simulate_outcome(final_action: str, rng: random.Random) -> str:
    prob = OUTCOME_PROBABILITIES.get(final_action, 0.0)
    return "recovered" if rng.random() < prob else "unrecovered"


def run_batch(seed: int = 42) -> dict:
    rng = random.Random(seed)

    transactions_path = DATA_DIR / "transactions.csv"
    if not transactions_path.exists():
        raise FileNotFoundError(f"{transactions_path} not found — run generate_data.py first.")

    results = []
    audit_lines = []

    with open(transactions_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            txn = {
                "txn_id": int(row["txn_id"]),
                "decline_code": row["decline_code"],
                "amount": float(row["amount"]),
                "attempt_number": int(row["attempt_number"]),
                "created_at": datetime.now(),  # freshly "failed" for this simulation run
            }

            classification = classify(txn)
            decision = decide(txn, classification)
            outcome = simulate_outcome(decision.final_action, rng)

            results.append({
                "txn_id": txn["txn_id"],
                "decline_code": txn["decline_code"],
                "amount": txn["amount"],
                "category": classification["category"],
                "final_action": decision.final_action,
                "stopping_reason": decision.stopping_reason,
                "escalation_flag": decision.escalation_flag,
                "outcome": outcome,
            })

            audit_lines.append(json.dumps({
                "txn_id": txn["txn_id"],
                "event_type": "batch_processed",
                "router_path": classification["router_path"],
                "final_action": decision.final_action,
                "reasoning": decision.reasoning,
                "outcome": outcome,
                "timestamp": datetime.now().isoformat(),
            }, default=str))

    # Write per-transaction results
    results_path = DATA_DIR / "batch_results.csv"
    with open(results_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    # Write audit trail
    audit_path = DATA_DIR / "audit_trail.jsonl"
    with open(audit_path, "w", encoding="utf-8") as f:
        f.write("\n".join(audit_lines))

    # Compute headline metrics
    total_txns = len(results)
    total_amount_at_risk = sum(r["amount"] for r in results)
    total_recovered = sum(r["amount"] for r in results if r["outcome"] == "recovered")
    recovery_rate = total_recovered / total_amount_at_risk if total_amount_at_risk else 0

    by_category = {}
    for r in results:
        cat = r["category"]
        by_category.setdefault(cat, {"count": 0, "recovered": 0})
        by_category[cat]["count"] += 1
        if r["outcome"] == "recovered":
            by_category[cat]["recovered"] += 1

    summary = {
        "total_transactions": total_txns,
        "total_amount_at_risk": round(total_amount_at_risk, 2),
        "total_recovered": round(total_recovered, 2),
        "recovery_rate": round(recovery_rate, 4),
        "by_category": by_category,
    }

    print(f"\n{'='*50}")
    print(f"BATCH RUN SUMMARY")
    print(f"{'='*50}")
    print(f"Total transactions:      {summary['total_transactions']}")
    print(f"Total amount at risk:    ₹{summary['total_amount_at_risk']:,.2f}")
    print(f"Total recovered:         ₹{summary['total_recovered']:,.2f}")
    print(f"Recovery rate:           {summary['recovery_rate']*100:.1f}%")
    print(f"\nBreakdown by category:")
    for cat, stats in by_category.items():
        rate = stats["recovered"] / stats["count"] * 100 if stats["count"] else 0
        print(f"  {cat:30s} {stats['recovered']:>4d}/{stats['count']:<4d} ({rate:.1f}%)")
    print(f"\nResults written to:      {results_path}")
    print(f"Audit trail written to:  {audit_path}")

    return summary


if __name__ == "__main__":
    run_batch()

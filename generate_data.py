"""
Phoenix synthetic data generator.

Generates realistic-ish customers and failed-transaction data for the
recovery agent to operate on. Weighting is based on the decline-code
categories in decline_codes.json, roughly matched to the failure-reason
distributions cited in the Stripe dunning research (insufficient funds
and expired cards dominate; technical failures are a meaningful chunk;
hard-stop/fraud is a small but real slice).

No real payment data is used anywhere in this project.

Usage:
    pip install faker pandas
    python generate_data.py --customers 300 --transactions 400 --out ./data
"""

import argparse
import json
import random
from pathlib import Path

import pandas as pd

try:
    from faker import Faker
except ImportError as exc:
    raise RuntimeError(
        "Missing dependency: install requirements with `pip install faker pandas`"
    ) from exc

fake = Faker("en_IN")

# Category -> (weight, list of codes in that category)
# Weights approximate real-world dunning failure distributions.
DECLINE_WEIGHTS = {
    "customer_retry_delay": (0.35, ["insufficient_funds"]),
    "customer_action_required": (0.25, [
        "card_expired", "card_number_invalid", "bank_account_invalid",
        "incorrect_cvv", "incorrect_otp", "invalid_vpa",
        "user_not_registered_for_netbanking",
    ]),
    "technical_retry": (0.20, [
        "bank_technical_error", "gateway_technical_error", "bank_not_available",
        "server_error", "issuer_technical_error", "upi_app_technical_error",
        "request_timed_out",
    ]),
    "limit_based_retry": (0.08, [
        "transaction_daily_limit_exceeded", "transaction_frequency_limit_exceeded",
        "otp_attempts_exceeded",
    ]),
    "hard_stop_compliance": (0.07, [
        "debit_instrument_blocked", "payment_risk_check_failed",
        "compliance_violation", "card_declined",
    ]),
    "customer_retry_immediate": (0.05, [
        "authentication_failed", "payment_cancelled", "payment_timed_out",
    ]),
}

PAYMENT_METHODS = ["card", "upi", "netbanking", "wallet"]
PLANS = [
    ("Starter", 499), ("Growth", 1499), ("Pro", 4999),
    ("Business", 14999), ("Enterprise", 49999),
]

AFA_FREE_LIMIT_GENERAL = 15000
AFA_FREE_LIMIT_DESIGNATED = 100000  # insurance/mutual funds/credit card bills — not modeled here, using general limit


def weighted_decline_code() -> str:
    categories = list(DECLINE_WEIGHTS.keys())
    weights = [DECLINE_WEIGHTS[c][0] for c in categories]
    category = random.choices(categories, weights=weights, k=1)[0]
    return random.choice(DECLINE_WEIGHTS[category][1])


def generate_customers(n: int) -> pd.DataFrame:
    rows = []
    for i in range(1, n + 1):
        plan, mrr = random.choice(PLANS)
        tenure = random.randint(1, 900)
        # crude LTV segmentation from tenure + plan value
        if mrr >= 14999 or tenure > 400:
            segment = "high"
        elif mrr >= 1499 or tenure > 100:
            segment = "medium"
        else:
            segment = "low"
        rows.append({
            "customer_id": i,
            "name": fake.name(),
            "email": fake.email(),
            "phone": fake.phone_number(),
            "plan": plan,
            "mrr": mrr,
            "tenure_days": tenure,
            "ltv_segment": segment,
        })
    return pd.DataFrame(rows)


def generate_transactions(n: int, customers: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for i in range(1, n + 1):
        cust = customers.sample(1).iloc[0]
        decline_code = weighted_decline_code()
        amount = float(cust["mrr"])
        afa_required = amount > AFA_FREE_LIMIT_GENERAL
        rows.append({
            "txn_id": i,
            "customer_id": int(cust["customer_id"]),
            "amount": amount,
            "currency": "INR",
            "decline_code": decline_code,
            "payment_method": random.choice(PAYMENT_METHODS),
            "attempt_number": 1,
            "status": "failed",
            "afa_required": afa_required,
        })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--customers", type=int, default=300)
    parser.add_argument("--transactions", type=int, default=400)
    parser.add_argument("--out", type=str, default="./data")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    Faker.seed(args.seed)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    customers = generate_customers(args.customers)
    transactions = generate_transactions(args.transactions, customers)

    customers.to_csv(out_dir / "customers.csv", index=False)
    transactions.to_csv(out_dir / "transactions.csv", index=False)

    print(f"Generated {len(customers)} customers -> {out_dir / 'customers.csv'}")
    print(f"Generated {len(transactions)} transactions -> {out_dir / 'transactions.csv'}")
    print("\nDecline code distribution:")
    print(transactions["decline_code"].value_counts())


if __name__ == "__main__":
    main()

"""
One-time (or repeatable) seed script. Loads:
  - decline_codes.json  -> decline_codes table
  - data/customers.csv  -> customers table
  - data/transactions.csv -> transactions table

Run generate_data.py first to produce the CSVs.

Usage:
    python seed_db.py
"""

import json
import os
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set — check your .env file.")
    return psycopg2.connect(DATABASE_URL)


def seed_decline_codes(conn):
    data = json.loads((BASE_DIR / "decline_codes.json").read_text(encoding="utf-8"))
    codes = data["decline_codes"]

    with conn.cursor() as cur:
        for entry in codes:
            cur.execute(
                """
                INSERT INTO decline_codes (code, category, retry_delay_hours, requires_customer_action, notes)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (code) DO UPDATE SET
                    category = EXCLUDED.category,
                    retry_delay_hours = EXCLUDED.retry_delay_hours,
                    requires_customer_action = EXCLUDED.requires_customer_action,
                    notes = EXCLUDED.notes
                """,
                (
                    entry["code"],
                    entry["category"],
                    entry.get("retry_delay_hours"),
                    entry.get("requires_customer_action", False),
                    entry.get("notes", ""),
                ),
            )
    conn.commit()
    print(f"Seeded {len(codes)} decline codes.")


def seed_customers(conn):
    path = DATA_DIR / "customers.csv"
    if not path.exists():
        print(f"Skipping customers — {path} not found. Run generate_data.py first.")
        return

    df = pd.read_csv(path)
    with conn.cursor() as cur:
        for _, row in df.iterrows():
            cur.execute(
                """
                INSERT INTO customers (customer_id, name, email, phone, plan, mrr, tenure_days, ltv_segment)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (customer_id) DO NOTHING
                """,
                (
                    int(row["customer_id"]), row["name"], row["email"], row["phone"],
                    row["plan"], float(row["mrr"]), int(row["tenure_days"]), row["ltv_segment"],
                ),
            )
    conn.commit()
    print(f"Seeded {len(df)} customers.")

    # Reset the serial sequence so future INSERTs (without explicit customer_id) don't collide
    with conn.cursor() as cur:
        cur.execute("SELECT setval('customers_customer_id_seq', (SELECT MAX(customer_id) FROM customers))")
    conn.commit()


def seed_transactions(conn):
    path = DATA_DIR / "transactions.csv"
    if not path.exists():
        print(f"Skipping transactions — {path} not found. Run generate_data.py first.")
        return

    df = pd.read_csv(path)
    with conn.cursor() as cur:
        for _, row in df.iterrows():
            cur.execute(
                """
                INSERT INTO transactions
                    (txn_id, customer_id, amount, currency, decline_code, payment_method,
                     attempt_number, status, afa_required)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (txn_id) DO NOTHING
                """,
                (
                    int(row["txn_id"]), int(row["customer_id"]), float(row["amount"]),
                    row["currency"], row["decline_code"], row["payment_method"],
                    int(row["attempt_number"]), row["status"], bool(row["afa_required"]),
                ),
            )
    conn.commit()
    print(f"Seeded {len(df)} transactions.")

    with conn.cursor() as cur:
        cur.execute("SELECT setval('transactions_txn_id_seq', (SELECT MAX(txn_id) FROM transactions))")
    conn.commit()


def main():
    conn = get_conn()
    try:
        seed_decline_codes(conn)
        seed_customers(conn)
        seed_transactions(conn)
    finally:
        conn.close()
    print("\nSeeding complete.")


if __name__ == "__main__":
    main()

# Phoenix — Agentic AI Revenue Recovery Engine

**Razorpay AI Buildathon — Track 03: AI Revenue Recovery**

> Find revenue that's slipping away and win it back.

## What it does

Phoenix is an agent that detects at-risk revenue from failed recurring payments, diagnoses why each payment failed, decides the right recovery action, and executes a bounded recovery workflow — with compliant stopping rules and a full audit trail.

Unlike a blanket "retry after 24 hours" policy, Phoenix routes each failure differently based on its actual cause: a technical bank glitch gets retried within the hour, an expired card gets a comms flow instead of a wasted retry, insufficient funds gets retried after a payday-aware delay, and fraud/compliance-flagged failures are stopped immediately and escalated — never retried.

## The problem

A significant share of subscription churn is involuntary — the customer didn't choose to leave, their payment just failed and nobody handled it well. Treating every failure the same way either wastes retry attempts on unrecoverable cases or under-reacts to cases that would have recovered with the right timing and message.

## Results

Run on a batch of 400 synthetic failed transactions:

| Metric | Value |
|---|---|
| Total amount at risk | ₹53.2L |
| Total recovered | ₹26.7L |
| **Recovery rate** | **~50%** |
| Hard-stop / compliance category recovery | 0% (by design — never retried) |

The 50% figure sits in line with published dunning benchmarks for "smart retries + segmented notifications" systems (before adding a card-update page, which typically pushes recovery further). See `data/batch_results.csv` for the per-transaction breakdown and `data/audit_trail.jsonl` for the full decision-by-decision audit trail.

Reproduce with:
```bash
python generate_data.py --customers 300 --transactions 400
python build_index.py
python batch_runner.py
```

## Architecture

```
Failed transaction
      │
      ▼
 ┌─────────────┐     ┌──────────────────┐
 │   Router     │────▶│  RAG (FAISS)      │  decline-code taxonomy +
 │ (classify    │     │  retrieval layer  │  recovery best practices
 │  failure)    │     └──────────────────┘
      │
      ▼
 ┌─────────────────────┐
 │  Decision Agent       │  retry / notify / notify_reauth / escalate
 │  + stopping rules     │  (compliance-aware: RBI AFA thresholds)
 └─────────────────────┘
      │
      ▼
 ┌─────────────────────┐     ┌──────────────┐
 │  Message drafter      │────▶│ audit_log     │  every state change,
 │  (LLM, template       │     │ (append-only) │  immutable
 │  fallback)             │     └──────────────┘
 └─────────────────────┘
      │
      ▼
 ┌─────────────────────┐
 │  Batch metrics         │  recovery rate, ₹ recovered, per-category breakdown
 └─────────────────────┘
```

Note: classification and the retry/escalate/stop decision are deterministic, rule-based logic — not LLM calls. The LLM is scoped narrowly to drafting the customer-facing message, with a template fallback so the pipeline works even without an API key. In a compliance-sensitive domain, every "should this retry" decision needs to be explainable without interpreting a model's reasoning.

## Compliance & stopping rules

- **Retry cap:** max 4 attempts over 14 days for soft/technical declines (source: Stripe dunning benchmarks — beyond this, retry attempts increase decline rates with card networks).
- **Hard stop:** fraud-flagged, compliance-violation, and blocked-instrument declines are never retried — routed straight to escalation. This check runs *before* every other rule, including the AFA check below, so a fraud flag always wins regardless of transaction amount.
- **AFA-aware routing:** recurring transactions above ₹15,000 (₹1,00,000 for insurance/mutual funds/credit card bills) require fresh Additional Factor Authentication per the RBI e-Mandate Framework — these are never silently auto-retried; the agent always routes them to a re-authentication notification instead.
- **Audit trail:** every decision the agent makes is logged as an immutable event, independent of the final-decision table, so any transaction can be traced end-to-end.

## Tech stack

- **Backend:** FastAPI
- **Orchestration:** custom router/decision-function pattern (deliberately not LLM-driven — see Architecture note above)
- **RAG:** FAISS + sentence-transformers
- **LLM:** provider-abstracted (Groq primary), used only for message drafting
- **Database:** PostgreSQL (schema in `schema.sql`; pipeline also runs in a dry-run mode without a DB connection)
- **Data:** fully synthetic, generated via `generate_data.py` — no real payment data is used anywhere in this project

## Setup

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

python generate_data.py --customers 300 --transactions 400
python build_index.py
python batch_runner.py       # headline recovery-rate metric
python decision_agent.py     # standalone stopping-rule test cases
```

Optional — to run against a live Postgres instance instead of dry-run mode, set `DATABASE_URL` in a `.env` file, run `schema.sql` against it, then `python seed_db.py`.

## What's built vs. not (honest scope for a ~2-week build)

**Built and tested:** router, RAG retrieval, decision agent with stopping rules, message drafter, audit logging, batch runner with recovery-rate metrics, Postgres schema and seed pipeline.

**Not completed in this window:** a live dashboard UI and cloud deployment. Given the timeline, priority went to the decision logic and compliance handling itself, since that's the part this track is actually evaluating — the metrics above come from the batch runner's console/CSV output rather than a rendered dashboard.

## Data sources / research

- Razorpay error/decline code reference
- Stripe dunning management benchmarks
- RBI Digital Payments — E-Mandate Framework (AFA thresholds)

## Pitch video

[link here]

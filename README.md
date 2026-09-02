# Phoenix — Agentic AI Revenue Recovery Engine

**Razorpay AI Buildathon — Track 03: AI Revenue Recovery**

> Find revenue that's slipping away and win it back.

## What it does

Phoenix is an agent that detects at-risk revenue from failed recurring payments, diagnoses *why* each payment failed, decides the right recovery action, and executes a bounded recovery workflow — with compliant stopping rules and a full audit trail.

Unlike a blanket "retry after 24 hours" policy, Phoenix routes each failure differently based on its actual cause: a technical bank glitch gets retried within the hour, an expired card gets a comms flow instead of a wasted retry, insufficient funds gets retried after a payday-aware delay, and fraud/compliance-flagged failures are stopped immediately and escalated — never retried.

## The problem

A significant share of subscription churn is *involuntary* — the customer didn't choose to leave, their payment just failed and nobody handled it well. Treating every failure the same way either wastes retry attempts on unrecoverable cases or under-reacts to cases that would have recovered with the right timing and message.

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
 │  Decision Agent       │  retry / notify / escalate / stop
 │  + stopping rules     │  (compliance-aware: RBI AFA thresholds)
 └─────────────────────┘
      │
      ▼
 ┌─────────────────────┐     ┌──────────────┐
 │  Action execution     │────▶│ audit_log     │  every state change,
 │  (simulated gateway)  │     │ (append-only) │  immutable
 └─────────────────────┘     └──────────────┘
      │
      ▼
 ┌─────────────────────┐
 │  batch_runs metrics    │  recovery rate, ₹ recovered, time-to-recovery
 └─────────────────────┘
```

*(Diagram to be replaced with a proper architecture image before submission.)*

## Compliance & stopping rules

- **Retry cap:** max 4 attempts over 14 days for soft/technical declines (source: Stripe dunning benchmarks — beyond this, retry attempts increase decline rates with card networks).
- **Hard stop:** fraud-flagged, compliance-violation, and blocked-instrument declines are never retried — routed straight to escalation.
- **AFA-aware routing:** recurring transactions above ₹15,000 (₹1,00,000 for insurance/mutual funds/credit card bills) require fresh Additional Factor Authentication per the RBI e-Mandate Framework — these are never silently auto-retried; the agent always routes them to a re-authentication notification instead.
- **Audit trail:** every decision the agent makes is logged as an immutable event, independent of the final-decision table, so any transaction can be traced end-to-end.

## Tech stack

- **Backend:** FastAPI
- **Orchestration:** custom router/decision-function pattern
- **RAG:** FAISS + sentence-transformers
- **LLM:** provider-abstracted (Groq primary, OpenAI/Anthropic fallback)
- **Database:** PostgreSQL
- **Scheduling:** APScheduler
- **Dashboard:** TBD (Streamlit or Next.js)

## Status

🚧 In active development for the Razorpay AI Buildathon (submission deadline: Sept 5, 2026).

## Data sources / research

- Razorpay error/decline code reference
- Stripe dunning management benchmarks
- RBI Digital Payments — E-Mandate Framework (AFA thresholds)

All data used in this project (transactions, customers) is synthetically generated; no real payment data is used.

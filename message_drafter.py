"""
Drafts the customer-facing message for a given decision. Uses an LLM
when an API key is configured (Groq by default — fast, generous free
tier), and falls back to a plain template otherwise so the pipeline
never breaks in a demo just because a key isn't set.

This is deliberately the ONLY place in Phoenix that calls an LLM.
Classification (router.py) and the decision logic (decision_agent.py)
are both fast, deterministic, and explainable without one — the LLM is
reserved for the one sub-task that genuinely benefits from generation:
writing a message in the right tone.
"""

import os

TEMPLATES = {
    "notify": (
        "Hi {name}, quick heads-up — we couldn't process your payment for "
        "your {plan} subscription. This usually happens because {reason}. "
        "You can update your payment details here: [update link]."
    ),
    "notify_reauth": (
        "Hi {name}, your recent payment for {plan} needs a quick "
        "re-authentication step before we can complete it — this is a "
        "one-time security check for larger recurring payments. "
        "Please confirm here: [reauth link]."
    ),
    "escalate": None,  # escalations go to an internal queue, not a customer message
}

FRIENDLY_REASONS = {
    "card_expired": "your card on file has expired",
    "card_number_invalid": "there was an issue with your card details",
    "bank_account_invalid": "there was an issue with your linked bank account",
    "incorrect_cvv": "the card verification code didn't match",
    "incorrect_otp": "the one-time password didn't go through in time",
    "invalid_vpa": "there was an issue with your UPI ID",
}


def _template_fallback(customer: dict, decision, decline_code: str) -> str:
    template = TEMPLATES.get(decision.final_action)
    if template is None:
        return "[Internal escalation — no customer-facing message for this action]"
    reason = FRIENDLY_REASONS.get(decline_code, "a temporary issue with the payment")
    return template.format(name=customer.get("name", "there"), plan=customer.get("plan", "subscription"), reason=reason)


def draft_message(customer: dict, decision, decline_code: str) -> dict:
    """
    Returns {"text": str, "source": "llm" | "template"}
    """
    api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        return {"text": _template_fallback(customer, decision, decline_code), "source": "template"}

    try:
        from groq import Groq  # imported lazily so the package is optional until a key is set
        client = Groq(api_key=api_key)

        prompt = (
            f"Write a short, friendly SMS/email message (2-3 sentences) to a customer "
            f"named {customer.get('name', 'there')} on the {customer.get('plan', 'subscription')} plan. "
            f"Their recurring payment failed because: {decision.reasoning}\n"
            f"Action being taken: {decision.final_action}.\n"
            f"Tone: helpful heads-up, not a collections notice. No subject line, just the message body."
        )
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
        )
        return {"text": response.choices[0].message.content.strip(), "source": "llm"}
    except Exception as e:
        # never let a flaky API call break the recovery pipeline — fall back silently to template
        return {"text": _template_fallback(customer, decision, decline_code), "source": f"template (llm_error: {e})"}


if __name__ == "__main__":
    from decision_agent import Decision

    fake_customer = {"name": "Priya", "plan": "Growth"}
    fake_decision = Decision(
        txn_id=1, final_action="notify", stopping_reason=None, escalation_flag=False,
        scheduled_at=None, reasoning="Card expired, needs update.",
    )
    result = draft_message(fake_customer, fake_decision, "card_expired")
    print(f"[{result['source']}]\n{result['text']}")

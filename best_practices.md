# Recovery Best Practices — Knowledge Base

This document is the RAG source for Phoenix's decision agent. It is chunked
and embedded so the agent can retrieve the relevant reasoning when deciding
how to handle a specific failed transaction. Each section is written to
stand alone as a retrievable chunk.

## Retry timing by failure type

Technical and gateway-side failures (bank server errors, timeouts, high
gateway traffic) are usually transient and resolve on their own. These
should be retried soon — within one to a few hours — since the underlying
system issue is unlikely to still be present, and there is no reason to
make the customer wait.

Insufficient-funds failures behave differently. Retrying immediately after
an insufficient-funds decline is usually pointless, since the account
balance hasn't had time to change. The recommended delay is two to three
days, ideally timed around when the customer is likely to be paid — an
immediate retry wastes an attempt, while a well-timed one has meaningfully
better odds.

Card-expired and similar customer-fixable failures should never be
retried as-is. Retrying the same expired card will fail every time no
matter how many attempts are made or how long the delay is. These cases
need a different kind of action entirely: a direct request to the
customer to update their payment details, not a silent retry.

## Retry caps and network health

Retrying a declined transaction repeatedly does not raise the eventual
success rate in proportion to the number of attempts — instead, a high
volume of repeated declines on the same instrument raises the account's
decline rate with the card network, which can lead to higher processing
fees or account-level flags from the network itself. For this reason,
retry attempts should be capped, generally at around four to six attempts
spread over a fourteen-to-twenty-one-day window. Once that cap is reached
without success, the transaction should stop retrying and move to a
different kind of recovery action (customer communication) or be marked
as unrecoverable.

## Communication timing and tone

The single biggest jump in recovery rate comes not from retries but from
timely, well-targeted customer communication. A message sent within about
two hours of a failure recovers meaningfully more often than one sent
even a few days later — engagement drops off quickly as time passes.

Messages should be segmented by the actual failure reason rather than
generic. A message referencing the specific problem (for example, that a
card has expired) is far more actionable to a customer than a vague
notice that a payment "could not be processed."

Tone matters as much as timing. The customer did not choose to cancel —
their payment failed for a reason outside their control in most cases.
The first message in any sequence should read as a helpful heads-up, not
as a collections notice. Escalating language ("action required," "your
access will be paused") should be reserved for later messages in a
sequence, not the first one, since an aggressive first contact damages
the relationship without improving recovery odds.

A typical escalation sequence spans about two weeks: an initial friendly
notice within hours of failure, a gentle reminder a few days later, a
message stating a clear deadline roughly a week in, and a final notice
shortly before the grace period ends.

## Grace periods

Cancelling access immediately on the first failed payment is unnecessarily
harsh, since the same payment method may succeed on the very next attempt.
A short grace period — roughly one to two weeks of continued access — gives
recovery actions time to work before any access is paused, while still
setting a clear endpoint so recovery doesn't drag on indefinitely.

## When not to retry at all

Some failures should never be retried automatically, regardless of how
much time has passed. Failures tied to risk checks, compliance flags, or
a blocked/restricted instrument indicate the transaction was stopped for
a reason beyond simple payment friction — repeatedly attempting to charge
a flagged instrument does not improve outcomes and can itself create
compliance exposure. These cases should be stopped immediately (zero
retries) and routed to escalation rather than treated as a normal
recoverable failure.

## Regulatory constraint on retries (India-specific)

Recurring payments above a certain value require fresh authentication
(Additional Factor Authentication) under RBI's e-mandate framework — the
authentication requirement is only waived for smaller recurring amounts.
This means that for higher-value recurring transactions, a failed payment
cannot simply be retried silently in the background; the customer must
be brought back through an authentication step. Any recovery action for a
transaction above this threshold should default to a customer
notification requesting re-authentication rather than an automatic retry,
regardless of what the decline code alone would otherwise suggest.

## What to track

Recovery rate should be measured by decline-code category, not just in
aggregate — an overall recovery rate can look reasonable while masking
that one entire category (for example, expired cards) is being recovered
far less often than others. Time-to-recovery is also worth tracking
separately, since it indicates whether a grace period is well-calibrated:
if the large majority of recoveries happen in the first few days, an
unnecessarily long grace period is just delaying certainty for both sides
without improving outcomes.

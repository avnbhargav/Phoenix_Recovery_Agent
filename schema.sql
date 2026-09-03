-- Phoenix schema
-- Postgres 14+

CREATE TABLE customers (
    customer_id     SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT NOT NULL,
    phone           TEXT,
    plan            TEXT NOT NULL,
    mrr             NUMERIC(10,2) NOT NULL,
    tenure_days     INTEGER NOT NULL,
    ltv_segment     TEXT NOT NULL CHECK (ltv_segment IN ('high', 'medium', 'low')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE decline_codes (
    code                        TEXT PRIMARY KEY,
    category                    TEXT NOT NULL CHECK (category IN (
                                    'technical_retry', 'customer_retry_delay',
                                    'customer_retry_immediate', 'customer_action_required',
                                    'limit_based_retry', 'hard_stop_compliance'
                                )),
    retry_delay_hours           INTEGER,               -- NULL = do not retry
    requires_customer_action    BOOLEAN NOT NULL,
    notes                       TEXT
);

CREATE TABLE transactions (
    txn_id           SERIAL PRIMARY KEY,
    customer_id      INTEGER NOT NULL REFERENCES customers(customer_id),
    amount           NUMERIC(10,2) NOT NULL,
    currency         TEXT NOT NULL DEFAULT 'INR',
    decline_code     TEXT REFERENCES decline_codes(code),
    payment_method   TEXT NOT NULL,
    attempt_number   INTEGER NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'failed' CHECK (status IN (
                        'failed', 'retrying', 'recovered', 'abandoned', 'escalated'
                     )),
    afa_required     BOOLEAN NOT NULL DEFAULT false,   -- true if amount exceeds RBI AFA-free threshold
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_transactions_customer ON transactions(customer_id);
CREATE INDEX idx_transactions_decline_code ON transactions(decline_code);
CREATE INDEX idx_transactions_status ON transactions(status);

CREATE TABLE agent_decisions (
    decision_id       SERIAL PRIMARY KEY,
    txn_id            INTEGER NOT NULL REFERENCES transactions(txn_id),
    router_path       TEXT NOT NULL,        -- e.g. "insufficient_funds -> customer_retry_delay"
    rag_sources_used  JSONB,                -- which knowledge-base chunks were retrieved
    confidence        NUMERIC(4,3),
    final_action       TEXT NOT NULL,        -- retry / notify / escalate / stop
    reasoning         TEXT,
    stopping_reason   TEXT,                 -- NULL unless the agent decided to stop
    escalation_flag   BOOLEAN NOT NULL DEFAULT false,
    rule_version      TEXT NOT NULL DEFAULT 'v1',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_agent_decisions_txn ON agent_decisions(txn_id);

CREATE TABLE audit_log (
    log_id            SERIAL PRIMARY KEY,
    txn_id            INTEGER NOT NULL REFERENCES transactions(txn_id),
    event_type        TEXT NOT NULL,        -- classified / retry_scheduled / message_sent / outcome_recorded / stopped / escalated
    payload_snapshot  JSONB NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_log_txn ON audit_log(txn_id);

CREATE TABLE recovery_actions (
    action_id     SERIAL PRIMARY KEY,
    txn_id        INTEGER NOT NULL REFERENCES transactions(txn_id),
    action_type   TEXT NOT NULL CHECK (action_type IN (
                    'retry', 'email', 'sms', 'whatsapp', 'escalate'
                  )),
    scheduled_at  TIMESTAMPTZ NOT NULL,
    executed_at   TIMESTAMPTZ,
    outcome       TEXT CHECK (outcome IN ('success', 'failure', 'pending', NULL)),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_recovery_actions_txn ON recovery_actions(txn_id);

CREATE TABLE batch_runs (
    batch_id                SERIAL PRIMARY KEY,
    run_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_transactions      INTEGER NOT NULL,
    total_amount_at_risk    NUMERIC(12,2) NOT NULL,
    total_recovered         NUMERIC(12,2) NOT NULL,
    recovery_rate           NUMERIC(5,4) NOT NULL,   -- e.g. 0.6500 = 65%
    avg_time_to_recovery_hours NUMERIC(8,2)
);

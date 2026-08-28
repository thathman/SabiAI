-- Strategy runs are persisted separately from the pick ledger so an observation
-- never becomes a pick merely because a model mentioned it.
ALTER TABLE picks_v2 ADD COLUMN owner TEXT NOT NULL DEFAULT 'sabi_boy';
ALTER TABLE picks_v2 ADD COLUMN record_kind TEXT NOT NULL DEFAULT 'pick';
ALTER TABLE picks_v2 ADD COLUMN strategy_code TEXT;
ALTER TABLE picks_v2 ADD COLUMN source_run_id TEXT;
ALTER TABLE picks_v2 ADD COLUMN model_generation TEXT;

CREATE INDEX IF NOT EXISTS idx_picks_owner_kind
    ON picks_v2(owner, record_kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_picks_strategy_code
    ON picks_v2(strategy_code, outcome, created_at DESC);

ALTER TABLE daily_research_runs ADD COLUMN strategy_plans_json TEXT NOT NULL DEFAULT '[]';

CREATE TABLE IF NOT EXISTS strategy_plans (
    id TEXT PRIMARY KEY,
    strategy_code TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    target_odds TEXT,
    combined_odds TEXT,
    suggested_stake TEXT,
    confidence_pct REAL,
    rationale TEXT NOT NULL DEFAULT '',
    candidate_count INTEGER NOT NULL DEFAULT 0,
    candidates_json TEXT NOT NULL DEFAULT '[]',
    source_run_id TEXT,
    generated_at TEXT NOT NULL,
    expires_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_strategy_plans_latest
    ON strategy_plans(generated_at DESC, strategy_code);
CREATE INDEX IF NOT EXISTS idx_strategy_plans_strategy
    ON strategy_plans(strategy_code, generated_at DESC);

-- The daily 1.30 strategy is a 30-day progression, not a fresh one-day stake.
ALTER TABLE strategy_plans ADD COLUMN chain_json TEXT NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS strategy_chain_state (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL DEFAULT 'sabi_boy',
    strategy_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    target_days INTEGER NOT NULL DEFAULT 30,
    target_odds TEXT NOT NULL DEFAULT '1.30',
    starting_stake TEXT NOT NULL DEFAULT '1000.00',
    current_stake TEXT NOT NULL DEFAULT '1000.00',
    completed_days INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ready',
    active_ticket_id TEXT,
    last_outcome TEXT,
    last_settled_at TEXT,
    cycle_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO strategy_chain_state(
    id,owner,strategy_code,name,target_days,target_odds,starting_stake,current_stake,status
) VALUES(
    'sabi_boy_daily_chain_1_30','sabi_boy','daily_chain_1_30',
    'Daily 1.30 Chain',30,'1.30','1000.00','1000.00','ready'
);

CREATE INDEX IF NOT EXISTS idx_strategy_chain_owner_status
    ON strategy_chain_state(owner, status, updated_at DESC);

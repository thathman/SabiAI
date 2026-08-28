ALTER TABLE tickets ADD COLUMN owner TEXT NOT NULL DEFAULT 'sabi_boy';
ALTER TABLE tickets ADD COLUMN strategy_code TEXT;
CREATE INDEX IF NOT EXISTS idx_tickets_owner_strategy
    ON tickets(owner, strategy_code, created_at DESC);

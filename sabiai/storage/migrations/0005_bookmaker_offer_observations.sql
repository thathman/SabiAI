CREATE TABLE IF NOT EXISTS bookmaker_offer_observations (
    id TEXT PRIMARY KEY,
    target_bookmaker_slug TEXT NOT NULL,
    sport TEXT,
    event TEXT NOT NULL,
    home TEXT,
    away TEXT,
    event_ref TEXT,
    market TEXT NOT NULL,
    market_ref TEXT,
    decimal_odds TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL,
    source_draft_id TEXT REFERENCES ticket_drafts(id),
    raw_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_bookmaker_offer_observed
    ON bookmaker_offer_observations(target_bookmaker_slug, observed_at);

CREATE INDEX IF NOT EXISTS idx_bookmaker_offer_event
    ON bookmaker_offer_observations(target_bookmaker_slug, event, market);

CREATE INDEX IF NOT EXISTS idx_bookmaker_offer_draft
    ON bookmaker_offer_observations(source_draft_id);

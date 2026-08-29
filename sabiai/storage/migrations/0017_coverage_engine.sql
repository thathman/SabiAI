-- V2.4 coverage engine: canonical discovery universe + market inventory.

CREATE TABLE IF NOT EXISTS coverage_events (
    id TEXT PRIMARY KEY,
    sport TEXT NOT NULL,
    competition TEXT,
    country TEXT,
    division TEXT,
    event_name TEXT NOT NULL,
    home TEXT,
    away TEXT,
    starts_at TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled',
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_coverage_events_start ON coverage_events(starts_at);
CREATE INDEX IF NOT EXISTS idx_coverage_events_sport_start ON coverage_events(sport, starts_at);

CREATE TABLE IF NOT EXISTS coverage_event_sources (
    event_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_event_id TEXT,
    provider_sport_key TEXT,
    source_event_name TEXT,
    source_payload_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(event_id, source_name),
    FOREIGN KEY(event_id) REFERENCES coverage_events(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_coverage_event_sources_provider ON coverage_event_sources(source_name, source_event_id);

CREATE TABLE IF NOT EXISTS coverage_market_catalogue (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    bookmaker TEXT,
    source_market_key TEXT,
    source_market_id TEXT,
    family TEXT NOT NULL,
    metric TEXT,
    period TEXT,
    participant TEXT,
    line REAL,
    market_label TEXT NOT NULL,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(event_id) REFERENCES coverage_events(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_coverage_market_catalogue_event ON coverage_market_catalogue(event_id);
CREATE INDEX IF NOT EXISTS idx_coverage_market_catalogue_family ON coverage_market_catalogue(family);

CREATE TABLE IF NOT EXISTS coverage_market_offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    catalogue_id TEXT,
    source_name TEXT NOT NULL,
    bookmaker TEXT,
    source_market_key TEXT,
    source_market_id TEXT,
    source_outcome_id TEXT,
    family TEXT NOT NULL,
    metric TEXT,
    period TEXT,
    participant TEXT,
    side TEXT,
    line REAL,
    selection_label TEXT NOT NULL,
    decimal_odds REAL NOT NULL CHECK(decimal_odds > 1.0),
    observed_at TEXT NOT NULL,
    source_last_update TEXT,
    rule_fingerprint TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(event_id) REFERENCES coverage_events(id) ON DELETE CASCADE,
    FOREIGN KEY(catalogue_id) REFERENCES coverage_market_catalogue(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_coverage_market_offers_event_time ON coverage_market_offers(event_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_coverage_market_offers_family_time ON coverage_market_offers(family, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_coverage_market_offers_bookmaker_time ON coverage_market_offers(bookmaker, observed_at DESC);

CREATE TABLE IF NOT EXISTS coverage_discovery_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    horizon_hours INTEGER NOT NULL,
    sports_requested INTEGER NOT NULL DEFAULT 0,
    source_attempts INTEGER NOT NULL DEFAULT 0,
    source_successes INTEGER NOT NULL DEFAULT 0,
    source_failures INTEGER NOT NULL DEFAULT 0,
    events_seen INTEGER NOT NULL DEFAULT 0,
    canonical_events INTEGER NOT NULL DEFAULT 0,
    priced_events INTEGER NOT NULL DEFAULT 0,
    market_catalogue_count INTEGER NOT NULL DEFAULT 0,
    market_offer_count INTEGER NOT NULL DEFAULT 0,
    prefiltered_events INTEGER NOT NULL DEFAULT 0,
    researched_events INTEGER NOT NULL DEFAULT 0,
    selected_recommendations INTEGER NOT NULL DEFAULT 0,
    details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_coverage_discovery_runs_started ON coverage_discovery_runs(started_at DESC);

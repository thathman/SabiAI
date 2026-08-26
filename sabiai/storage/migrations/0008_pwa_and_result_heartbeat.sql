CREATE TABLE IF NOT EXISTS push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL UNIQUE,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    user_agent TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    disabled_at TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_success_at TEXT,
    last_error_at TEXT,
    last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_push_subscriptions_active
    ON push_subscriptions(disabled_at, updated_at);

CREATE TABLE IF NOT EXISTS event_result_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    status TEXT NOT NULL,
    home_score TEXT,
    away_score TEXT,
    observed_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, source_name, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_event_result_latest
    ON event_result_observations(event_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS source_cache (
    cache_key TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    sport TEXT,
    capability TEXT,
    payload_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    source_observed_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_source_cache_expiry ON source_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_source_cache_source ON source_cache(source_name);

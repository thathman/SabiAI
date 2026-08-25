CREATE TABLE IF NOT EXISTS source_discoveries (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate',
    sports_json TEXT NOT NULL DEFAULT '[]',
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    reliability TEXT NOT NULL DEFAULT 'unknown',
    notes TEXT,
    discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_at TEXT,
    last_checked_at TEXT,
    last_check_ok INTEGER,
    last_error TEXT,
    UNIQUE(url)
);
CREATE INDEX IF NOT EXISTS idx_source_discoveries_status ON source_discoveries(status, last_checked_at);

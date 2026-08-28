ALTER TABLE daily_research_runs ADD COLUMN coverage_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE daily_research_runs ADD COLUMN all_recommendations_json TEXT NOT NULL DEFAULT '[]';

CREATE TABLE IF NOT EXISTS research_slice_cache (
    cache_key TEXT PRIMARY KEY,
    scan_date TEXT NOT NULL,
    sport TEXT NOT NULL,
    country TEXT NOT NULL,
    competition TEXT NOT NULL,
    division TEXT NOT NULL,
    events_json TEXT NOT NULL DEFAULT '[]',
    recommendations_json TEXT NOT NULL DEFAULT '[]',
    model TEXT,
    usage_json TEXT NOT NULL DEFAULT '{}',
    fetched_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_research_slice_cache_scope
    ON research_slice_cache(scan_date, sport, country, competition, division);
CREATE INDEX IF NOT EXISTS idx_research_slice_cache_expiry
    ON research_slice_cache(expires_at);

CREATE TABLE IF NOT EXISTS research_slice_runs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    scan_date TEXT NOT NULL,
    sport TEXT NOT NULL,
    country TEXT NOT NULL,
    competition TEXT NOT NULL,
    division TEXT NOT NULL,
    event_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    cache_hit INTEGER NOT NULL DEFAULT 0,
    model TEXT,
    events_json TEXT NOT NULL DEFAULT '[]',
    recommendations_json TEXT NOT NULL DEFAULT '[]',
    source_failures_json TEXT NOT NULL DEFAULT '[]',
    usage_json TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_research_slice_runs_run
    ON research_slice_runs(run_id, scan_date, sport, country, competition, division);

CREATE TABLE IF NOT EXISTS daily_research_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key TEXT NOT NULL UNIQUE,
    scan_date TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    model TEXT,
    events_considered INTEGER NOT NULL DEFAULT 0,
    source_failures_json TEXT NOT NULL DEFAULT '[]',
    recommendations_json TEXT NOT NULL DEFAULT '[]',
    notes_json TEXT NOT NULL DEFAULT '[]',
    usage_json TEXT NOT NULL DEFAULT '{}',
    push_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_daily_research_runs_date
    ON daily_research_runs(scan_date, generated_at DESC);

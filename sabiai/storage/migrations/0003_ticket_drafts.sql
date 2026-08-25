CREATE TABLE IF NOT EXISTS ticket_drafts (
    id TEXT PRIMARY KEY,
    parent_draft_id TEXT REFERENCES ticket_drafts(id),
    source_type TEXT NOT NULL,
    source_reference TEXT,
    source_bookmaker_slug TEXT,
    target_bookmaker_slug TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    payload_json TEXT NOT NULL,
    issues_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ticket_drafts_created
    ON ticket_drafts(created_at);

CREATE INDEX IF NOT EXISTS idx_ticket_drafts_parent
    ON ticket_drafts(parent_draft_id);

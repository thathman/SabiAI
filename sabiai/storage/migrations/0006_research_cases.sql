CREATE TABLE IF NOT EXISTS research_cases (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    sport TEXT NOT NULL,
    event TEXT NOT NULL,
    market TEXT,
    home TEXT,
    away TEXT,
    event_id TEXT REFERENCES events(id) ON DELETE SET NULL,
    objective TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    notes_json TEXT NOT NULL DEFAULT '[]',
    assessment_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_assessed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_research_cases_status ON research_cases(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_research_cases_event ON research_cases(event_id, event);

CREATE TABLE IF NOT EXISTS research_case_evidence (
    case_id TEXT NOT NULL REFERENCES research_cases(id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES research_evidence(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (case_id, evidence_id)
);
CREATE INDEX IF NOT EXISTS idx_research_case_evidence_id ON research_case_evidence(evidence_id);

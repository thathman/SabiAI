-- V2.5 decision context stays beside picks_v2 so the canonical pick ledger is unchanged.
CREATE TABLE IF NOT EXISTS engine_pick_context (
    pick_id TEXT PRIMARY KEY REFERENCES picks_v2(id) ON DELETE CASCADE,
    offer_ref TEXT NOT NULL,
    bookmaker TEXT,
    observed_at TEXT,
    estimated_probability_pct REAL NOT NULL,
    consensus_probability_pct REAL,
    fair_odds REAL,
    expected_value_pct REAL,
    decision_state TEXT NOT NULL,
    evidence_quality TEXT,
    evidence_ready INTEGER NOT NULL DEFAULT 0,
    evidence_sources_json TEXT NOT NULL DEFAULT '[]',
    missing_evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_engine_pick_context_offer ON engine_pick_context(offer_ref);
CREATE INDEX IF NOT EXISTS idx_engine_pick_context_decision ON engine_pick_context(decision_state, created_at DESC);

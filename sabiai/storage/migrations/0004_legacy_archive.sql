CREATE TABLE IF NOT EXISTS legacy_archive (
    source_table TEXT NOT NULL,
    legacy_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    migrated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_table, legacy_key)
);

CREATE INDEX IF NOT EXISTS idx_legacy_archive_table
ON legacy_archive(source_table);

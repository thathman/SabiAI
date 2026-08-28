ALTER TABLE ticket_legs ADD COLUMN pick_id TEXT REFERENCES picks_v2(id);
CREATE INDEX IF NOT EXISTS idx_ticket_legs_pick_id ON ticket_legs(pick_id);

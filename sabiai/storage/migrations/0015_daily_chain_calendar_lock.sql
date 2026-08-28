-- Add the calendar-day guard separately so databases that already applied 0014
-- receive the same chain state shape without replaying an earlier migration.
ALTER TABLE strategy_chain_state ADD COLUMN last_ticket_date TEXT;

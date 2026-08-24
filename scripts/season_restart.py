#!/usr/bin/env python3
"""Season restart: update bankroll to ₦30,000, reset chain to Day 1 / ₦1,000."""
import sqlite3, os, sys
from datetime import datetime, timezone

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "bets.db")

def main():
    if not os.path.exists(DB):
        print(f"ERROR: Database not found at {DB}")
        sys.exit(1)

    db = sqlite3.connect(DB)
    now = datetime.now(timezone.utc).isoformat()

    # 1. Update bankroll
    db.execute("""
        INSERT INTO bankroll (ts, stake, balance, note, delta, kind)
        VALUES (?, 0, 30000, 'Season restart — new bankroll confirmed by Hendrix', 30000, 'season_restart')
    """, (now,))
    print("✅ Bankroll set to ₦30,000")

    # 2. Reset chain state
    db.execute("""
        UPDATE continuous_bet_state SET
            streak_day = 1,
            starting_stake = 1000,
            current_stake = 1000,
            total_compounded = 0,
            cycle_count = 0,
            streak_status = 'active',
            last_pick_id = NULL,
            last_pick_date = NULL,
            last_outcome = NULL,
            restrategy_until = NULL,
            restrategy_started_at = NULL,
            restrategy_reason = NULL,
            started_on = ?,
            updated_at = ?
        WHERE id = 1
    """, (now, now))
    print("✅ Chain reset: Day 1, ₦1,000 stake, status=active")

    db.commit()
    db.close()
    print(f"\n🎰 Season restart complete. Bankroll: ₦30,000 | Chain: Day 1 / ₦1,000")

if __name__ == "__main__":
    main()

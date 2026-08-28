from pathlib import Path

from sabiai.storage import HistoryService, PerformanceAnalytics, SabiDatabase


def test_record_views_can_separate_sabi_boy_and_hendrix(tmp_path: Path):
    db = SabiDatabase(tmp_path / "owners.db")
    db.initialize()
    with db.transaction() as conn:
        conn.execute("INSERT INTO sports(id,slug,name) VALUES('sp','football','Football')")
        conn.execute("INSERT INTO events(id,sport_id,name,starts_at,status) VALUES('e','sp','Home vs Away','2026-08-28T12:00:00+00:00','finished')")
        conn.execute("INSERT INTO markets(id,event_id,kind,label) VALUES('m','e','winner','Home to win')")
        conn.execute("INSERT INTO selections(id,market_id,label) VALUES('s','m','Home to win')")
        for pick_id, owner, outcome in [('p1', 'sabi_boy', 'won'), ('p2', 'hendrix', 'lost')]:
            conn.execute(
                "INSERT INTO picks_v2(id,event_id,market_id,selection_id,decimal_odds,outcome,owner) VALUES(?,?,?,?,?,?,?)",
                (pick_id, 'e', 'm', 's', '1.50', outcome, owner),
            )
    assert HistoryService(db).summary(owner="sabi_boy")["picks"]["total"] == 1
    assert HistoryService(db).summary(owner="hendrix")["picks"]["lost"] == 1
    assert PerformanceAnalytics(db).streaks(owner="sabi_boy")["current"] == {"type": "won", "count": 1}

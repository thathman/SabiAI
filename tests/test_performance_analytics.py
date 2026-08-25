from pathlib import Path

from sabiai.storage import PerformanceAnalytics, SabiDatabase


def _db(tmp_path: Path) -> SabiDatabase:
    db = SabiDatabase(tmp_path / "analytics.db")
    db.initialize()
    with db.transaction() as conn:
        conn.execute("INSERT INTO sports(id,slug,name) VALUES('sport_football','football','Football')")
        conn.execute("INSERT INTO competitions(id,sport_id,name) VALUES('comp_pl','sport_football','Premier League')")
        for event_id, name, stamp in (
            ('e1','Arsenal vs Chelsea','2026-08-20T12:00:00+00:00'),
            ('e2','Liverpool vs Everton','2026-08-21T12:00:00+00:00'),
            ('e3','Leeds vs Wolves','2026-08-22T12:00:00+00:00'),
        ):
            conn.execute(
                "INSERT INTO events(id,sport_id,competition_id,name,starts_at,status) VALUES(?,?,?,?,?,'finished')",
                (event_id, 'sport_football', 'comp_pl', name, stamp),
            )
        markets = (
            ('m1','e1','winner','Arsenal to win'),
            ('m2','e2','total','Over 2.5 goals'),
            ('m3','e3','handicap','Leeds +1.5 handicap'),
        )
        for market_id, event_id, kind, label in markets:
            conn.execute(
                "INSERT INTO markets(id,event_id,kind,label) VALUES(?,?,?,?)",
                (market_id, event_id, kind, label),
            )
            conn.execute(
                "INSERT INTO selections(id,market_id,label) VALUES(?,?,?)",
                (f's_{market_id}', market_id, label),
            )
        picks = (
            ('p1','e1','m1','s_m1','1.40','Kelly','won','2026-08-20T13:00:00+00:00'),
            ('p2','e2','m2','s_m2','1.80','Kelly','won','2026-08-21T13:00:00+00:00'),
            ('p3','e3','m3','s_m3','2.20','Long Shot','lost','2026-08-22T13:00:00+00:00'),
            ('p4','e1','m1','s_m1','3.50','Long Shot','lost','2026-08-23T13:00:00+00:00'),
            ('p5','e2','m2','s_m2','5.50','Kelly','won','2026-08-24T13:00:00+00:00'),
        )
        for row in picks:
            conn.execute(
                """INSERT INTO picks_v2(id,event_id,market_id,selection_id,decimal_odds,strategy,outcome,created_at,settled_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (*row[:-1], row[-1], row[-1]),
            )

        conn.execute(
            """INSERT INTO tickets(id,source_type,status,combined_odds,created_at,settled_at)
               VALUES('t1','booking_code','lost','5.20','2026-08-22T10:00:00+00:00','2026-08-22T14:00:00+00:00')"""
        )
        conn.execute(
            """INSERT INTO tickets(id,source_type,parent_ticket_id,status,combined_odds,created_at,settled_at)
               VALUES('t2','edit','t1','won','3.20','2026-08-23T10:00:00+00:00','2026-08-23T14:00:00+00:00')"""
        )
        conn.execute(
            """INSERT INTO ticket_legs(id,ticket_id,leg_no,event_id,market_id,selection_id,decimal_odds,outcome)
               VALUES('l1','t1',1,'e1','m1','s_m1','1.40','won')"""
        )
        conn.execute(
            """INSERT INTO ticket_legs(id,ticket_id,leg_no,event_id,market_id,selection_id,decimal_odds,outcome)
               VALUES('l2','t1',2,'e3','m3','s_m3','2.20','lost')"""
        )
        conn.execute(
            """INSERT INTO ticket_legs(id,ticket_id,leg_no,event_id,market_id,selection_id,decimal_odds,outcome)
               VALUES('l3','t2',1,'e2','m2','s_m2','1.80','won')"""
        )

        ledger = (
            ('2026-08-20T09:00:00+00:00','opening_balance','100.00','100.00'),
            ('2026-08-20T10:00:00+00:00','stake','-10.00','90.00'),
            ('2026-08-20T14:00:00+00:00','payout','18.00','108.00'),
            ('2026-08-21T09:00:00+00:00','deposit','50.00','158.00'),
            ('2026-08-21T15:00:00+00:00','withdrawal','-20.00','138.00'),
        )
        for occurred_at, kind, amount, balance_after in ledger:
            conn.execute(
                "INSERT INTO bankroll_ledger(occurred_at,kind,amount,balance_after) VALUES(?,?,?,?)",
                (occurred_at, kind, amount, balance_after),
            )
    return db


def test_streaks_and_profit_loss(tmp_path):
    analytics = PerformanceAnalytics(_db(tmp_path))
    streaks = analytics.streaks()
    assert streaks["current"] == {"type": "won", "count": 1}
    assert streaks["best_win_streak"] == 2
    assert streaks["worst_losing_streak"] == 2

    pnl = analytics.profit_loss()
    assert pnl["betting"]["profit_loss"] == "8.00"
    assert pnl["funding"]["deposits_and_opening"] == "150.00"
    assert pnl["bankroll"] == "138.00"


def test_breakdowns_and_ticket_killers(tmp_path):
    analytics = PerformanceAnalytics(_db(tmp_path))
    strategies = {row["strategy"]: row for row in analytics.by_strategy()}
    assert strategies["Kelly"]["won"] == 3
    assert strategies["Long Shot"]["lost"] == 2

    odds = {row["odds_band"]: row for row in analytics.by_odds_band()}
    assert odds["1.01–1.49"]["won"] == 1
    assert odds["5.00+"]["won"] == 1

    killers = analytics.ticket_killers()
    assert len(killers) == 1
    assert killers[0]["ticket_id"] == "t1"
    assert killers[0]["selection"] == "Leeds +1.5 handicap"

    sources = analytics.ticket_sources()
    assert any(row["version_type"] == "original" and row["lost"] == 1 for row in sources)
    assert any(row["version_type"] == "edited" and row["won"] == 1 for row in sources)


def test_chart_series_and_ticket_bands(tmp_path):
    analytics = PerformanceAnalytics(_db(tmp_path))
    daily = analytics.daily_outcomes(30)
    assert daily[-1]["won"] == 1

    bankroll = analytics.bankroll_series()
    assert bankroll[-1]["balance"] == "138.00"

    sizes = {row["leg_count"]: row for row in analytics.by_ticket_size()}
    assert sizes[2]["lost"] == 1
    assert sizes[1]["won"] == 1

    bands = {row["combined_odds_band"]: row for row in analytics.by_combined_odds_band()}
    assert bands["3.00–4.99"]["won"] == 1
    assert bands["5.00–9.99"]["lost"] == 1

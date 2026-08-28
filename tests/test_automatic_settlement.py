from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sabiai.settlement import AutomaticSettlementService, ResultSnapshot
from sabiai.storage import SabiDatabase


def _db(tmp_path):
    db = SabiDatabase(tmp_path / "auto-settlement.db")
    db.initialize()
    started = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    with db.transaction() as conn:
        conn.execute("INSERT INTO sports(id,slug,name) VALUES('sp','football','Football')")
        conn.execute("INSERT INTO participants(id,sport_id,participant_type,name) VALUES('home','sp','team','Home')")
        conn.execute("INSERT INTO participants(id,sport_id,participant_type,name) VALUES('away','sp','team','Away')")
        conn.execute(
            """INSERT INTO events(id,sport_id,name,starts_at,home_participant_id,away_participant_id,status)
               VALUES('e1','sp','Home vs Away',?,'home','away','scheduled')""",
            (started,),
        )
        conn.execute("INSERT INTO event_source_ids(event_id,source_name,source_event_id) VALUES('e1','TheSportsDB','42')")
        markets = [
            ("m1", "winner", "Home to win", None, None, "full_event", None, "s1", "home", "home"),
            ("m2", "total", "Over 2.5 goals", "goals", "2.5", "full_event", None, "s2", "over", None),
            ("m3", "count", "Both teams to score — Yes", "teams_scoring", None, "full_event", None, "s3", "yes", None),
            ("m4", "player", "Player shots", "shots", "1.5", "full_event", None, "s4", "over", None),
        ]
        for market_id, kind, label, metric, line, period, market_participant, selection_id, side, selection_participant in markets:
            conn.execute(
                """INSERT INTO markets(id,event_id,kind,label,metric,line,period,participant_id)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (market_id, "e1", kind, label, metric, line, period, market_participant),
            )
            conn.execute(
                "INSERT INTO selections(id,market_id,label,side,participant_id) VALUES(?,?,?,?,?)",
                (selection_id, market_id, label, side, selection_participant),
            )
        for index in range(1, 5):
            conn.execute(
                """INSERT INTO picks_v2(id,event_id,market_id,selection_id,decimal_odds,outcome,created_at)
                   VALUES(?,?,?,?,?,'pending',?)""",
                (f"p{index}", "e1", f"m{index}", f"s{index}", "1.80", started),
            )
        conn.execute(
            "INSERT INTO tickets(id,source_type,status,combined_odds,created_at) VALUES('t1','instruction','pending','3.24',?)",
            (started,),
        )
        for index in (1, 2):
            conn.execute(
                """INSERT INTO ticket_legs(id,ticket_id,leg_no,event_id,market_id,selection_id,decimal_odds,outcome)
                   VALUES(?,?,?,?,?,?,?,'pending')""",
                (f"l{index}", "t1", index, "e1", f"m{index}", f"s{index}", "1.80"),
            )
    return db


def _snapshot(status="finished"):
    return ResultSnapshot(
        source_name="TheSportsDB",
        source_event_id="42",
        status=status,
        home_score=Decimal("2") if status == "finished" else Decimal("1"),
        away_score=Decimal("1") if status == "finished" else Decimal("0"),
        observed_at=datetime.now(timezone.utc).isoformat(),
        payload={"strStatus": status, "intHomeScore": "2", "intAwayScore": "1"},
    )


def test_final_heartbeat_settles_supported_markets_once_and_audits(tmp_path):
    db = _db(tmp_path)
    service = AutomaticSettlementService(db, fetchers={"thesportsdb": lambda _: _snapshot()})

    first = service.run()
    second = service.run()

    assert first.picks_settled == 3
    assert first.ticket_legs_settled == 2
    assert first.records_skipped == 1
    assert second.changed == 0
    assert second.records_skipped == 1
    with db.connect() as conn:
        picks = dict(conn.execute("SELECT id,outcome FROM picks_v2 ORDER BY id").fetchall())
        ticket = conn.execute("SELECT status FROM tickets WHERE id='t1'").fetchone()[0]
        audits = conn.execute("SELECT COUNT(*) FROM settlement_audit").fetchone()[0]
        observations = conn.execute("SELECT COUNT(*) FROM event_result_observations").fetchone()[0]
        event_status = conn.execute("SELECT status FROM events WHERE id='e1'").fetchone()[0]
    assert picks == {"p1": "won", "p2": "won", "p3": "won", "p4": "pending"}
    assert ticket == "won"
    assert audits == 6
    assert observations == 1
    assert event_status == "finished"


def test_live_heartbeat_updates_event_without_settling(tmp_path):
    db = _db(tmp_path)
    report = AutomaticSettlementService(
        db, fetchers={"thesportsdb": lambda _: _snapshot("live")}
    ).run()
    assert report.live_events == 1
    assert report.changed == 0
    with db.connect() as conn:
        assert conn.execute("SELECT status FROM events WHERE id='e1'").fetchone()[0] == "live"
        assert conn.execute("SELECT COUNT(*) FROM settlement_audit").fetchone()[0] == 0


def test_non_thesportsdb_source_can_resolve_exact_event_for_result_heartbeat(tmp_path):
    db = _db(tmp_path)
    with db.connect() as conn:
        event_day = conn.execute("SELECT starts_at FROM events WHERE id='e1'").fetchone()[0][:10]
    with db.transaction() as conn:
        conn.execute("DELETE FROM event_source_ids WHERE event_id='e1'")
        conn.execute("INSERT INTO event_source_ids(event_id,source_name,source_event_id) VALUES('e1','Parse · SportyBet','sr:match:1')")
    service = AutomaticSettlementService(db, fetchers={})
    calls = []

    def fake_fetch(request):
        calls.append(request.capability)
        if request.capability == "event_search":
            return {"raw": {"events": [{"strEvent": "Home vs Away", "dateEvent": event_day, "idEvent": "99"}]}}
        return {"raw": {"event": {"strStatus": "FT", "intHomeScore": "2", "intAwayScore": "1"}}}

    service._thesportsdb_fallback.adapter.fetch = fake_fetch
    report = service.run()
    assert report.finished_events == 1
    assert report.picks_settled == 3
    assert calls == ["event_search", "event_lookup"]


def test_score_evaluator_handles_draw_no_bet_and_team_totals():
    snapshot = _snapshot()
    base = {
        "sport_slug": "football",
        "period": "full_event",
        "home_participant_id": "home",
        "away_participant_id": "away",
        "market_participant_id": None,
        "selection_participant_id": "home",
    }
    handicap = {
        **base,
        "kind": "handicap",
        "metric": "draw_no_bet",
        "line": "0",
        "side": "home",
    }
    team_total = {
        **base,
        "kind": "team_total",
        "metric": "goals",
        "line": "1.5",
        "side": "over",
    }
    assert AutomaticSettlementService.evaluate(handicap, snapshot) == "won"
    assert AutomaticSettlementService.evaluate(team_total, snapshot) == "won"

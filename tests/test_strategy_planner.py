from decimal import Decimal
from pathlib import Path

from sabiai.storage import DailyResearchLog, SabiDatabase, StrategyPlanStore
from sabiai.strategy import StrategyChainStore, StrategyLearningService, StrategyPlanner, StrategyTicketService
from sabiai.settlement import SettlementService


def _recommendations():
    return [
        {"sport": "football", "event": "A vs B", "market": "A to win", "pick": "A", "decimal_odds": 1.18, "confidence_pct": 72},
        {"sport": "basketball", "event": "C vs D", "market": "C to win", "pick": "C", "decimal_odds": 1.14, "confidence_pct": 68},
        {"sport": "tennis", "event": "E vs F", "market": "E to win", "pick": "E", "decimal_odds": 1.25, "confidence_pct": 64},
    ]


def test_strategy_planner_builds_daily_chain_and_precision_plan():
    plans = StrategyPlanner().build(_recommendations(), bankroll=Decimal("30000"), source_run_id="run-1")
    by_code = {row["strategy_code"]: row for row in plans}
    assert by_code["daily_chain_1_30"]["status"] == "ready"
    assert Decimal(by_code["daily_chain_1_30"]["combined_odds"]) >= Decimal("1.30")
    assert Decimal(by_code["daily_chain_1_30"]["suggested_stake"]) == Decimal("300.00")
    assert by_code["precision_picks"]["candidates"][0]["event"] == "A vs B"


def test_daily_chain_state_compounds_only_wins_and_resets_losses(tmp_path: Path):
    db = SabiDatabase(tmp_path / "chain.db")
    db.initialize()
    chain = StrategyChainStore(db)
    initial = chain.ensure()
    assert initial["current_day"] == 1
    assert initial["current_stake"] == "1000.00"

    chain.attach_ticket("day-1")
    after_win = chain.settle_ticket("day-1", "won", "1.30")
    assert after_win["completed_days"] == 1
    assert after_win["current_day"] == 2
    assert after_win["current_stake"] == "1300.00"
    assert after_win["status"] == "ready"

    chain.attach_ticket("day-2")
    after_loss = chain.settle_ticket("day-2", "lost", "1.30")
    assert after_loss["completed_days"] == 0
    assert after_loss["current_day"] == 1
    assert after_loss["current_stake"] == "1000.00"


def test_daily_chain_marks_a_cycle_complete_after_thirty_wins(tmp_path: Path):
    db = SabiDatabase(tmp_path / "chain-complete.db")
    db.initialize()
    chain = StrategyChainStore(db)
    for day in range(1, 31):
        chain.attach_ticket(f"day-{day}")
        state = chain.settle_ticket(f"day-{day}", "won", "1.30")
    assert state["status"] == "completed"
    assert state["completed_days"] == 30
    assert state["cycle_count"] == 1
    restarted = chain.ensure()
    assert restarted["status"] == "ready"
    assert restarted["current_day"] == 1
    assert restarted["current_stake"] == restarted["starting_stake"]


def test_planner_holds_the_next_chain_day_until_settlement():
    state = {
        "status": "pending",
        "completed_days": 4,
        "target_days": 30,
        "target_odds": "1.30",
        "starting_stake": "1000.00",
        "current_stake": "2856.10",
        "active_ticket_id": "ticket-day-5",
    }
    plan = next(
        row for row in StrategyPlanner().build(_recommendations(), bankroll="30000", source_run_id="run-chain", chain_state=state)
        if row["strategy_code"] == "daily_chain_1_30"
    )
    assert plan["status"] == "pending"
    assert plan["chain"]["current_day"] == 5
    assert Decimal(plan["suggested_stake"]) == Decimal("2856.10")
    assert plan["candidate_count"] == 0


def test_weekly_long_shot_does_not_pad_weak_legs():
    plans = StrategyPlanner().build(_recommendations(), bankroll="30000", source_run_id="run-2")
    long_shot = next(row for row in plans if row["strategy_code"] == "weekly_long_shot_1000")
    assert long_shot["status"] == "watch"
    assert long_shot["combined_odds"] is not None
    assert long_shot["candidate_count"] == 3


def test_strategy_plans_and_research_log_persist(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    plans = StrategyPlanner().build(_recommendations(), bankroll="1000", source_run_id="run-3")
    StrategyPlanStore(db).save_many(plans)
    DailyResearchLog(db).save(
        {
            "run_id": "run-3",
            "date": "2026-08-28",
            "generated_at": "2026-08-28T08:00:00+00:00",
            "recommendations": _recommendations(),
            "strategy_plans": plans,
        }
    )
    latest = StrategyPlanStore(db).latest_by_strategy()
    assert {row["strategy_code"] for row in latest} == {
        "daily_chain_1_30",
        "weekly_long_shot_1000",
        "precision_picks",
    }
    assert DailyResearchLog(db).latest()["strategy_plans"][0]["strategy_code"] == "precision_picks"


def test_scan_context_includes_records_for_sabi_boy(tmp_path: Path):
    db = SabiDatabase(tmp_path / "scan-context.db")
    db.initialize()
    DailyResearchLog(db).save(
        {
            "run_id": "run-context",
            "date": "2026-08-28",
            "generated_at": "2026-08-28T08:00:00+00:00",
            "recommendations": [],
            "strategy_plans": [],
        }
    )
    with db.transaction() as conn:
        conn.execute("INSERT INTO sports(id,slug,name) VALUES('sp','football','Football')")
        conn.execute("INSERT INTO events(id,sport_id,name,starts_at,status) VALUES('e','sp','Home vs Away','2026-08-28T12:00:00+00:00','scheduled')")
        conn.execute("INSERT INTO markets(id,event_id,kind,label) VALUES('m','e','winner','Home to win')")
        conn.execute("INSERT INTO selections(id,market_id,label) VALUES('s','m','Home to win')")
        conn.execute("""INSERT INTO picks_v2(id,event_id,market_id,selection_id,decimal_odds,owner,source_run_id)
                        VALUES('p','e','m','s','1.50','sabi_boy','run-context')""")
    context = DailyResearchLog(db).context()
    assert context["recorded_picks"][0]["id"] == "p"


def test_strategy_learning_is_bounded_and_v2_native(tmp_path: Path):
    db = SabiDatabase(tmp_path / "learning.db")
    db.initialize()
    with db.transaction() as conn:
        conn.execute("INSERT INTO sports(id,slug,name) VALUES('sp','football','Football')")
        conn.execute("INSERT INTO events(id,sport_id,name,starts_at,status) VALUES('e','sp','Home vs Away','2026-08-28T12:00:00+00:00','finished')")
        conn.execute("INSERT INTO markets(id,event_id,kind,label) VALUES('m','e','winner','Home to win')")
        conn.execute("INSERT INTO selections(id,market_id,label) VALUES('s','m','Home to win')")
        for index in range(15):
            outcome = 'won' if index < 10 else 'lost'
            conn.execute(
                """INSERT INTO picks_v2(id,event_id,market_id,selection_id,decimal_odds,strategy,
                   strategy_code,outcome,stake,payout,owner) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (f'p{index}', 'e', 'm', 's', '1.50', 'Daily 1.30 Chain', 'daily_chain_1_30', outcome, '1.00', '2.00' if outcome == 'won' else None, 'sabi_boy'),
            )
        conn.execute(
            """INSERT INTO picks_v2(id,event_id,market_id,selection_id,decimal_odds,strategy,
               strategy_code,outcome,owner,record_kind) VALUES('tip','e','m','s','2.00','Daily 1.30 Chain','daily_chain_1_30','won','hendrix','tip')"""
        )
    rows = StrategyLearningService(db).summaries()
    assert rows[0]["strategy_code"] == "daily_chain_1_30"
    assert rows[0]["settled_picks"] == 15
    assert rows[0]["policy"] == "eligible_to_expand"
    assert rows[0]["owner"] == "sabi_boy"


def test_ready_strategy_plan_materializes_one_ticket_without_external_action(tmp_path: Path):
    db = SabiDatabase(tmp_path / "strategy-ticket.db")
    db.initialize()
    with db.transaction() as conn:
        conn.execute("INSERT INTO bankroll_ledger(kind,amount,balance_after,note) VALUES('opening_balance','1000','1000','test')")
    plan = StrategyPlanner().build(_recommendations(), bankroll="1000", source_run_id="run-ticket")
    result = StrategyTicketService(db).materialize(plan, model="test-model", source_run_id="run-ticket")
    assert result and result[0]["strategy_code"] == "daily_chain_1_30"
    with db.connect() as conn:
        ticket = conn.execute("SELECT strategy_code,owner,stake,status FROM tickets").fetchone()
        legs = conn.execute("SELECT COUNT(*) FROM ticket_legs").fetchone()[0]
        balance = conn.execute("SELECT balance_after FROM bankroll_ledger ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert ticket["strategy_code"] == "daily_chain_1_30"
    assert ticket["owner"] == "sabi_boy"
    assert ticket["status"] == "pending"
    assert legs >= 1
    assert balance == "990.00"


def test_strategy_ticket_settlement_updates_its_linked_tip_for_learning(tmp_path: Path):
    db = SabiDatabase(tmp_path / "strategy-settle.db")
    db.initialize()
    with db.transaction() as conn:
        conn.execute("INSERT INTO bankroll_ledger(kind,amount,balance_after,note) VALUES('opening_balance','1000','1000','test')")
    plan = StrategyPlanner().build(_recommendations(), bankroll="1000", source_run_id="run-settle")
    StrategyTicketService(db).materialize(plan, model="test-model", source_run_id="run-settle")
    with db.connect() as conn:
        leg = conn.execute("SELECT id,pick_id FROM ticket_legs ORDER BY leg_no LIMIT 1").fetchone()
        leg_id, pick_id = leg["id"], leg["pick_id"]
    SettlementService(db).settle_ticket_leg(leg_id, "won", source="test")
    with db.connect() as conn:
        assert conn.execute("SELECT outcome FROM picks_v2 WHERE id=?", (pick_id,)).fetchone()[0] == "won"

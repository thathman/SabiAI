from pathlib import Path

from sabiai.storage import AdvancedAnalytics, OfferObservationStore, SabiDatabase


def test_ticket_version_outcome_comparison(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO tickets(id,source_type,status,combined_odds) VALUES('parent','booking_code','lost','20.00')"
        )
        conn.execute(
            "INSERT INTO tickets(id,source_type,parent_ticket_id,status,combined_odds) VALUES('child','conversion','parent','won','8.00')"
        )
    result = AdvancedAnalytics(db).ticket_version_outcomes()
    assert result["summary"]["total_pairs"] == 1
    assert result["summary"]["improved_result"] == 1
    assert result["pairs"][0]["comparison"] == "improved_result"
    assert result["pairs"][0]["combined_odds_change"] == "-12.00"


def test_bookmaker_price_history_and_disagreement(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    store = OfferObservationStore(db)
    store.save(
        target_bookmaker_slug="sportybet",
        event="Arsenal vs Chelsea",
        market="Over 2.5 goals",
        decimal_odds="1.80",
        observed_at="2026-08-25T12:00:00+00:00",
        source="test",
    )
    store.save(
        target_bookmaker_slug="sportybet",
        event="Arsenal vs Chelsea",
        market="Over 2.5 goals",
        decimal_odds="1.84",
        observed_at="2026-08-25T12:05:00+00:00",
        source="test",
    )
    store.save(
        target_bookmaker_slug="bet9ja",
        event="Arsenal vs Chelsea",
        market="Over 2.5 goals",
        decimal_odds="1.78",
        observed_at="2026-08-25T12:05:00+00:00",
        source="test",
    )

    analytics = AdvancedAnalytics(db)
    sporty = next(row for row in analytics.bookmaker_price_history() if row["bookmaker"] == "sportybet")
    assert sporty["first_odds"] == "1.80"
    assert sporty["latest_odds"] == "1.84"
    assert sporty["change"] == "0.040"

    gap = analytics.latest_price_disagreements()[0]
    assert gap["bookmakers"] == 2
    assert gap["highest_latest_odds"] == "1.840"
    assert gap["lowest_latest_odds"] == "1.780"
    assert gap["latest_gap"] == "0.060"

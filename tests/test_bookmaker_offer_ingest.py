from datetime import datetime, timedelta, timezone
from pathlib import Path

from sabiai.config import Settings
from sabiai.openclaw.gateway import SabiToolGateway


def _gateway(tmp_path: Path) -> SabiToolGateway:
    return SabiToolGateway(
        Settings(
            repo_root=tmp_path,
            data_dir=tmp_path / "data",
            legacy_bets_db=tmp_path / "data" / "bets.db",
            v2_db=tmp_path / "data" / "v2.db",
            timezone="Africa/Lagos",
            paid_sources_enabled=False,
        )
    )


def _source_leg():
    return {
        "sport": "Football",
        "event": "Arsenal vs Chelsea",
        "home": "Arsenal",
        "away": "Chelsea",
        "market": "Over 2.5 goals",
        "odds": "1.70",
    }


def _now():
    return datetime.now(timezone.utc).isoformat()


def test_market_search_ingest_rejects_wrong_book_and_invalid_odds(tmp_path: Path):
    gateway = _gateway(tmp_path)
    result = gateway.dispatch(
        "bookmaker.market_search.ingest",
        {
            "target_bookmaker": "SportyBet",
            "offers": [
                {
                    "event": "Arsenal vs Chelsea",
                    "market": "Over 2.5 goals",
                    "decimal_odds": "1.82",
                    "bookmaker": "SportyBet",
                    "sport": "Football",
                },
                {
                    "event": "Arsenal vs Chelsea",
                    "market": "Over 2.5 goals",
                    "decimal_odds": "0.82",
                    "bookmaker": "SportyBet",
                },
                {
                    "event": "Arsenal vs Chelsea",
                    "market": "Over 2.5 goals",
                    "decimal_odds": "1.90",
                    "bookmaker": "Bet9ja",
                },
            ],
        },
    )

    assert result["ok"] is True
    data = result["data"]
    assert len(data["offers"]) == 1
    assert data["offers"][0]["odds"] == "1.82"
    assert data["usable"] is False
    assert len([issue for issue in data["issues"] if issue["level"] == "error"]) == 2
    assert any(issue["level"] == "warning" for issue in data["issues"])


def test_duplicate_browser_offer_is_ignored_with_warning(tmp_path: Path):
    gateway = _gateway(tmp_path)
    row = {
        "event": "Arsenal vs Chelsea",
        "market": "Over 2.5 goals",
        "decimal_odds": "1.82",
        "bookmaker": "SportyBet",
        "sport": "Football",
        "event_ref": "evt-1",
        "market_ref": "mkt-1",
        "observed_at": _now(),
    }
    result = gateway.dispatch(
        "bookmaker.market_search.ingest",
        {"target_bookmaker": "SportyBet", "offers": [row, dict(row)]},
    )

    assert result["ok"] is True
    assert len(result["data"]["offers"]) == 1
    assert len(result["data"]["observations"]) == 1
    assert any(issue["level"] == "warning" for issue in result["data"]["issues"])


def test_convert_from_search_requires_fresh_timestamp(tmp_path: Path):
    gateway = _gateway(tmp_path)
    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    result = gateway.dispatch(
        "bookmaker.convert.from_search",
        {
            "bookmaker": "Bet9ja",
            "target_bookmaker": "SportyBet",
            "max_age_seconds": 180,
            "legs": [_source_leg()],
            "offers": [
                {
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "sport": "Football",
                    "market": "Over 2.5 goals",
                    "decimal_odds": "1.82",
                    "bookmaker": "SportyBet",
                    "observed_at": stale,
                }
            ],
        },
    )
    assert result["ok"] is True
    assert result["data"]["ready"] is False
    assert result["data"]["conversion"] is None
    assert any("maximum allowed age" in issue["message"] for issue in result["data"]["search"]["issues"])


def test_convert_from_search_accepts_exact_market_and_rejects_near_line(tmp_path: Path):
    gateway = _gateway(tmp_path)

    exact = gateway.dispatch(
        "bookmaker.convert.from_search",
        {
            "bookmaker": "Bet9ja",
            "target_bookmaker": "SportyBet",
            "legs": [_source_leg()],
            "offers": [
                {
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "sport": "Football",
                    "market": "Over 2.5 goals",
                    "decimal_odds": "1.82",
                    "bookmaker": "SportyBet",
                    "event_ref": "evt-1",
                    "market_ref": "mkt-25",
                    "observed_at": _now(),
                }
            ],
        },
    )
    assert exact["ok"] is True
    assert exact["data"]["ready"] is True
    assert exact["data"]["conversion"]["target_ticket"] is not None
    assert exact["data"]["conversion"]["legs"][0]["target_odds"] == "1.82"
    assert exact["data"]["draft"] is not None
    assert len(exact["data"]["search"]["observations"]) == 1

    near = gateway.dispatch(
        "bookmaker.convert.from_search",
        {
            "bookmaker": "Bet9ja",
            "target_bookmaker": "SportyBet",
            "legs": [_source_leg()],
            "offers": [
                {
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "sport": "Football",
                    "market": "Over 3.5 goals",
                    "decimal_odds": "2.30",
                    "bookmaker": "SportyBet",
                    "observed_at": _now(),
                }
            ],
        },
    )
    assert near["ok"] is True
    assert near["data"]["ready"] is False
    assert near["data"]["conversion"]["legs"][0]["status"] == "missing_market"
    assert near["data"]["draft"] is None


def test_conversion_draft_keeps_parent_and_price_observations(tmp_path: Path):
    gateway = _gateway(tmp_path)
    source = gateway.dispatch(
        "ticket.draft.save",
        {
            "bookmaker": "Bet9ja",
            "source_type": "booking_code",
            "source_reference": "Bet9ja:ABC123",
            "legs": [_source_leg()],
        },
    )
    assert source["ok"] is True
    source_draft_id = source["data"]["id"]

    converted = gateway.dispatch(
        "bookmaker.convert.from_search",
        {
            "source_draft_id": source_draft_id,
            "bookmaker": "Bet9ja",
            "target_bookmaker": "SportyBet",
            "legs": [_source_leg()],
            "offers": [
                {
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "sport": "Football",
                    "market": "Over 2.5 goals",
                    "decimal_odds": "1.82",
                    "bookmaker": "SportyBet",
                    "event_ref": "evt-1",
                    "market_ref": "mkt-25",
                    "observed_at": _now(),
                }
            ],
        },
    )
    assert converted["ok"] is True
    target_draft = converted["data"]["draft"]
    assert target_draft["parent_draft_id"] == source_draft_id
    assert target_draft["target_bookmaker_slug"] == "sportybet"
    assert target_draft["payload"]["price_observations"]

    lineage = gateway.dispatch("ticket.draft.lineage", {"draft_id": target_draft["id"]})
    assert lineage["ok"] is True
    assert [item["id"] for item in lineage["data"]["lineage"]] == [source_draft_id, target_draft["id"]]

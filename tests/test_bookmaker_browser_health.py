from datetime import datetime, timezone
from pathlib import Path

import pytest

from sabiai.bookmakers import BookmakerBrowserHealthService
from sabiai.storage import OfferObservationStore, SabiDatabase


def test_browser_health_distinguishes_configured_from_recently_exercised(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    service = BookmakerBrowserHealthService(db)
    now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)

    before = service.one("SportyBet", now=now)
    assert before.market_search_configured is True
    assert before.code_build_configured is True
    assert before.runtime_exercised_recently is False
    assert before.state == "configured_not_recently_exercised"

    OfferObservationStore(db).save(
        target_bookmaker_slug="sportybet",
        event="Arsenal vs Chelsea",
        market="Over 2.5 goals",
        decimal_odds="1.82",
        observed_at=now.isoformat(),
        source="openclaw_browser",
    )
    after = service.one("SportyBet", now=now)
    assert after.runtime_exercised_recently is True
    assert after.state == "recently_exercised"


def test_removed_bookmaker_has_no_health_surface(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    with pytest.raises(ValueError, match="Unknown bookmaker"):
        BookmakerBrowserHealthService(db).one(
            "1xBet",
            now=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
        )

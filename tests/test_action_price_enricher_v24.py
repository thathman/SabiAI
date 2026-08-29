from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sabiai.config import Settings
from sabiai.research import ActionPriceEnricher
from sabiai.sources import Source, SourceBundle, SourceCost, SourceKind, SourceRegistry
from sabiai.storage import CoverageStore, SabiDatabase


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "legacy.db",
        v2_db=tmp_path / "data" / "v2.db",
        timezone="Africa/Lagos",
        paid_sources_enabled=False,
        parse_api_key="parse-key",
        parse_sportybet_scraper_id="sportybet",
        research_sports=("football",),
    )


def test_sportybet_action_price_enricher_persists_full_returned_slate(tmp_path: Path):
    source = Source(
        name="Parse · SportyBet",
        kind=SourceKind.PUBLIC_ENDPOINT,
        cost=SourceCost.FREE,
        sports={"football"},
        capabilities={"fixtures"},
    )
    registry = SourceRegistry()
    registry.register(source)
    rows = [
        {
            "eventId": f"sporty-{index}",
            "homeTeamName": f"Home {index}",
            "awayTeamName": f"Away {index}",
            "tournament": "Premier League",
            "kickoffTime": "2026-08-29T12:00:00+00:00",
            "homeOdds": "1.80",
            "drawOdds": "3.40",
            "awayOdds": "4.20",
        }
        for index in range(3)
    ]

    def fetch(_request):
        return {"raw": {"data": {"events": rows}}}

    database = SabiDatabase(tmp_path / "data" / "v2.db")
    database.initialize()
    result = ActionPriceEnricher(
        _settings(tmp_path),
        database,
        bundle=SourceBundle(registry=registry, fetchers={source.name: fetch}),
    ).refresh(now=datetime(2026, 8, 29, 8, 0, tzinfo=ZoneInfo("Africa/Lagos")))

    assert result.events_persisted == 3
    assert result.priced_events == 3
    assert result.market_offers == 9
    assert len(CoverageStore(database).radar(now=datetime(2026, 8, 29, 7, 0, tzinfo=ZoneInfo("UTC")), horizon_hours=24)) == 3

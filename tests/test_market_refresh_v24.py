from datetime import datetime, timedelta, timezone

from sabiai.research.market_refresh import MarketRefreshPolicy


def test_market_refresh_policy_uses_progressive_near_start_tiers():
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    assert MarketRefreshPolicy.tier(now + timedelta(hours=30), now=now) is None
    assert MarketRefreshPolicy.tier(now + timedelta(hours=20), now=now).name == "T-24h"
    assert MarketRefreshPolicy.tier(now + timedelta(hours=10), now=now).name == "T-12h"
    assert MarketRefreshPolicy.tier(now + timedelta(hours=4), now=now).name == "T-6h"
    assert MarketRefreshPolicy.tier(now + timedelta(minutes=60), now=now).name == "T-90m"
    assert MarketRefreshPolicy.tier(now - timedelta(minutes=1), now=now) is None


def test_refresh_bucket_is_stable_inside_tier_interval():
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    starts = now + timedelta(hours=5)
    first = MarketRefreshPolicy.bucket(starts, now=now)
    second = MarketRefreshPolicy.bucket(starts, now=now + timedelta(minutes=30))
    assert first == second
    later = MarketRefreshPolicy.bucket(starts, now=now + timedelta(hours=2))
    assert later != first

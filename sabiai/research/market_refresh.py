from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class RefreshTier:
    name: str
    interval_seconds: int


class MarketRefreshPolicy:
    """Near-start refresh cadence for expensive/deep market enrichment.

    The cheap event radar can run every 30 minutes. Deep/metered market discovery is bucketed
    so an event is not repeatedly charged at the same distance from start.
    """

    T24 = RefreshTier("T-24h", 6 * 3600)
    T12 = RefreshTier("T-12h", 3 * 3600)
    T6 = RefreshTier("T-6h", 90 * 60)
    T90 = RefreshTier("T-90m", 30 * 60)

    @classmethod
    def tier(cls, starts_at: object, *, now: datetime | None = None) -> RefreshTier | None:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        starts = cls._time(starts_at)
        if starts is None:
            return None
        seconds = (starts - now).total_seconds()
        if seconds <= 0 or seconds > 24 * 3600:
            return None
        if seconds <= 90 * 60:
            return cls.T90
        if seconds <= 6 * 3600:
            return cls.T6
        if seconds <= 12 * 3600:
            return cls.T12
        return cls.T24

    @classmethod
    def bucket(cls, starts_at: object, *, now: datetime | None = None) -> str | None:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        tier = cls.tier(starts_at, now=now)
        if tier is None:
            return None
        bucket = int(now.timestamp()) // tier.interval_seconds
        return f"{tier.name}:{bucket}"

    @staticmethod
    def _time(value: object) -> datetime | None:
        if value is None or not str(value).strip():
            return None
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

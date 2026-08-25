from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sabiai.storage import OfferObservationStore, SabiDatabase

from .browser_profiles import BookmakerBrowserProfiles
from .registry import BookmakerRegistry, default_bookmakers


@dataclass(frozen=True, slots=True)
class BookmakerBrowserHealth:
    bookmaker: str
    slug: str
    state: str
    restoration_configured: bool
    market_search_configured: bool
    code_build_configured: bool
    oldest_verification_days: int | None
    recent_price_observation_at: str | None
    recent_price_observation_age_seconds: int | None
    runtime_exercised_recently: bool
    notes: tuple[str, ...]


class BookmakerBrowserHealthService:
    """Separate browser-playbook configuration truth from recent live execution truth."""

    def __init__(
        self,
        database: SabiDatabase | str | Path,
        bookmakers: BookmakerRegistry | None = None,
        profiles: BookmakerBrowserProfiles | None = None,
    ):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)
        self.bookmakers = bookmakers or default_bookmakers()
        self.profiles = profiles or BookmakerBrowserProfiles()

    def all(
        self,
        *,
        now: datetime | None = None,
        verification_stale_days: int = 30,
        runtime_recent_hours: int = 24,
    ) -> list[BookmakerBrowserHealth]:
        now = now or datetime.now(timezone.utc)
        return [
            self.one(
                bookmaker.slug,
                now=now,
                verification_stale_days=verification_stale_days,
                runtime_recent_hours=runtime_recent_hours,
            )
            for bookmaker in self.bookmakers.all()
        ]

    def one(
        self,
        bookmaker_name: str,
        *,
        now: datetime | None = None,
        verification_stale_days: int = 30,
        runtime_recent_hours: int = 24,
    ) -> BookmakerBrowserHealth:
        bookmaker = self.bookmakers.resolve(bookmaker_name)
        if bookmaker is None:
            raise ValueError(f"Unknown bookmaker: {bookmaker_name}")
        now = now or datetime.now(timezone.utc)
        restore = self.profiles.get(bookmaker.slug)
        search = self.profiles.market_search(bookmaker.slug)
        build = self.profiles.browser_build(bookmaker.slug)
        configured = (
            bool(restore and restore.public_restore and restore.entry_url),
            bool(search and search.ready and search.entry_url),
            bool(build and build.ready and build.entry_url),
        )

        verified_dates = []
        for profile in (restore, search, build):
            raw = getattr(profile, "verified_on", None) if profile is not None else None
            if not raw:
                continue
            try:
                stamp = datetime.fromisoformat(str(raw)).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            verified_dates.append(stamp)
        oldest_days = max(((now - stamp).days for stamp in verified_dates), default=None)

        observations = OfferObservationStore(self.db).recent(bookmaker_slug=bookmaker.slug, limit=1)
        latest = observations[0] if observations else None
        observation_age = None
        runtime_recent = False
        if latest and latest.observed_at:
            try:
                observed = datetime.fromisoformat(str(latest.observed_at).replace("Z", "+00:00"))
                if observed.tzinfo is None:
                    observed = observed.replace(tzinfo=timezone.utc)
                observation_age = max(0, int((now - observed.astimezone(timezone.utc)).total_seconds()))
                runtime_recent = observation_age <= int(timedelta(hours=runtime_recent_hours).total_seconds())
            except ValueError:
                observation_age = None

        notes: list[str] = []
        if not configured[0]:
            notes.append("Booking-code restoration is not currently verified/configured.")
        if not configured[1]:
            notes.append("Public market search is not currently verified/configured.")
        if not configured[2]:
            notes.append("Booking-code creation is not currently verified/configured.")
        if oldest_days is not None and oldest_days > verification_stale_days:
            notes.append(f"At least one browser playbook verification is {oldest_days} days old and needs revalidation.")
        if not runtime_recent:
            notes.append(f"No fresh bookmaker price observation was recorded in the last {runtime_recent_hours} hours.")

        if not any(configured):
            state = "unverified"
        elif oldest_days is not None and oldest_days > verification_stale_days:
            state = "stale_playbook"
        elif runtime_recent:
            state = "recently_exercised"
        else:
            state = "configured_not_recently_exercised"

        return BookmakerBrowserHealth(
            bookmaker=bookmaker.name,
            slug=bookmaker.slug,
            state=state,
            restoration_configured=configured[0],
            market_search_configured=configured[1],
            code_build_configured=configured[2],
            oldest_verification_days=oldest_days,
            recent_price_observation_at=latest.observed_at if latest else None,
            recent_price_observation_age_seconds=observation_age,
            runtime_exercised_recently=runtime_recent,
            notes=tuple(notes),
        )

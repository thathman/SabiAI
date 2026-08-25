from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from .conversion import TargetOffer
from .registry import BookmakerRegistry, default_bookmakers


@dataclass(frozen=True, slots=True)
class OfferIssue:
    row: int
    level: str
    message: str


@dataclass(frozen=True, slots=True)
class VerifiedOffer:
    offer: TargetOffer
    observed_at: str | None
    age_seconds: int | None
    fresh: bool | None
    source: str
    raw: dict


@dataclass(slots=True)
class OfferBatch:
    target_bookmaker_slug: str
    offers: list[VerifiedOffer] = field(default_factory=list)
    issues: list[OfferIssue] = field(default_factory=list)
    max_age_seconds: int | None = None
    freshness_required: bool = False

    @property
    def usable(self) -> bool:
        return bool(self.offers) and not any(issue.level == "error" for issue in self.issues)


class BookmakerOfferService:
    """Normalize browser/adapter market-search results before conversion uses them.

    Plain ingestion may accept an unstamped price with a warning so OpenClaw can inspect the
    extraction. Conversion/build paths should call with require_fresh=True; in that mode a
    missing/unparseable/stale timestamp is an error and the price never reaches conversion.
    """

    def __init__(self, bookmakers: BookmakerRegistry | None = None):
        self.bookmakers = bookmakers or default_bookmakers()

    def normalize(
        self,
        *,
        target_bookmaker: str,
        rows: Iterable[dict],
        source: str = "openclaw_browser",
        require_fresh: bool = False,
        max_age_seconds: int = 180,
        now: datetime | None = None,
    ) -> OfferBatch:
        target = self.bookmakers.resolve(target_bookmaker)
        if target is None:
            raise ValueError(f"Unknown target bookmaker: {target_bookmaker}")
        if max_age_seconds < 0:
            raise ValueError("max_age_seconds cannot be negative.")
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)

        batch = OfferBatch(
            target_bookmaker_slug=target.slug,
            max_age_seconds=max_age_seconds if require_fresh else None,
            freshness_required=require_fresh,
        )
        seen: set[tuple[str, str, str, str | None]] = set()
        for index, raw_value in enumerate(rows, start=1):
            if not isinstance(raw_value, dict):
                batch.issues.append(OfferIssue(index, "error", "Offer row must be an object."))
                continue
            raw = dict(raw_value)
            event = str(raw.get("event") or "").strip()
            market = str(raw.get("market") or raw.get("selection") or raw.get("pick") or "").strip()
            odds = raw.get("decimal_odds") if raw.get("decimal_odds") is not None else raw.get("odds")
            if not event:
                batch.issues.append(OfferIssue(index, "error", "Offer is missing the explicit event name."))
                continue
            if not market:
                batch.issues.append(OfferIssue(index, "error", f"{event}: offer is missing market/selection."))
                continue
            if odds is None:
                batch.issues.append(OfferIssue(index, "error", f"{event} — {market}: decimal odds are missing."))
                continue

            supplied_book = str(raw.get("bookmaker") or raw.get("bookmaker_slug") or target.slug).strip()
            resolved_book = self.bookmakers.resolve(supplied_book)
            if resolved_book is None and supplied_book.casefold() == target.slug.casefold():
                resolved_book = target
            if resolved_book is None or resolved_book.slug != target.slug:
                batch.issues.append(
                    OfferIssue(index, "error", f"{event} — {market}: offer does not belong to {target.name}.")
                )
                continue

            try:
                offer = TargetOffer(
                    event=event,
                    market=market,
                    odds=odds,
                    bookmaker_slug=target.slug,
                    event_ref=self._text(raw.get("event_ref")),
                    market_ref=self._text(raw.get("market_ref")),
                    home=self._text(raw.get("home")),
                    away=self._text(raw.get("away")),
                    sport=self._text(raw.get("sport")),
                )
            except (TypeError, ValueError) as exc:
                batch.issues.append(OfferIssue(index, "error", f"{event} — {market}: {exc}"))
                continue

            observed_at, age_seconds = self._observed(raw.get("observed_at"), now=now)
            if observed_at is None:
                level = "error" if require_fresh else "warning"
                batch.issues.append(
                    OfferIssue(
                        index,
                        level,
                        f"{event} — {market}: observed_at is missing or invalid; re-read the bookmaker price before conversion/building.",
                    )
                )
                if require_fresh:
                    continue
            fresh = age_seconds is not None and age_seconds <= max_age_seconds
            if age_seconds is not None and age_seconds < -15:
                level = "error" if require_fresh else "warning"
                batch.issues.append(
                    OfferIssue(index, level, f"{event} — {market}: observed_at is in the future; re-read the price with a correct clock.")
                )
                if require_fresh:
                    continue
            if require_fresh and age_seconds is not None and age_seconds > max_age_seconds:
                batch.issues.append(
                    OfferIssue(
                        index,
                        "error",
                        f"{event} — {market}: price is {age_seconds}s old; maximum allowed age is {max_age_seconds}s. Recheck the bookmaker.",
                    )
                )
                continue

            key = (
                self._norm(event),
                self._norm(market),
                str(offer.odds),
                offer.market_ref,
            )
            if key in seen:
                batch.issues.append(OfferIssue(index, "warning", f"Duplicate offer ignored: {event} — {market} @ {offer.odds}."))
                continue
            seen.add(key)
            batch.offers.append(
                VerifiedOffer(
                    offer=offer,
                    observed_at=observed_at,
                    age_seconds=max(age_seconds, 0) if age_seconds is not None else None,
                    fresh=fresh if observed_at is not None else None,
                    source=source,
                    raw=raw,
                )
            )

        return batch

    @staticmethod
    def as_conversion_offers(batch: OfferBatch) -> list[TargetOffer]:
        return [item.offer for item in batch.offers]

    @staticmethod
    def _observed(value, *, now: datetime) -> tuple[str | None, int | None]:
        if value is None or str(value).strip() == "":
            return None, None
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None, None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        age = int((now - dt).total_seconds())
        return dt.isoformat(), age

    @staticmethod
    def _text(value) -> str | None:
        text = str(value).strip() if value is not None else ""
        return text or None

    @staticmethod
    def _norm(value: str) -> str:
        return "".join(ch for ch in value.casefold() if ch.isalnum())

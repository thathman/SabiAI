from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
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
    source: str


@dataclass(slots=True)
class OfferBatch:
    target_bookmaker_slug: str
    offers: list[VerifiedOffer] = field(default_factory=list)
    issues: list[OfferIssue] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return bool(self.offers) and not any(issue.level == "error" for issue in self.issues)


class BookmakerOfferService:
    """Normalize browser/adapter market-search results before conversion uses them."""

    def __init__(self, bookmakers: BookmakerRegistry | None = None):
        self.bookmakers = bookmakers or default_bookmakers()

    def normalize(
        self,
        *,
        target_bookmaker: str,
        rows: Iterable[dict],
        source: str = "openclaw_browser",
    ) -> OfferBatch:
        target = self.bookmakers.resolve(target_bookmaker)
        if target is None:
            raise ValueError(f"Unknown target bookmaker: {target_bookmaker}")

        batch = OfferBatch(target_bookmaker_slug=target.slug)
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

            observed_at = self._timestamp(raw.get("observed_at"))
            if raw.get("observed_at") and observed_at is None:
                batch.issues.append(
                    OfferIssue(index, "warning", f"{event} — {market}: observed_at could not be parsed; recheck price freshness before building.")
                )

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
                    source=source,
                )
            )

        return batch

    @staticmethod
    def as_conversion_offers(batch: OfferBatch) -> list[TargetOffer]:
        return [item.offer for item in batch.offers]

    @staticmethod
    def _timestamp(value) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _text(value) -> str | None:
        text = str(value).strip() if value is not None else ""
        return text or None

    @staticmethod
    def _norm(value: str) -> str:
        return "".join(ch for ch in value.casefold() if ch.isalnum())

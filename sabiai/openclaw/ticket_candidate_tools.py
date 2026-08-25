from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

from sabiai.bookmakers import BookmakerOfferService
from sabiai.tickets import VerifiedReplacement, VerifiedVariantService

from .helpers import ticket_from_args
from .serializers import draft_to_dict, ticket_to_dict


class TicketCandidateTools:
    def __init__(self, app):
        self.app = app
        self.offer_service = BookmakerOfferService(app.bookmakers)
        self.variants = VerifiedVariantService(app.market_interpreter, app.ticket_workshop)

    def handlers(self) -> dict:
        return {
            "ticket.higher_odds.from_verified_offers": self.higher_odds,
            "ticket.candidates.compare": self.compare,
        }

    def higher_odds(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        bookmaker_name = str(args.get("target_bookmaker") or args.get("bookmaker") or "").strip()
        rows = args.get("replacements")
        if not bookmaker_name:
            raise ValueError("ticket.higher_odds.from_verified_offers needs target_bookmaker.")
        if not isinstance(rows, list) or not rows:
            raise ValueError("ticket.higher_odds.from_verified_offers needs replacements as a non-empty list.")

        batch = self.offer_service.normalize(
            target_bookmaker=bookmaker_name,
            rows=rows,
            source=str(args.get("source") or "openclaw_browser"),
            require_fresh=True,
            max_age_seconds=int(args.get("max_age_seconds", 180)),
        )
        if not batch.offers:
            return {
                "ready": False,
                "issues": [asdict(issue) for issue in batch.issues],
                "reason": "No fresh verified replacement prices survived validation.",
            }

        replacements: list[VerifiedReplacement] = []
        for item in batch.offers:
            leg_id = str(item.raw.get("leg_id") or "").strip()
            if not leg_id:
                raise ValueError("Every replacement offer needs leg_id so Sabi Boy knows exactly which ticket leg may change.")
            replacements.append(
                VerifiedReplacement(
                    leg_id=leg_id,
                    event=item.offer.event,
                    market=item.offer.market,
                    odds=Decimal(str(item.offer.odds)),
                    bookmaker=item.offer.bookmaker_slug,
                    observed_at=str(item.observed_at),
                    home=item.offer.home,
                    away=item.offer.away,
                    note=item.raw.get("note"),
                )
            )

        child, changes = self.variants.higher_odds(
            ticket,
            replacements,
            require_increase=bool(args.get("require_increase", True)),
        )
        draft = None
        parent_draft_id = str(args.get("draft_id") or "").strip() or None
        if bool(args.get("save_draft", True)):
            target = self.app.bookmakers.resolve(bookmaker_name)
            draft_obj = self.app._draft_store().create(
                {
                    "ticket": ticket_to_dict(child),
                    "changes": [asdict(change) for change in changes],
                    "freshness_issues": [asdict(issue) for issue in batch.issues],
                },
                source_type="higher_odds_variant",
                source_reference=parent_draft_id or ticket.source_reference or ticket.id,
                source_bookmaker_slug=(target.slug if target else bookmaker_name.casefold()),
                target_bookmaker_slug=(target.slug if target else bookmaker_name.casefold()),
                status="draft",
                issues=[asdict(issue) for issue in batch.issues],
                parent_draft_id=parent_draft_id,
            )
            draft = draft_to_dict(draft_obj)
        return {
            "ready": True,
            "original_combined_odds": str(ticket.combined_odds),
            "new_combined_odds": str(child.combined_odds),
            "ticket": ticket_to_dict(child),
            "changes": [asdict(change) for change in changes],
            "issues": [asdict(issue) for issue in batch.issues],
            "draft": draft,
        }

    def compare(self, args: dict) -> dict:
        base_args = args.get("base")
        if not isinstance(base_args, dict):
            # Also support the normal top-level legs/draft_id shape for the base ticket.
            base_args = args
        base = ticket_from_args(self.app, base_args)
        raw_candidates = args.get("candidates")
        if not isinstance(raw_candidates, list) or not raw_candidates:
            raise ValueError("ticket.candidates.compare needs a non-empty candidates list.")
        candidates = []
        for index, raw in enumerate(raw_candidates, start=1):
            if not isinstance(raw, dict):
                raise ValueError("Each candidate must be an object containing legs or draft_id.")
            label = str(raw.get("label") or f"Candidate {index}")
            candidates.append((label, ticket_from_args(self.app, raw)))
        summaries = self.variants.compare(base, candidates)
        return {
            "base": {
                "ticket_id": base.id,
                "leg_count": len(base.legs),
                "combined_odds": str(base.combined_odds),
            },
            "candidates": [asdict(row) for row in summaries],
            "note": "Candidates are ordered by combined decimal odds, not by a claim that the highest-odds version is preferable.",
        }

from __future__ import annotations

from dataclasses import asdict

from sabiai.bookmakers import BookmakerBrowserProfiles, BookmakerOfferService, TargetOffer
from sabiai.storage import OfferObservationStore
from sabiai.system import SystemReadinessService
from sabiai.tickets import RebuiltTicketVerificationService, RestoredSlipService

from .helpers import bookmaker_slug, ticket_from_args
from .serializers import conversion_to_dict, draft_to_dict, json_value, ticket_to_dict


class BookmakerTools:
    def __init__(self, app):
        self.app = app
        self.browser_profiles = BookmakerBrowserProfiles()
        self.offer_service = BookmakerOfferService(app.bookmakers)
        self.rebuilt_verifier = RebuiltTicketVerificationService()

    def handlers(self) -> dict:
        return {
            "bookmaker.resolve": self.resolve,
            "bookmaker.capabilities": self.capabilities,
            "bookmaker.browser.playbook": self.browser_playbook,
            "bookmaker.market_search.playbook": self.market_search_playbook,
            "bookmaker.market_search.ingest": self.market_search_ingest,
            "bookmaker.market_search.recent": self.market_search_recent,
            "bookmaker.booking_code.import_plan": self.booking_code_import_plan,
            "bookmaker.booking_code.restore": self.booking_code_restore,
            "bookmaker.search.plan": self.search_plan,
            "bookmaker.convert.plan": self.convert_plan,
            "bookmaker.convert.from_search": self.convert_from_search,
            "bookmaker.build.plan": self.build_plan,
            "bookmaker.build.execute": self.build_execute,
            "bookmaker.build.verify": self.build_verify,
        }

    def resolve(self, args: dict) -> dict:
        bookmaker = self.app.bookmakers.resolve(str(args.get("name", "")))
        if bookmaker is None:
            return {"found": False, "name": args.get("name")}
        adapter = self.app.bookmaker_adapters.get(bookmaker.slug)
        profile = self.browser_profiles.get(bookmaker.slug)
        market_profile = self.browser_profiles.market_search(bookmaker.slug)
        proven = sorted(cap.value for cap in adapter.capabilities()) if adapter else []
        return {
            "found": True,
            "id": bookmaker.id,
            "name": bookmaker.name,
            "slug": bookmaker.slug,
            "proven_capabilities": proven,
            "browser_restore_verified": bool(profile and profile.public_restore and profile.entry_url),
            "browser_market_search_verified": bool(market_profile and market_profile.ready and market_profile.entry_url),
        }

    def capabilities(self, args: dict) -> dict:
        name = args.get("name")
        if name:
            bookmaker = self.app.bookmakers.resolve(str(name))
            if bookmaker is None:
                return {"found": False, "name": name}
            adapter = self.app.bookmaker_adapters.get(bookmaker.slug)
            profile = self.browser_profiles.get(bookmaker.slug)
            market_profile = self.browser_profiles.market_search(bookmaker.slug)
            return {
                "found": True,
                "bookmaker": bookmaker.name,
                "slug": bookmaker.slug,
                "adapter": json_value(adapter.status()) if adapter else None,
                "browser_playbook": json_value(profile) if profile else None,
                "market_search_playbook": json_value(market_profile) if market_profile else None,
            }
        rows = []
        for bookmaker in self.app.bookmakers.all():
            adapter = self.app.bookmaker_adapters.get(bookmaker.slug)
            profile = self.browser_profiles.get(bookmaker.slug)
            market_profile = self.browser_profiles.market_search(bookmaker.slug)
            rows.append(
                {
                    "bookmaker": bookmaker.name,
                    "slug": bookmaker.slug,
                    "adapter": json_value(adapter.status()) if adapter else None,
                    "browser_restore_verified": bool(profile and profile.public_restore and profile.entry_url),
                    "browser_verified_on": profile.verified_on if profile else None,
                    "browser_market_search_verified": bool(
                        market_profile and market_profile.ready and market_profile.entry_url
                    ),
                    "market_search_verified_on": market_profile.verified_on if market_profile else None,
                }
            )
        return {"bookmakers": rows}

    def browser_playbook(self, args: dict) -> dict:
        bookmaker = self.app.bookmakers.resolve(str(args.get("bookmaker") or args.get("name") or ""))
        if bookmaker is None:
            return {"found": False, "name": args.get("bookmaker") or args.get("name")}
        profile = self.browser_profiles.get(bookmaker.slug)
        return {
            "found": profile is not None,
            "bookmaker": bookmaker.name,
            "slug": bookmaker.slug,
            "playbook": json_value(profile) if profile else None,
        }

    def market_search_playbook(self, args: dict) -> dict:
        bookmaker = self.app.bookmakers.resolve(str(args.get("bookmaker") or args.get("name") or ""))
        if bookmaker is None:
            return {"found": False, "name": args.get("bookmaker") or args.get("name")}
        profile = self.browser_profiles.market_search(bookmaker.slug)
        return {
            "found": profile is not None,
            "ready": bool(profile and profile.ready),
            "bookmaker": bookmaker.name,
            "slug": bookmaker.slug,
            "playbook": json_value(profile) if profile else None,
        }

    def market_search_ingest(self, args: dict) -> dict:
        target = str(args.get("target_bookmaker") or args.get("bookmaker") or "").strip()
        rows = args.get("offers")
        if not target:
            raise ValueError("bookmaker.market_search.ingest needs target_bookmaker.")
        if not isinstance(rows, list):
            raise ValueError("bookmaker.market_search.ingest needs offers as a list.")
        batch = self.offer_service.normalize(
            target_bookmaker=target,
            rows=rows,
            source=str(args.get("source") or "openclaw_browser"),
            require_fresh=bool(args.get("require_fresh", False)),
            max_age_seconds=int(args.get("max_age_seconds", 180)),
        )
        observations = self._persist_offer_batch(
            batch,
            source_draft_id=self._source_draft_id(args),
        ) if bool(args.get("persist", True)) else []
        data = self._offer_batch(batch)
        data["observations"] = observations
        return data

    def market_search_recent(self, args: dict) -> dict:
        bookmaker = str(args.get("bookmaker") or "").strip()
        slug = None
        if bookmaker:
            resolved = self.app.bookmakers.resolve(bookmaker)
            if resolved is None:
                raise ValueError(f"Unknown bookmaker: {bookmaker}")
            slug = resolved.slug
        rows = OfferObservationStore(self.app._db(initialize=True)).recent(
            bookmaker_slug=slug,
            limit=int(args.get("limit", 100)),
        )
        return {"offers": [json_value(row) for row in rows]}

    def booking_code_import_plan(self, args: dict) -> dict:
        plan = self.app.bookmaker_execution.import_booking_code(
            bookmaker=str(args.get("bookmaker", "")),
            booking_code=str(args.get("booking_code", "")),
        )
        return json_value(plan)

    def booking_code_restore(self, args: dict) -> dict:
        bookmaker = str(args.get("bookmaker") or "").strip()
        booking_code = str(args.get("booking_code") or "").strip()
        payload = args.get("payload")
        if not bookmaker:
            raise ValueError("bookmaker.booking_code.restore needs bookmaker.")
        if not isinstance(payload, dict):
            raise ValueError("bookmaker.booking_code.restore needs the structured browser-restored payload.")

        result = RestoredSlipService(self.app.ticket_normalizer).normalize(
            bookmaker=bookmaker,
            booking_code=booking_code,
            payload=payload,
        )
        issues = [asdict(issue) for issue in result.issues]
        draft = None
        if result.usable and bool(args.get("save_draft", True)):
            draft_obj = self.app._draft_store().create(
                ticket_to_dict(result.ticket),
                source_type="booking_code",
                source_reference=f"{bookmaker}:{booking_code}",
                source_bookmaker_slug=bookmaker_slug(self.app, bookmaker),
                status="restored",
                issues=issues,
            )
            draft = draft_to_dict(draft_obj)

        return {
            "usable": result.usable,
            "bookmaker": result.bookmaker,
            "booking_code": result.booking_code,
            "ticket": ticket_to_dict(result.ticket),
            "issues": issues,
            "reported_leg_count": result.reported_leg_count,
            "reported_combined_odds": str(result.reported_combined_odds) if result.reported_combined_odds is not None else None,
            "computed_combined_odds": str(result.computed_combined_odds),
            "combined_odds_match": result.combined_odds_match,
            "draft": draft,
        }

    def search_plan(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        target = str(args.get("target_bookmaker") or "")
        bookmaker = self.app.bookmakers.resolve(target)
        if bookmaker is None:
            raise ValueError(f"Unknown target bookmaker: {target}")
        plan = self.app.bookmaker_discovery.plan_conversion(
            ticket,
            target_bookmaker=target,
        )
        data = json_value(plan)
        market_profile = self.browser_profiles.market_search(bookmaker.slug)
        data["browser_playbook"] = json_value(market_profile) if market_profile else None
        data["browser_ready"] = bool(market_profile and market_profile.ready and market_profile.entry_url)
        if not data["browser_ready"]:
            data.setdefault("notes", []).append(
                f"{bookmaker.name} does not yet have a verified V2 public market-search browser playbook."
            )
        return data

    def convert_plan(self, args: dict) -> dict:
        source_ticket = ticket_from_args(self.app, args)
        target_name = str(args.get("target_bookmaker", ""))
        target = self.app.bookmakers.resolve(target_name)
        if target is None:
            raise ValueError(f"Unknown target bookmaker: {target_name}")

        offers = [
            TargetOffer(
                event=str(raw["event"]),
                market=str(raw.get("market") or raw.get("pick") or ""),
                odds=raw["odds"],
                bookmaker_slug=str(raw.get("bookmaker_slug") or target.slug),
                event_ref=raw.get("event_ref"),
                market_ref=raw.get("market_ref"),
                home=raw.get("home"),
                away=raw.get("away"),
                sport=raw.get("sport"),
            )
            for raw in args.get("target_offers", [])
        ]
        return self._convert_ticket(
            source_ticket,
            target_name=target.name,
            offers=offers,
            source_bookmaker=args.get("bookmaker"),
        )

    def convert_from_search(self, args: dict) -> dict:
        source_ticket = ticket_from_args(self.app, args)
        target_name = str(args.get("target_bookmaker") or "").strip()
        rows = args.get("offers")
        if not target_name:
            raise ValueError("bookmaker.convert.from_search needs target_bookmaker.")
        if not isinstance(rows, list):
            raise ValueError("bookmaker.convert.from_search needs offers as a list.")

        source_draft_id = self._source_draft_id(args)
        max_age_seconds = int(args.get("max_age_seconds", 180))
        batch = self.offer_service.normalize(
            target_bookmaker=target_name,
            rows=rows,
            source=str(args.get("source") or "openclaw_browser"),
            require_fresh=True,
            max_age_seconds=max_age_seconds,
        )
        observations = self._persist_offer_batch(batch, source_draft_id=source_draft_id)
        search = self._offer_batch(batch)
        search["observations"] = observations
        if not batch.offers:
            return {
                "ready": False,
                "search": search,
                "conversion": None,
                "draft": None,
                "reason": "No fresh valid target-bookmaker offers survived browser-result validation.",
            }
        conversion = self._convert_ticket(
            source_ticket,
            target_name=target_name,
            offers=self.offer_service.as_conversion_offers(batch),
            source_bookmaker=args.get("bookmaker"),
        )

        draft = None
        if conversion.get("ready") and bool(args.get("save_draft", True)):
            target = self.app.bookmakers.resolve(target_name)
            source_book = bookmaker_slug(self.app, str(args.get("bookmaker") or "")) if args.get("bookmaker") else None
            payload = {
                "ticket": conversion.get("target_ticket"),
                "conversion": conversion,
                "price_observations": observations,
                "price_max_age_seconds": max_age_seconds,
            }
            draft_obj = self.app._draft_store().create(
                payload,
                source_type="conversion",
                source_reference=source_draft_id or source_ticket.source_reference or source_ticket.id,
                source_bookmaker_slug=source_book,
                target_bookmaker_slug=target.slug if target else target_name,
                status="converted",
                issues=search.get("issues", []),
                parent_draft_id=source_draft_id,
            )
            draft = draft_to_dict(draft_obj)

        return {
            "ready": bool(conversion.get("ready")),
            "search": search,
            "conversion": conversion,
            "draft": draft,
        }

    def _convert_ticket(
        self,
        source_ticket,
        *,
        target_name: str,
        offers: list[TargetOffer],
        source_bookmaker=None,
    ) -> dict:
        target = self.app.bookmakers.resolve(target_name)
        if target is None:
            raise ValueError(f"Unknown target bookmaker: {target_name}")
        source_book = None
        if source_bookmaker:
            resolved = self.app.bookmakers.resolve(str(source_bookmaker))
            source_book = resolved.slug if resolved else str(source_bookmaker)
        plan = self.app.ticket_converter.plan(
            source_ticket,
            target_bookmaker=target.name,
            offers=offers,
            source_bookmaker_slug=source_book,
        )
        return conversion_to_dict(plan)

    def build_plan(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        target = self._build_target(args)
        return json_value(self.app.bookmaker_execution.build(ticket, bookmaker=target))

    def build_execute(self, args: dict) -> dict:
        readiness = SystemReadinessService(self.app._db(initialize=True)).assess()
        if not readiness.can_build_ticket:
            return {
                "executed": False,
                "reason": f"Sabi Boy is currently {readiness.label}; ticket-building execution is paused.",
                "readiness": json_value(readiness),
            }

        ticket = ticket_from_args(self.app, args)
        target = self._build_target(args)
        plan = self.app.bookmaker_execution.build(ticket, bookmaker=target)
        result = self.app.bookmaker_runner.execute(
            plan,
            repo_root=self.app.settings.repo_root,
            dry_run=bool(args.get("dry_run", False)),
            timeout_seconds=int(args.get("timeout_seconds", 120)),
        )
        return {
            "executed": True,
            "plan": json_value(plan),
            "result": json_value(result),
        }

    def _build_target(self, args: dict) -> str:
        target = str(args.get("target_bookmaker") or args.get("bookmaker") or "").strip()
        if target or not args.get("draft_id"):
            return target
        draft = self.app._draft_store().get(str(args["draft_id"]))
        if draft is None:
            return ""
        return str(draft.target_bookmaker_slug or draft.source_bookmaker_slug or "")

    def build_verify(self, args: dict) -> dict:
        bookmaker = str(args.get("bookmaker") or args.get("target_bookmaker") or "").strip()
        booking_code = str(args.get("booking_code") or "").strip()
        payload = args.get("payload")
        if not bookmaker or not booking_code:
            raise ValueError("bookmaker.build.verify needs bookmaker and booking_code.")
        if not isinstance(payload, dict):
            raise ValueError("bookmaker.build.verify needs the structured browser-restored payload for the newly built booking code.")

        expected_draft_id = str(args.get("expected_draft_id") or args.get("draft_id") or "").strip()
        expected_payload = None
        expected_draft = None
        if expected_draft_id:
            expected_draft = self.app._draft_store().get(expected_draft_id)
            if expected_draft is None:
                raise ValueError(f"Unknown expected conversion draft: {expected_draft_id}")
            expected_payload = expected_draft.payload.get("ticket") if isinstance(expected_draft.payload, dict) else None
            if expected_payload is None and isinstance(expected_draft.payload, dict):
                expected_payload = expected_draft.payload
        if expected_payload is None:
            expected_payload = {"legs": args.get("expected_legs") or args.get("legs") or []}

        expected_legs = expected_payload.get("legs") if isinstance(expected_payload, dict) else None
        if not isinstance(expected_legs, list) or not expected_legs:
            raise ValueError("Expected converted ticket has no legs to verify.")
        expected_norm = self.app.ticket_normalizer.normalize(
            expected_legs,
            bookmaker=bookmaker,
            source_type="build_plan",
            source_reference=expected_draft_id or None,
        )
        expected_errors = [issue.message for issue in expected_norm.issues if issue.level == "error"]
        if expected_errors:
            raise ValueError("Expected ticket cannot be normalized: " + "; ".join(expected_errors))

        restored = RestoredSlipService(self.app.ticket_normalizer).normalize(
            bookmaker=bookmaker,
            booking_code=booking_code,
            payload=payload,
        )
        verification = self.rebuilt_verifier.verify(expected_norm.ticket, restored.ticket)
        data = json_value(verification)
        data["booking_code"] = booking_code
        data["bookmaker"] = bookmaker
        data["restored_issues"] = [asdict(issue) for issue in restored.issues]
        data["restored_combined_odds"] = str(restored.computed_combined_odds)
        data["reported_combined_odds"] = (
            str(restored.reported_combined_odds) if restored.reported_combined_odds is not None else None
        )

        verified_draft = None
        if verification.structure_verified and expected_draft is not None and bool(args.get("save_draft", True)):
            revised_payload = dict(expected_draft.payload)
            revised_payload["booking_code"] = booking_code
            revised_payload["verification"] = data
            revised_payload["restored_ticket"] = ticket_to_dict(restored.ticket)
            draft_obj = self.app._draft_store().revise(
                expected_draft.id,
                revised_payload,
                issues=[asdict(issue) for issue in restored.issues],
                status="verified_built",
                target_bookmaker_slug=bookmaker_slug(self.app, bookmaker),
            )
            verified_draft = draft_to_dict(draft_obj)

        return {
            "verified": verification.structure_verified,
            "ready_to_return_code": verification.ready_to_return_code,
            "prices_changed": verification.prices_changed,
            "verification": data,
            "draft": verified_draft,
        }

    def _persist_offer_batch(self, batch, *, source_draft_id: str | None) -> list[dict]:
        store = OfferObservationStore(self.app._db(initialize=True))
        observations = []
        for item in batch.offers:
            if not item.observed_at:
                continue
            offer = item.offer
            row = store.save(
                target_bookmaker_slug=batch.target_bookmaker_slug,
                sport=offer.sport,
                event=offer.event,
                home=offer.home,
                away=offer.away,
                event_ref=offer.event_ref,
                market=offer.market,
                market_ref=offer.market_ref,
                decimal_odds=str(offer.odds),
                observed_at=item.observed_at,
                source=item.source,
                source_draft_id=source_draft_id,
                raw=item.raw,
            )
            observations.append(json_value(row))
        return observations

    def _source_draft_id(self, args: dict) -> str | None:
        draft_id = str(args.get("source_draft_id") or args.get("draft_id") or "").strip()
        if not draft_id:
            return None
        if self.app._draft_store().get(draft_id) is None:
            raise ValueError(f"Unknown source ticket draft: {draft_id}")
        return draft_id

    @staticmethod
    def _offer_batch(batch) -> dict:
        return {
            "usable": batch.usable,
            "target_bookmaker_slug": batch.target_bookmaker_slug,
            "freshness_required": batch.freshness_required,
            "max_age_seconds": batch.max_age_seconds,
            "offers": [
                {
                    "event": item.offer.event,
                    "market": item.offer.market,
                    "odds": str(item.offer.odds),
                    "bookmaker_slug": item.offer.bookmaker_slug,
                    "event_ref": item.offer.event_ref,
                    "market_ref": item.offer.market_ref,
                    "home": item.offer.home,
                    "away": item.offer.away,
                    "sport": item.offer.sport,
                    "observed_at": item.observed_at,
                    "age_seconds": item.age_seconds,
                    "fresh": item.fresh,
                    "source": item.source,
                }
                for item in batch.offers
            ],
            "issues": [asdict(issue) for issue in batch.issues],
        }

from __future__ import annotations

from sabiai.sports import FormService

from .sports_tools import SportsTools


class SportsInsightTools:
    """Human-facing form/H2H/availability summaries built from provider-safe lookups."""

    def __init__(self, app):
        self.app = app
        self.lookup = SportsTools(app)
        self.form = FormService()

    def handlers(self) -> dict:
        return {
            "sports.form_summary": self.form_summary,
            "sports.compare_form_summary": self.compare_form_summary,
            "sports.h2h": self.h2h,
            "sports.injury_summary": self.injury_summary,
            "sports.match_snapshot": self.match_snapshot,
        }

    def form_summary(self, args: dict) -> dict:
        team = str(args.get("team") or "").strip()
        if not team:
            raise ValueError("sports.form_summary needs team.")
        lookup = self.lookup.team_form(args)
        limit = int(args.get("limit", 10))
        summary = self.form.summarize(team, lookup.get("sources", []), limit=limit)
        venue = str(args.get("venue") or "").strip().casefold()
        if venue:
            if venue not in {"home", "away"}:
                raise ValueError("venue must be home or away.")
            summary = self._venue_summary(summary, venue=venue, limit=limit)
        return {
            "team": team,
            "sport": args.get("sport"),
            "venue": venue or "all",
            "summary": summary,
            "complete": lookup.get("complete", False),
            "needs_more_sources": lookup.get("needs_more_sources", False),
            "sources": lookup.get("sources", []),
            "failures": lookup.get("failures", []),
            "note": lookup.get("note"),
        }

    def compare_form_summary(self, args: dict) -> dict:
        home = str(args.get("home") or "").strip()
        away = str(args.get("away") or "").strip()
        if not home or not away:
            raise ValueError("sports.compare_form_summary needs explicit home and away team names.")
        shared = dict(args)
        shared.pop("home", None)
        shared.pop("away", None)
        home_result = self.form_summary({"team": home, **shared})
        away_result = self.form_summary({"team": away, **shared})

        home_venue = self.form_summary({"team": home, "venue": "home", **shared})
        away_venue = self.form_summary({"team": away, "venue": "away", **shared})
        return {
            "home_team": home,
            "away_team": away,
            "overall": {
                "home": home_result,
                "away": away_result,
            },
            "venue_specific": {
                "home_team_at_home": home_venue,
                "away_team_away": away_venue,
            },
            "complete": bool(home_result.get("complete") and away_result.get("complete")),
            "plain": (
                f"{home}: {home_result['summary']['form']} overall; {home_venue['summary']['form']} at home. "
                f"{away}: {away_result['summary']['form']} overall; {away_venue['summary']['form']} away."
            ),
        }

    def h2h(self, args: dict) -> dict:
        home = str(args.get("home") or "").strip()
        away = str(args.get("away") or "").strip()
        if not home or not away:
            raise ValueError("sports.h2h needs explicit home and away team names.")

        lookup_args = dict(args)
        lookup_args.pop("home", None)
        lookup_args.pop("away", None)
        lookup_args["team"] = home
        lookup_args["limit"] = max(int(args.get("limit", 10)), int(args.get("form_scan_limit", 25)))
        lookup = self.lookup.team_form(lookup_args)
        h2h = self.form.head_to_head(
            home,
            away,
            lookup.get("sources", []),
            limit=int(args.get("limit", 10)),
        )
        return {
            **h2h,
            "coverage": "recent_available_history",
            "complete_history": False,
            "sources": lookup.get("sources", []),
            "failures": lookup.get("failures", []),
            "note": (
                "This is recent H2H found in the available free-source schedule window, not a claim of complete all-time history. "
                "Use the Research Scout/official archives when older meetings matter."
            ),
        }

    def injury_summary(self, args: dict) -> dict:
        team = str(args.get("team") or "").strip()
        if not team:
            raise ValueError("sports.injury_summary needs team.")
        lookup = self.lookup.team_injuries(args)
        rows: list[dict] = []
        for source_item in lookup.get("sources", []):
            source = source_item.get("source")
            response = source_item.get("response") or {}
            payload = response.get("payload") if isinstance(response, dict) else None
            raw = payload.get("raw") if isinstance(payload, dict) else None
            injuries = raw.get("injuries") if isinstance(raw, dict) else None
            if not isinstance(injuries, list):
                continue
            for item in injuries:
                if not isinstance(item, dict):
                    continue
                athlete = item.get("athlete") if isinstance(item.get("athlete"), dict) else {}
                name = str(
                    athlete.get("displayName")
                    or athlete.get("fullName")
                    or item.get("name")
                    or item.get("player")
                    or "Unknown player"
                ).strip()
                status = item.get("status")
                if isinstance(status, dict):
                    status = status.get("name") or status.get("type") or status.get("description")
                detail = (
                    item.get("details")
                    or item.get("detail")
                    or item.get("description")
                    or item.get("type")
                )
                rows.append(
                    {
                        "player": name,
                        "status": str(status or "Listed").strip(),
                        "detail": str(detail).strip() if detail else None,
                        "source": source,
                    }
                )
        return {
            "team": team,
            "listed": len(rows),
            "players": rows,
            "complete": False,
            "needs_official_confirmation": True,
            "failures": lookup.get("failures", []),
            "plain": (
                f"{team}: no players were listed in the available public injury feed."
                if not rows
                else f"{team}: {len(rows)} player(s) listed in the available public injury feed."
            ),
            "note": lookup.get("note"),
        }

    def match_snapshot(self, args: dict) -> dict:
        """Gather the standard pre-play research picture without making a betting decision."""
        home = str(args.get("home") or "").strip()
        away = str(args.get("away") or "").strip()
        sport = str(args.get("sport") or "").strip()
        market = str(args.get("market") or "").strip() or None
        if not home or not away:
            raise ValueError("sports.match_snapshot needs explicit home and away team names.")
        if not sport:
            raise ValueError("sports.match_snapshot needs sport.")

        sections: dict[str, dict | None] = {}
        errors: dict[str, str] = {}

        def capture(name: str, fn):
            try:
                sections[name] = fn()
            except Exception as exc:
                sections[name] = None
                errors[name] = str(exc)

        capture("form", lambda: self.compare_form_summary(args))
        capture("h2h", lambda: self.h2h(args))
        capture("home_injuries", lambda: self.injury_summary({"team": home, **args}))
        capture("away_injuries", lambda: self.injury_summary({"team": away, **args}))

        plan = self.app.research_planner.plan(
            sport,
            market_text=market,
            home=home,
            away=away,
        )
        still_to_check: list[str] = []
        if errors:
            still_to_check.append("Retry or replace any research section that could not be loaded from the current free sources.")
        still_to_check.append("Confirm important absences/lineups with a current official team/league source or fresh reputable reporting.")
        if market:
            still_to_check.extend(plan.market_focus)
        if plan.needs_source_discovery:
            still_to_check.append("Confirm the sport/competition rules and identify reliable sources before relying on the research.")

        plain_parts = [f"{home} vs {away} — {sport}."]
        form_section = sections.get("form")
        if isinstance(form_section, dict) and form_section.get("plain"):
            plain_parts.append(str(form_section["plain"]))
        home_injuries = sections.get("home_injuries")
        away_injuries = sections.get("away_injuries")
        if isinstance(home_injuries, dict):
            plain_parts.append(str(home_injuries.get("plain")))
        if isinstance(away_injuries, dict):
            plain_parts.append(str(away_injuries.get("plain")))

        return {
            "sport": sport,
            "home_team": home,
            "away_team": away,
            "market": market,
            "plain": " ".join(part for part in plain_parts if part),
            "sections": sections,
            "errors": errors,
            "research_checklist": list(plan.checklist),
            "market_specific_checks": list(plan.market_focus),
            "still_to_check": list(dict.fromkeys(still_to_check)),
            "ready_for_decision": not errors and bool(sections.get("form")),
            "note": "This snapshot assembles research evidence. Sabi Boy still decides separately whether the evidence and current bookmaker price justify BET, WATCH, WAIT, PASS or REJECT.",
        }

    @staticmethod
    def _venue_summary(summary: dict, *, venue: str, limit: int) -> dict:
        games = [game for game in summary.get("games", []) if game.get("venue") == venue][:limit]
        wins = sum(1 for game in games if game.get("result") == "W")
        draws = sum(1 for game in games if game.get("result") == "D")
        losses = sum(1 for game in games if game.get("result") == "L")
        known = [game.get("result") for game in games if game.get("result") in {"W", "D", "L"}]
        return {
            "team": summary.get("team"),
            "venue": venue,
            "played": len(games),
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "form": "-".join(known) if known else "—",
            "games": games,
        }

from __future__ import annotations

from sabiai.sports import FormService

from .sports_tools import SportsTools


class SportsInsightTools:
    """Human-facing form/H2H summaries built from provider-safe sports lookups."""

    def __init__(self, app):
        self.lookup = SportsTools(app)
        self.form = FormService()

    def handlers(self) -> dict:
        return {
            "sports.form_summary": self.form_summary,
            "sports.compare_form_summary": self.compare_form_summary,
            "sports.h2h": self.h2h,
        }

    def form_summary(self, args: dict) -> dict:
        team = str(args.get("team") or "").strip()
        if not team:
            raise ValueError("sports.form_summary needs team.")
        lookup = self.lookup.team_form(args)
        limit = int(args.get("limit", 10))
        summary = self.form.summarize(team, lookup.get("sources", []), limit=limit)
        return {
            "team": team,
            "sport": args.get("sport"),
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
        return {
            "home_team": home,
            "away_team": away,
            "home": home_result,
            "away": away_result,
            "complete": bool(home_result.get("complete") and away_result.get("complete")),
            "plain": (
                f"{home}: {home_result['summary']['form']} ({home_result['summary']['wins']}W, "
                f"{home_result['summary']['draws']}D, {home_result['summary']['losses']}L) | "
                f"{away}: {away_result['summary']['form']} ({away_result['summary']['wins']}W, "
                f"{away_result['summary']['draws']}D, {away_result['summary']['losses']}L)"
            ),
        }

    def h2h(self, args: dict) -> dict:
        home = str(args.get("home") or "").strip()
        away = str(args.get("away") or "").strip()
        if not home or not away:
            raise ValueError("sports.h2h needs explicit home and away team names.")

        # Use the home side's provider-safe recent form feeds; H2H is intentionally labelled
        # as a recent-meetings view because free public schedule coverage varies by competition.
        lookup_args = dict(args)
        lookup_args.pop("home", None)
        lookup_args.pop("away", None)
        lookup_args["team"] = home
        # Give the source enough recent games to find repeated meetings where available.
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

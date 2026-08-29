from __future__ import annotations

from dataclasses import dataclass

from sabiai.domain.types import MarketKind

from .arbitrage import SettlementRules


@dataclass(frozen=True, slots=True)
class SettlementProfile:
    sport: str
    market_kind: str
    rules: SettlementRules
    verification_required: bool
    verification_topics: tuple[str, ...]
    note: str


class SettlementRuleLibrary:
    """Conservative structural rules for every proactive engine sport.

    These defaults protect market equivalence. They never replace the target bookmaker's
    current published settlement rules where retirement, dead heat, overtime or interruption
    handling can differ.
    """

    def profile(
        self,
        sport: str,
        market_kind: MarketKind | str,
        *,
        period: str = "full_event",
        line_key: str | None = None,
    ) -> SettlementProfile:
        sport_key = str(sport or "").strip().casefold().replace("_", " ")
        kind = market_kind.value if isinstance(market_kind, MarketKind) else str(market_kind or "").strip().casefold()
        period_key = str(period or "full_event").strip().casefold()

        if sport_key in {"football", "soccer", "futsal"}:
            return self._profile(sport_key, kind, period_key, line_key, includes_overtime=False,
                void="abandonment/postponement bookmaker rule must match",
                format_rule="regulation scope must match",
                topics=("abandonment/postponement", "extra-time scope"),
                note="Normal match markets are regulation-time unless the exact market says otherwise.")

        if sport_key in {"basketball", "baseball", "american football", "ice hockey", "hockey"}:
            overtime = period_key in {"full_event", "full_game", "full_match"}
            topics = ["overtime/extra-innings scope", "postponement/shortened-game rule"]
            if sport_key in {"ice hockey", "hockey"}:
                topics.append("three-way regulation vs two-way including overtime/shootout")
            if sport_key == "baseball":
                topics.append("listed-pitcher/start requirements")
            return self._profile(sport_key, kind, period_key, line_key, includes_overtime=overtime,
                void="shortened/postponed event rule must match",
                format_rule="event duration and overtime scope must match",
                topics=tuple(topics),
                note="Full-game markets often include overtime/extra innings, but exact duration and shortened-game rules must match.")

        if sport_key in {"tennis", "table tennis", "badminton", "padel", "beach volleyball"}:
            return self._profile(sport_key, kind, period_key, line_key, includes_overtime=None,
                void="walkover/withdrawal rule must match", retirement="bookmaker_specific",
                format_rule="best-of/set format must match",
                topics=("retirement", "walkover", "minimum completed sets/games", "format changes"),
                note="Do not treat prices as equivalent until retirement/walkover and completed-set rules match.")

        if sport_key == "golf":
            return self._profile(sport_key, kind, period_key, line_key, includes_overtime=None,
                void="withdrawal/cut rule must match", dead_heat="bookmaker_specific",
                format_rule="round/tournament/field scope must match",
                topics=("dead heat", "withdrawal", "cut", "reduced event", "round vs tournament scope"),
                note="Dead-heat and withdrawal handling can materially change settlement.")

        if sport_key in {
            "motorsport", "formula 1", "f1", "motogp", "cycling", "horse racing",
            "greyhound racing", "racing", "athletics", "winter sports",
        }:
            return self._profile(sport_key, kind, period_key, line_key, includes_overtime=None,
                void="start/non-runner/classification rule must match", dead_heat="bookmaker_specific",
                format_rule="classification/field/session scope must match",
                topics=("non-runner/DNS", "official classification", "dead heat", "event shortening/cancellation", "heat/stage/session scope"),
                note="Race/field markets require explicit start, classification and tie/non-runner rule matching.")

        if sport_key in {"mma", "boxing"}:
            return self._profile(sport_key, kind, period_key, line_key, includes_overtime=None,
                void="no-contest/draw/technical-decision rule must match",
                format_rule="scheduled rounds and method scope must match",
                topics=("draw/no contest", "technical decision", "round started/completed rule", "method classification"),
                note="Combat-sport method and round markets must match the bookmaker's draw/no-contest and round-completion definitions.")

        if sport_key in {"esports", "counter-strike", "cs2", "league of legends", "dota 2", "valorant"}:
            return self._profile(sport_key, kind, period_key, line_key, includes_overtime=None,
                void="forfeit/cancelled-map rule must match", retirement="not_applicable",
                format_rule="map/series/patch/format scope must match",
                topics=("forfeit", "map cancellation", "series-format change", "walkover", "overtime inclusion"),
                note="Map/series scope and forfeit/cancellation rules must be verified.")

        if sport_key == "cricket":
            return self._profile(sport_key, kind, period_key, line_key, includes_overtime=None,
                void="no-result/reduced-overs rule must match",
                format_rule="format/innings/overs scope must match",
                topics=("DLS/reduced overs", "no result", "super over inclusion", "player participation", "format"),
                note="Cricket markets require format and reduced-overs/no-result rule matching.")

        if sport_key in {
            "volleyball", "handball", "rugby", "rugby league", "darts", "snooker",
            "water polo", "floorball", "aussie rules",
        }:
            return self._profile(sport_key, kind, period_key, line_key, includes_overtime=None,
                void="event/format interruption rule must match",
                format_rule="set/frame/extra-period/event scope must match",
                topics=("event format", "abandonment/interruption", "extra period/tiebreak scope", "draw/tie handling"),
                note="Verify event format and interruption/extra-period rules before treating cross-book prices as equivalent.")

        return self._profile(sport_key or "unknown", kind or "unknown", period_key, line_key,
            includes_overtime=None, void="bookmaker_specific", format_rule="bookmaker_specific",
            topics=("event format", "void/cancellation", "tie/extra-time handling"),
            note="No trustworthy generic settlement rule exists yet; verify the target bookmaker explicitly.")

    @staticmethod
    def _profile(
        sport: str,
        kind: str,
        period: str,
        line_key: str | None,
        *,
        includes_overtime: bool | None,
        void: str,
        format_rule: str,
        topics: tuple[str, ...],
        note: str,
        retirement: str | None = None,
        dead_heat: str | None = None,
    ) -> SettlementProfile:
        return SettlementProfile(
            sport=sport,
            market_kind=kind,
            rules=SettlementRules(
                period=period,
                includes_overtime=includes_overtime,
                void_rule=void,
                line_key=line_key,
                retirement_rule=retirement,
                dead_heat_rule=dead_heat,
                format_rule=format_rule,
            ),
            verification_required=True,
            verification_topics=topics,
            note=note,
        )

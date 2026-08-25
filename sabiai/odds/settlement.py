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
    """Conservative baseline rule profiles for cross-book market equivalence.

    These are structural defaults, not substitutes for a bookmaker's published rules. Where
    retirement/dead-heat/forfeit behavior commonly varies, the profile explicitly requires a
    bookmaker-rule verification before cross-book execution.
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
            overtime = False if period_key in {"full_event", "regulation", "full_match"} else None
            return SettlementProfile(
                sport=sport_key,
                market_kind=kind,
                rules=SettlementRules(
                    period=period_key,
                    includes_overtime=overtime,
                    void_rule="abandonment/postponement bookmaker rule must match",
                    line_key=line_key,
                    format_rule="regulation scope must match",
                ),
                verification_required=True,
                verification_topics=("abandonment/postponement", "extra-time scope"),
                note="Treat normal football match markets as regulation-time only unless the exact market explicitly says otherwise; still verify bookmaker abandonment/postponement rules.",
            )

        if sport_key in {"basketball", "baseball", "american football", "ice hockey", "hockey"}:
            overtime = period_key in {"full_event", "full_game", "full_match"}
            topics = ["overtime/extra-innings scope", "postponement/shortened-game rule"]
            if sport_key in {"ice hockey", "hockey"}:
                topics.append("three-way regulation vs two-way including overtime/shootout")
            return SettlementProfile(
                sport=sport_key,
                market_kind=kind,
                rules=SettlementRules(
                    period=period_key,
                    includes_overtime=overtime,
                    void_rule="shortened/postponed event rule must match",
                    line_key=line_key,
                    format_rule="event duration and overtime scope must match",
                ),
                verification_required=True,
                verification_topics=tuple(topics),
                note="Full-game North American-style markets often include overtime/extra innings, but the exact market and shortened-game rule must match across books.",
            )

        if sport_key in {"tennis", "table tennis", "badminton", "padel"}:
            return SettlementProfile(
                sport=sport_key,
                market_kind=kind,
                rules=SettlementRules(
                    period=period_key,
                    includes_overtime=None,
                    void_rule="walkover/withdrawal rule must match",
                    line_key=line_key,
                    retirement_rule="bookmaker_specific",
                    format_rule="best-of/set format must match",
                ),
                verification_required=True,
                verification_topics=("retirement", "walkover", "minimum completed sets/games", "format changes"),
                note="Do not treat racquet-sport prices as equivalent until retirement/walkover and completed-set rules match.",
            )

        if sport_key in {"golf"}:
            return SettlementProfile(
                sport=sport_key,
                market_kind=kind,
                rules=SettlementRules(
                    period=period_key,
                    includes_overtime=None,
                    void_rule="withdrawal/cut rule must match",
                    line_key=line_key,
                    dead_heat_rule="bookmaker_specific",
                    format_rule="round/tournament/field scope must match",
                ),
                verification_required=True,
                verification_topics=("dead heat", "withdrawal", "cut", "reduced event", "round vs tournament scope"),
                note="Golf dead-heat and withdrawal handling can materially change settlement; verify the exact book rules.",
            )

        if sport_key in {"motorsport", "formula 1", "f1", "motogp", "cycling", "horse racing", "racing"}:
            return SettlementProfile(
                sport=sport_key,
                market_kind=kind,
                rules=SettlementRules(
                    period=period_key,
                    includes_overtime=None,
                    void_rule="start/non-runner/classification rule must match",
                    line_key=line_key,
                    dead_heat_rule="bookmaker_specific",
                    format_rule="classification/field scope must match",
                ),
                verification_required=True,
                verification_topics=("non-runner", "official classification", "dead heat", "event shortening/cancellation"),
                note="Race/field markets require explicit start, classification and tie/non-runner rule matching.",
            )

        if sport_key in {"esports", "counter-strike", "cs2", "league of legends", "dota 2", "valorant"}:
            return SettlementProfile(
                sport=sport_key,
                market_kind=kind,
                rules=SettlementRules(
                    period=period_key,
                    includes_overtime=None,
                    void_rule="forfeit/cancelled-map rule must match",
                    line_key=line_key,
                    retirement_rule="not_applicable",
                    format_rule="map/series/patch/format scope must match",
                ),
                verification_required=True,
                verification_topics=("forfeit", "map cancellation", "series-format change", "walkover", "overtime inclusion"),
                note="Esports settlement depends heavily on map/series scope and forfeit/cancellation rules; verify them before cross-book equivalence.",
            )

        if sport_key in {"volleyball", "handball", "rugby", "cricket", "darts", "snooker"}:
            return SettlementProfile(
                sport=sport_key,
                market_kind=kind,
                rules=SettlementRules(
                    period=period_key,
                    includes_overtime=None,
                    void_rule="event/format interruption rule must match",
                    line_key=line_key,
                    format_rule="set/innings/frame/extra-period scope must match",
                ),
                verification_required=True,
                verification_topics=("event format", "abandonment/interruption", "extra period/tiebreak scope"),
                note="Verify the exact event format and interruption/extra-period rules before treating cross-book prices as equivalent.",
            )

        return SettlementProfile(
            sport=sport_key or "unknown",
            market_kind=kind or "unknown",
            rules=SettlementRules(
                period=period_key,
                includes_overtime=None,
                void_rule="bookmaker_specific",
                line_key=line_key,
                format_rule="bookmaker_specific",
            ),
            verification_required=True,
            verification_topics=("event format", "void/cancellation", "tie/extra-time handling"),
            note="No trustworthy generic settlement profile exists for this sport/market yet; verify the bookmaker rules explicitly.",
        )

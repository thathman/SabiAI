#!/usr/bin/env python3
"""
rationale.py — Plain-English rationale generator for SabiAI picks.

Produces stats-first, jargon-free explanations for why a pick was made.

Usage:
    gen = RationaleGenerator(db_path)
    text = gen.generate(pick, features, model_probs)
"""

from typing import Dict, Optional


class RationaleGenerator:
    """Generate human-readable rationale for betting picks."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path

    def _form_line(self, team: str, stats: Dict, prefix: str = "") -> str:
        """Format a team's form into a readable line."""
        if not stats or stats.get('matches', 0) == 0:
            return f"{prefix}{team}: No recent form data"

        w = stats.get('wins', 0)
        d = stats.get('draws', 0)
        l = stats.get('losses', 0)
        gf = stats.get('avg_gf', 0)
        ga = stats.get('avg_ga', 0)

        form_str = f"{w}W {d}D {l}L"
        goals_str = f"scoring {gf} and conceding {ga} per game"

        return f"{prefix}{team}: {form_str} in last {stats['matches']} — {goals_str}"

    def _shots_line(self, team: str, stats: Dict, prefix: str = "") -> str:
        """Shots on target stats."""
        sot = stats.get('avg_sot', 0)
        if sot == 0:
            return ""
        return f"{prefix}{team}: {sot} shots on target per game"

    def _cs_line(self, team: str, stats: Dict, prefix: str = "") -> str:
        """Clean sheet percentage."""
        cs = stats.get('clean_sheet_pct', 0)
        if cs == 0:
            return ""
        return f"{prefix}{team}: {cs}% clean sheet rate"

    def _h2h_line(self, h2h: Dict) -> str:
        """Head-to-head summary."""
        if not h2h:
            return ""
        n = h2h.get('h2h_matches', h2h.get('matches', 0))
        if n == 0:
            return ""
        hw = h2h.get('h2h_home_wins', h2h.get('home_wins', 0))
        d = h2h.get('h2h_draws', h2h.get('draws', 0))
        aw = h2h.get('h2h_away_wins', h2h.get('away_wins', 0))
        avg_goals = h2h.get('h2h_avg_goals', h2h.get('avg_total_goals', 0))

        return f"H2H ({n} meetings): {hw} home wins, {d} draws, {aw} away — avg {avg_goals} goals"

    def _xg_line(self, team: str, stats: Dict, prefix: str = "") -> str:
        """Expected-goals stats when the upstream source provides them."""
        xg_for = stats.get('avg_xg_for')
        xg_against = stats.get('avg_xg_against')
        if xg_for is None and xg_against is None:
            return ""
        if xg_for is None:
            return f"{prefix}{team}: conceding {xg_against:.2f} xG per game"
        if xg_against is None:
            return f"{prefix}{team}: creating {xg_for:.2f} xG per game"
        return f"{prefix}{team}: creating {xg_for:.2f} xG and conceding {xg_against:.2f} xG per game"

    def _model_vs_market(self, pick: Dict) -> str:
        """Explain the value edge."""
        p_model = pick.get('p_model', 0)
        p_market = pick.get('p_market')
        ev_val = pick.get('ev', 0)

        lines = []

        if p_market:
            diff = p_model - p_market
            direction = "above" if diff > 0 else "below"
            lines.append(
                f"Model sees {p_model*100:.1f}% — {abs(diff)*100:.1f}% {direction} "
                f"the market's {p_market*100:.1f}%"
            )
        else:
            lines.append(f"Model probability: {p_model*100:.1f}%")

        if ev_val > 0:
            lines.append(f"Expected return: {ev_val*100:.1f}% per bet")

        return " | ".join(lines)

    def _pick_reason(self, pick: Dict, features: Dict) -> str:
        """Generate the core reason for the pick."""
        market = pick.get('market', '')
        pick_name = pick.get('pick', '')

        reasons = []

        if market == '1X2':
            h_pts = features.get('h_form5_pts', 0)
            a_pts = features.get('a_form5_pts', 0)
            elo_diff = features.get('elo_diff')

            if h_pts > a_pts:
                reasons.append(f"home team averaging {h_pts} pts/game vs away's {a_pts}")
            elif a_pts > h_pts:
                reasons.append(f"away team averaging {a_pts} pts/game vs home's {h_pts}")

            if elo_diff and abs(elo_diff) > 50:
                stronger = "home" if elo_diff > 0 else "away"
                reasons.append(f"Elo gap favours {stronger} side ({abs(elo_diff):.0f} pts)")

        elif 'O/U' in market:
            h_gf = features.get('h_form5_gf', 0)
            h_ga = features.get('h_form5_ga', 0)
            a_gf = features.get('a_form5_gf', 0)
            a_ga = features.get('a_form5_ga', 0)
            combined_avg = h_gf + h_ga + a_gf + a_ga
            reasons.append(f"combined scoring rate: {combined_avg:.1f} goals/match between both sides")

            if 'Over' in pick_name:
                btts_h = features.get('h_form5_btts_pct', 0)
                btts_a = features.get('a_form5_btts_pct', 0)
                if btts_h > 50 and btts_a > 50:
                    reasons.append(f"both teams see BTTS in >{min(btts_h, btts_a):.0f}% of recent games")
            else:
                cs_h = features.get('h_form5_cs_pct', 0)
                cs_a = features.get('a_form5_cs_pct', 0)
                if cs_h > 40 or cs_a > 40:
                    reasons.append(f"at least one side keeps clean sheets >{max(cs_h, cs_a):.0f}% of the time")

        elif 'BTTS' in market:
            h_btts = features.get('h_form5_btts_pct', 0)
            a_btts = features.get('a_form5_btts_pct', 0)
            if 'Yes' in pick_name:
                reasons.append(f"both sides score in >{min(h_btts, a_btts):.0f}% of recent games")
            else:
                cs_h = features.get('h_form5_cs_pct', 0)
                cs_a = features.get('a_form5_cs_pct', 0)
                reasons.append(f"one or both sides keep clean sheets frequently ({max(cs_h, cs_a):.0f}% rate)")

        if not reasons:
            reasons.append("statistical edge across multiple indicators")

        return "; ".join(reasons)

    def generate(self, pick: Dict, features: Dict, h2h: Dict = None,
                 home_stats: Dict = None, away_stats: Dict = None,
                 model_probs: Dict = None) -> str:
        """
        Generate complete plain-English rationale for a pick.

        Args:
            pick: Pick dict from value_engine.
            features: Feature dict from features.py.
            h2h: Head-to-head data.
            home_stats: Home team rolling stats.
            away_stats: Away team rolling stats.
            model_probs: Model probability output.

        Returns:
            Multi-line rationale string.
        """
        home = features.get('home', pick.get('match', '').split(' vs ')[0])
        away = features.get('away', pick.get('match', '').split(' vs ')[-1])

        sections = []

        # Header
        conf = pick.get('confidence', {})
        emoji = '🟢' if conf.get('label') == 'STRONG' else \
                '🟡' if conf.get('label') == 'SOLID' else '⚪'
        sections.append(f"{emoji} *{home} vs {away}*")
        sections.append(f"📌 {pick['market']}: {pick['pick']}")
        sections.append("")

        # Team form (stats first)
        sections.append("*Recent Form:*")
        if home_stats:
            sections.append(self._form_line(home, home_stats, "🏠 "))
        if away_stats:
            sections.append(self._form_line(away, away_stats, "✈️ "))

        # Shots on target
        shots_lines = []
        if home_stats and home_stats.get('avg_sot', 0) > 0:
            shots_lines.append(self._shots_line(home, home_stats, "🏠 "))
        if away_stats and away_stats.get('avg_sot', 0) > 0:
            shots_lines.append(self._shots_line(away, away_stats, "✈️ "))
        if shots_lines:
            sections.append("*Shots on Target:*")
            sections.extend(shots_lines)

        # xG, only when available from a richer source.
        xg_lines = []
        if home_stats:
            line = self._xg_line(home, home_stats, "🏠 ")
            if line:
                xg_lines.append(line)
        if away_stats:
            line = self._xg_line(away, away_stats, "✈️ ")
            if line:
                xg_lines.append(line)
        if xg_lines:
            sections.append("*xG:*")
            sections.extend(xg_lines)

        # Clean sheets
        cs_lines = []
        if home_stats and home_stats.get('clean_sheet_pct', 0) > 0:
            cs_lines.append(self._cs_line(home, home_stats, "🏠 "))
        if away_stats and away_stats.get('clean_sheet_pct', 0) > 0:
            cs_lines.append(self._cs_line(away, away_stats, "✈️ "))
        if cs_lines:
            sections.append("*Defensive Record:*")
            sections.extend(cs_lines)

        # H2H
        if h2h and h2h.get('h2h_matches', h2h.get('matches', 0)) > 0:
            sections.append("*Head to Head:*")
            sections.append(self._h2h_line(h2h))

        sections.append("")

        # Why this pick
        sections.append("*Why this pick:*")
        sections.append(self._pick_reason(pick, features))

        # Value explanation
        sections.append("")
        sections.append("*Value:*")
        sections.append(self._model_vs_market(pick))

        # Odds and confidence
        sections.append("")
        sections.append(f"📊 Odds: {pick['odds']}")
        sections.append(f"💰 Kelly stake: {pick.get('kelly', 0)*100:.1f}% of bankroll")
        sections.append(f"⭐ Confidence: {conf.get('score', 0)}/100")

        return "\n".join(sections)

    def generate_brief(self, pick: Dict) -> str:
        """Generate a short one-line rationale for compact displays."""
        match = pick.get('match', '? vs ?')
        market = pick.get('market', '?')
        pick_name = pick.get('pick', '?')
        p_model = pick.get('p_model', 0)
        ev_val = pick.get('ev', 0)
        conf = pick.get('confidence', {})
        emoji = '🟢' if conf.get('label') == 'STRONG' else \
                '🟡' if conf.get('label') == 'SOLID' else '⚪'

        return (f"{emoji} *{match}* — {market}: {pick_name} "
                f"(Model: {p_model*100:.0f}%, EV: {ev_val*100:.1f}%, "
                f"Odds: {pick['odds']})")

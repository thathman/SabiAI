from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sabiai.storage import AdvancedAnalytics, PerformanceAnalytics, SabiDatabase


@dataclass(frozen=True, slots=True)
class BlogTrigger:
    key: str
    priority: str
    title_hint: str
    reason: str
    data: dict


class BlogTriggerService:
    """Find meaningful reasons for Sabi Boy to reflect without generating filler posts."""

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def evaluate(
        self,
        *,
        hours: int = 24,
        now: datetime | None = None,
        streak_milestone: int = 3,
    ) -> list[BlogTrigger]:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        cutoff_dt = now - timedelta(hours=max(1, int(hours)))
        cutoff = cutoff_dt.isoformat()
        triggers: list[BlogTrigger] = []

        with self.db.connect() as conn:
            corrections = conn.execute(
                """SELECT entity_type,entity_id,previous_outcome,new_outcome,reason,changed_at
                   FROM settlement_audit
                   WHERE previous_outcome IS NOT NULL AND datetime(changed_at)>=datetime(?)
                   ORDER BY datetime(changed_at) DESC LIMIT 10""",
                (cutoff,),
            ).fetchall()
            recently_settled = conn.execute(
                """SELECT outcome,COUNT(*) AS n FROM picks_v2
                   WHERE settled_at IS NOT NULL AND datetime(settled_at)>=datetime(?)
                   GROUP BY outcome""",
                (cutoff,),
            ).fetchall()
            verified_sources = conn.execute(
                """SELECT name,url,sports_json,capabilities_json,verified_at
                   FROM source_discoveries
                   WHERE status='verified' AND verified_at IS NOT NULL
                     AND datetime(verified_at)>=datetime(?)
                   ORDER BY datetime(verified_at) DESC LIMIT 10""",
                (cutoff,),
            ).fetchall()

        if corrections:
            triggers.append(
                BlogTrigger(
                    key="settlement_correction",
                    priority="high",
                    title_hint="I had to correct the record",
                    reason=f"{len(corrections)} settlement correction(s) were recorded recently.",
                    data={"corrections": [dict(row) for row in corrections]},
                )
            )

        streaks = PerformanceAnalytics(self.db).streaks()
        current = streaks.get("current") or {}
        if int(current.get("count") or 0) >= max(2, int(streak_milestone)):
            kind = "winning" if current.get("type") == "won" else "losing"
            triggers.append(
                BlogTrigger(
                    key="streak_milestone",
                    priority="medium",
                    title_hint=f"What I am learning from this {kind} streak",
                    reason=f"Our current {kind} streak reached {current.get('count')} decided picks.",
                    data={"streaks": streaks},
                )
            )

        recent_killers = PerformanceAnalytics(self.db).ticket_killers(limit=5)
        fresh_killers = [
            row
            for row in recent_killers
            if self._parse_stamp(row.get("created_at"), default_tz=timezone.utc) >= cutoff_dt
        ]
        if fresh_killers:
            triggers.append(
                BlogTrigger(
                    key="ticket_killer",
                    priority="medium",
                    title_hint="One game changed the whole ticket",
                    reason=f"{len(fresh_killers)} recent lost ticket(s) were killed by exactly one leg.",
                    data={"tickets": fresh_killers},
                )
            )

        if verified_sources:
            triggers.append(
                BlogTrigger(
                    key="source_discovery",
                    priority="low",
                    title_hint="I found a new place to learn from",
                    reason=f"{len(verified_sources)} new source(s) were verified recently.",
                    data={"sources": [dict(row) for row in verified_sources]},
                )
            )

        settled = {row["outcome"]: int(row["n"]) for row in recently_settled}
        settled_total = sum(settled.values())
        if settled_total >= 8:
            triggers.append(
                BlogTrigger(
                    key="busy_results_window",
                    priority="low",
                    title_hint="A busy run of results gave me something to review",
                    reason=f"{settled_total} selections settled in the last {hours} hours.",
                    data={"outcomes": settled, "settled": settled_total},
                )
            )

        disagreements = AdvancedAnalytics(self.db).latest_price_disagreements(limit=10)
        meaningful = [row for row in disagreements if float(row.get("latest_gap") or 0) >= 0.10]
        if meaningful:
            triggers.append(
                BlogTrigger(
                    key="bookmaker_disagreement",
                    priority="low",
                    title_hint="The bookmakers disagreed more than usual",
                    reason=(
                        f"{len(meaningful)} observed market(s) have a latest recorded "
                        "decimal-price gap of at least 0.10."
                    ),
                    data={"markets": meaningful},
                )
            )

        order = {"high": 0, "medium": 1, "low": 2}
        return sorted(triggers, key=lambda row: (order.get(row.priority, 9), row.key))

    @staticmethod
    def _parse_stamp(value, *, default_tz=timezone.utc) -> datetime:
        if not value:
            return datetime.min.replace(tzinfo=default_tz)
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            try:
                parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return datetime.min.replace(tzinfo=default_tz)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=default_tz)
        return parsed.astimezone(timezone.utc)

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from sabiai.domain.aliases import normalize_name
from sabiai.domain.types import MarketKind
from sabiai.storage import SabiDatabase


@dataclass(slots=True)
class MigrationReport:
    source_db: str
    target_db: str
    source_counts: dict[str, int] = field(default_factory=dict)
    migrated_counts: dict[str, int] = field(default_factory=dict)
    archive_rows: int = 0
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    reconciliation: dict = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return not self.blockers and all(
            bool(value) for key, value in self.reconciliation.items() if key.endswith("_matches")
        )

    def as_dict(self) -> dict:
        data = asdict(self)
        data["ready"] = self.ready
        return data


class V1Migrator:
    """Deterministic, read-only-on-V1 migration into the canonical V2 database.

    The raw V1 rows are also copied into legacy_archive. This gives us a lossless safety net
    even for old tables that do not map directly into the new product model.
    """

    _event_split = re.compile(r"\s+(?:vs\.?|v\.?|-)\s+", re.I)

    def __init__(self, source_db: str | Path, target_db: str | Path):
        self.source_path = Path(source_db).expanduser()
        self.target = SabiDatabase(target_db)
        self.report = MigrationReport(str(self.source_path), str(self.target.path))

    def analyze(self) -> MigrationReport:
        self._require_source()
        with self._source() as source:
            tables = self._tables(source)
            self.report.source_counts = {
                table: int(source.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                for table in tables
                if table != "sqlite_sequence"
            }
            if "bets" not in tables:
                self.report.blockers.append("V1 source has no bets table.")
            if "bankroll" not in tables:
                self.report.warnings.append("V1 source has no bankroll table.")
            if "diary" not in tables:
                self.report.warnings.append("V1 source has no diary table.")
        return self.report

    def migrate(self) -> MigrationReport:
        self.analyze()
        if self.report.blockers:
            return self.report

        self.target.initialize()
        with self._source() as source:
            tables = self._tables(source)
            source_rows = {
                table: source.execute(f'SELECT * FROM "{table}"').fetchall()
                for table in tables
                if table != "sqlite_sequence"
            }

        with self.target.transaction() as target:
            self._archive_all(target, source_rows)
            self._migrate_bets(target, source_rows.get("bets", []), source_rows.get("bankroll", []))
            self._migrate_accumulators(
                target,
                source_rows.get("accumulators", []),
                source_rows.get("accumulator_legs", []),
            )
            self._migrate_weekly_long_shots(
                target,
                source_rows.get("weekly_long_shot", []),
                source_rows.get("bets", []),
            )
            self._migrate_bankroll(target, source_rows.get("bankroll", []))
            self._migrate_diary(target, source_rows.get("diary", []))
            target.execute(
                "INSERT OR REPLACE INTO v2_meta(key,value,updated_at) VALUES('v1_migration_source',?,CURRENT_TIMESTAMP)",
                (str(self.source_path),),
            )
            target.execute(
                "INSERT OR REPLACE INTO v2_meta(key,value,updated_at) VALUES('v1_migration_completed_at',?,CURRENT_TIMESTAMP)",
                (datetime.now(timezone.utc).isoformat(),),
            )

        self._reconcile()
        return self.report

    def _migrate_bets(self, target, rows, bankroll_rows) -> None:
        stakes = {
            str(row["bet_id"]): row["stake"]
            for row in bankroll_rows
            if "bet_id" in row.keys() and row["bet_id"] is not None and row["stake"] is not None
        }
        migrated = skipped = 0
        for row in rows:
            odds = self._valid_odds(row["odds"] if "odds" in row.keys() else None)
            match = str(row["match"] or "").strip() if "match" in row.keys() else ""
            pick = str(row["pick"] or "").strip() if "pick" in row.keys() else ""
            if odds is None or not match or not pick:
                skipped += 1
                self.report.blockers.append(
                    f"V1 bet {row['id']} cannot become a canonical pick: missing valid match/pick/decimal odds. Raw row is preserved in legacy_archive."
                )
                continue

            sport_id, sport_name = self._ensure_sport(target, row["sport"] if "sport" in row.keys() else None)
            created = self._timestamp(
                row["created_at"] if "created_at" in row.keys() else None,
                row["scan_date"] if "scan_date" in row.keys() else None,
            )
            starts = self._timestamp(
                row["kickoff"] if "kickoff" in row.keys() else None,
                row["scan_date"] if "scan_date" in row.keys() else created,
            )
            event_id = self._ensure_event(target, sport_id, sport_name, match, starts, self._outcome(row["outcome"] if "outcome" in row.keys() else None))
            market_id, selection_id, selection_label = self._ensure_market_selection(
                target,
                event_id,
                row["market"] if "market" in row.keys() else None,
                pick,
            )
            bookmaker_id = self._ensure_bookmaker(target, row["bookmaker"] if "bookmaker" in row.keys() else None)
            legacy_bet_id = str(row["bet_id"] or row["id"])
            pick_id = self._stable("pick_v1", legacy_bet_id)
            outcome = self._outcome(row["outcome"] if "outcome" in row.keys() else None)
            strategy = self._first(
                row["bet_type"] if "bet_type" in row.keys() else None,
                row["model"] if "model" in row.keys() else None,
            )
            rationale = self._first(
                row["plain_rationale"] if "plain_rationale" in row.keys() else None,
                row["notes"] if "notes" in row.keys() else None,
            )
            confidence = row["confidence_pct"] if "confidence_pct" in row.keys() else None
            selected = int(row["selected"] or 0) if "selected" in row.keys() else 0
            settled_at = (
                self._timestamp(row["settled_at"], created)
                if "settled_at" in row.keys() and row["settled_at"]
                else (created if outcome != "pending" else None)
            )
            stake = stakes.get(str(row["bet_id"])) if "bet_id" in row.keys() and row["bet_id"] else None
            target.execute(
                """INSERT OR IGNORE INTO picks_v2(
                       id,legacy_bet_id,event_id,market_id,selection_id,bookmaker_id,
                       decimal_odds,confidence_pct,rationale,strategy,selected,outcome,stake,
                       created_at,settled_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    pick_id,
                    legacy_bet_id,
                    event_id,
                    market_id,
                    selection_id,
                    bookmaker_id,
                    str(odds),
                    confidence,
                    rationale,
                    strategy,
                    selected,
                    outcome,
                    str(stake) if stake is not None else None,
                    created,
                    settled_at,
                ),
            )
            # Keep raw V1 text visible for audits without changing the user-facing normalized selection.
            target.execute(
                "UPDATE markets SET label=COALESCE(NULLIF(label,''),?) WHERE id=?",
                (str(row["market"] or selection_label), market_id),
            )
            migrated += 1

        self.report.migrated_counts["picks_v2"] = migrated
        if skipped:
            self.report.migrated_counts["bets_skipped"] = skipped

    def _migrate_accumulators(self, target, accumulators, legs) -> None:
        by_acc: dict[int, list] = {}
        for leg in legs:
            by_acc.setdefault(int(leg["acc_id"]), []).append(leg)
        count = leg_count = 0
        for row in accumulators:
            ticket_id = self._stable("ticket_v1_acc", row["id"])
            bookmaker_id = self._ensure_bookmaker(target, row["bookmaker"])
            created = self._timestamp(row["created_at"], None)
            status = self._ticket_status(row["status"])
            notes = [str(row["notes"])] if row["notes"] else []
            target.execute(
                """INSERT OR IGNORE INTO tickets(
                       id,bookmaker_id,source_type,source_reference,version_no,booking_code,
                       status,combined_odds,stake,payout,notes_json,created_at,settled_at
                   ) VALUES(?,?,?,?,1,?,?,?,?,?,?,?,?)""",
                (
                    ticket_id,
                    bookmaker_id,
                    "v1_accumulator",
                    row["slip_code"],
                    row["slip_code"],
                    status,
                    str(row["combined_odds"]) if row["combined_odds"] is not None else None,
                    str(row["stake"]) if row["stake"] is not None else None,
                    str(row["payout"]) if row["payout"] is not None else None,
                    json.dumps(notes, ensure_ascii=False),
                    created,
                    self._timestamp(row["settled_at"], created) if row["settled_at"] else None,
                ),
            )
            for index, leg in enumerate(by_acc.get(int(row["id"]), []), start=1):
                odds = self._valid_odds(leg["odds"])
                if odds is None:
                    self.report.blockers.append(
                        f"Accumulator {row['id']} leg {leg['id']} has invalid odds; raw row preserved but canonical leg skipped."
                    )
                    continue
                sport_id, sport_name = self._ensure_sport(target, leg["sport"])
                event_id = self._ensure_event(target, sport_id, sport_name, str(leg["match"] or "Unknown event"), created, self._outcome(leg["outcome"]))
                market_id, selection_id, _ = self._ensure_market_selection(target, event_id, leg["market"], leg["pick"])
                leg_id = self._stable("leg_v1_acc", row["id"], leg["id"])
                note = f"V1 confidence: {leg['confidence_pct']}%" if leg["confidence_pct"] is not None else None
                target.execute(
                    """INSERT OR IGNORE INTO ticket_legs(
                           id,ticket_id,leg_no,event_id,market_id,selection_id,bookmaker_id,
                           decimal_odds,locked,outcome,note
                       ) VALUES(?,?,?,?,?,?,?,?,0,?,?)""",
                    (
                        leg_id,
                        ticket_id,
                        index,
                        event_id,
                        market_id,
                        selection_id,
                        bookmaker_id,
                        str(odds),
                        self._outcome(leg["outcome"]),
                        note,
                    ),
                )
                leg_count += 1
            count += 1
        self.report.migrated_counts["accumulator_tickets"] = count
        self.report.migrated_counts["accumulator_legs"] = leg_count

    def _migrate_weekly_long_shots(self, target, rows, bets) -> None:
        bets_by_code: dict[str, list] = {}
        for bet in bets:
            code = str(bet["slip_code"] or "").strip() if "slip_code" in bet.keys() else ""
            if code:
                bets_by_code.setdefault(code, []).append(bet)

        count = legs_count = 0
        for row in rows:
            code = str(row["slip_code"] or "").strip()
            ticket_id = self._stable("ticket_v1_longshot", row["id"], code)
            bookmaker_id = self._ensure_bookmaker(target, row["bookmaker"])
            created = self._timestamp(row["created_at"], row["week_of"])
            target.execute(
                """INSERT OR IGNORE INTO tickets(
                       id,bookmaker_id,source_type,source_reference,version_no,booking_code,status,
                       combined_odds,stake,payout,notes_json,created_at,settled_at
                   ) VALUES(?,?,?,?,1,?,?,?,?,?,?,?,?)""",
                (
                    ticket_id,
                    bookmaker_id,
                    "v1_weekly_long_shot",
                    code or str(row["id"]),
                    code or None,
                    self._ticket_status(row["status"]),
                    str(row["combined_odds"]) if row["combined_odds"] is not None else None,
                    str(row["stake"]) if row["stake"] is not None else None,
                    str(row["payout"]) if row["payout"] is not None else None,
                    json.dumps([str(row["notes"])] if row["notes"] else [], ensure_ascii=False),
                    created,
                    self._timestamp(row["settled_at"], created) if row["settled_at"] else None,
                ),
            )
            for index, bet in enumerate(bets_by_code.get(code, []), start=1):
                odds = self._valid_odds(bet["odds"])
                if odds is None or not bet["match"] or not bet["pick"]:
                    continue
                sport_id, sport_name = self._ensure_sport(target, bet["sport"])
                event_id = self._ensure_event(target, sport_id, sport_name, str(bet["match"]), self._timestamp(bet["kickoff"], bet["scan_date"] or created), self._outcome(bet["outcome"]))
                market_id, selection_id, _ = self._ensure_market_selection(target, event_id, bet["market"], bet["pick"])
                target.execute(
                    """INSERT OR IGNORE INTO ticket_legs(
                           id,ticket_id,leg_no,event_id,market_id,selection_id,bookmaker_id,
                           decimal_odds,locked,outcome,note
                       ) VALUES(?,?,?,?,?,?,?,?,0,?,?)""",
                    (
                        self._stable("leg_v1_longshot", row["id"], bet["id"]),
                        ticket_id,
                        index,
                        event_id,
                        market_id,
                        selection_id,
                        bookmaker_id,
                        str(odds),
                        self._outcome(bet["outcome"]),
                        "Migrated from V1 weekly long-shot slip.",
                    ),
                )
                legs_count += 1
            count += 1
        self.report.migrated_counts["weekly_long_shot_tickets"] = count
        self.report.migrated_counts["weekly_long_shot_legs"] = legs_count

    def _migrate_bankroll(self, target, rows) -> None:
        if not rows:
            self.report.migrated_counts["bankroll_ledger"] = 0
            return

        existing = target.execute(
            "SELECT COUNT(*) FROM bankroll_ledger WHERE legacy_bet_id NOT LIKE 'v1-ledger:%' OR legacy_bet_id IS NULL"
        ).fetchone()[0]
        already = target.execute(
            "SELECT COUNT(*) FROM bankroll_ledger WHERE legacy_bet_id LIKE 'v1-ledger:%'"
        ).fetchone()[0]
        if existing and not already:
            self.report.blockers.append(
                "V2 bankroll already has non-migration entries. Migrate V1 bankroll before recording new V2 money events."
            )
            return

        previous_balance = Decimal("0.00")
        count = 0
        for row in sorted(rows, key=lambda item: int(item["id"])):
            legacy_key = f"v1-ledger:{row['id']}"
            if target.execute(
                "SELECT 1 FROM bankroll_ledger WHERE legacy_bet_id=?", (legacy_key,)
            ).fetchone():
                if row["balance"] is not None:
                    previous_balance = self._decimal(row["balance"])
                continue

            if row["balance"] is not None:
                balance = self._decimal(row["balance"])
                amount = (balance - previous_balance).quantize(Decimal("0.01"))
            elif row["delta"] is not None:
                amount = self._decimal(row["delta"])
                balance = (previous_balance + amount).quantize(Decimal("0.01"))
            else:
                self.report.blockers.append(f"V1 bankroll row {row['id']} has neither balance nor delta.")
                continue

            kind = self._ledger_kind(row["kind"], amount)
            target.execute(
                """INSERT INTO bankroll_ledger(
                       occurred_at,kind,amount,balance_after,legacy_bet_id,note
                   ) VALUES(?,?,?,?,?,?)""",
                (
                    self._timestamp(row["ts"], None),
                    kind,
                    str(amount),
                    str(balance),
                    legacy_key,
                    self._first(row["note"], f"Migrated V1 kind: {row['kind'] or 'unknown'}"),
                ),
            )
            previous_balance = balance
            count += 1
        self.report.migrated_counts["bankroll_ledger"] = count + int(already)

    def _migrate_diary(self, target, rows) -> None:
        count = 0
        for row in rows:
            post_id = self._stable("post_v1_diary", row["id"])
            title = str(row["title"] or f"Sabi diary — {row['date']}").strip()
            body = str(row["body"] or "").strip()
            if not body:
                body = "No written entry was stored for this V1 diary day."
            slug = f"v1-diary-{self._slug(row['date'] or row['id'])}-{self._stable('', title)[-8:]}".strip("-")
            tags = ["V1", "Diary"]
            if row["mood"]:
                tags.append(str(row["mood"]))
            related = {}
            if row["stats_json"]:
                try:
                    related["v1_stats"] = json.loads(row["stats_json"])
                except (TypeError, ValueError, json.JSONDecodeError):
                    related["v1_stats_raw"] = row["stats_json"]
            stamp = self._timestamp(row["created_at"], row["date"])
            target.execute(
                """INSERT OR IGNORE INTO blog_posts(
                       id,slug,title,body,excerpt,category,tags_json,status,related_json,
                       published_at,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    post_id,
                    slug,
                    title,
                    body,
                    body[:220],
                    "V1 Diary",
                    json.dumps(tags, ensure_ascii=False),
                    "published",
                    json.dumps(related, ensure_ascii=False),
                    stamp,
                    stamp,
                    stamp,
                ),
            )
            count += 1
        self.report.migrated_counts["diary_blog_posts"] = count

    def _archive_all(self, target, source_rows: dict[str, list]) -> None:
        count = 0
        for table, rows in source_rows.items():
            for row in rows:
                payload = {key: row[key] for key in row.keys()}
                key = self._legacy_key(table, payload)
                target.execute(
                    """INSERT OR REPLACE INTO legacy_archive(source_table,legacy_key,payload_json,migrated_at)
                       VALUES(?,?,?,CURRENT_TIMESTAMP)""",
                    (table, key, json.dumps(payload, ensure_ascii=False, default=str)),
                )
                count += 1
        self.report.archive_rows = count

    def _reconcile(self) -> None:
        with self._source() as source, self.target.connect() as target:
            v1_bets = source.execute("SELECT COUNT(*) FROM bets").fetchone()[0] if self._has_table(source, "bets") else 0
            migrated_picks = target.execute(
                "SELECT COUNT(*) FROM picks_v2 WHERE legacy_bet_id IS NOT NULL"
            ).fetchone()[0]
            skipped = self.report.migrated_counts.get("bets_skipped", 0)
            v1_acc = source.execute("SELECT COUNT(*) FROM accumulators").fetchone()[0] if self._has_table(source, "accumulators") else 0
            v2_acc = target.execute(
                "SELECT COUNT(*) FROM tickets WHERE source_type='v1_accumulator'"
            ).fetchone()[0]
            v1_diary = source.execute("SELECT COUNT(*) FROM diary").fetchone()[0] if self._has_table(source, "diary") else 0
            v2_diary = target.execute(
                "SELECT COUNT(*) FROM blog_posts WHERE id LIKE 'post_v1_diary_%'"
            ).fetchone()[0]

            v1_balance_row = source.execute(
                "SELECT balance FROM bankroll WHERE balance IS NOT NULL ORDER BY id DESC LIMIT 1"
            ).fetchone() if self._has_table(source, "bankroll") else None
            # V2 may already contain legitimate post-migration money events (for example,
            # a daily strategy stake).  Reconciliation must compare the V1 closing balance
            # with the balance represented by the migrated V1 ledger rows, rather than
            # treating those later V2 events as a migration error.
            v2_balance_row = target.execute(
                "SELECT balance_after FROM bankroll_ledger WHERE balance_after IS NOT NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
            v2_migration_balance_row = target.execute(
                """SELECT balance_after
                   FROM bankroll_ledger
                   WHERE legacy_bet_id LIKE 'v1-ledger:%'
                     AND balance_after IS NOT NULL
                   ORDER BY id DESC LIMIT 1"""
            ).fetchone()
            v1_balance = self._decimal(v1_balance_row[0]) if v1_balance_row else Decimal("0.00")
            v2_balance = self._decimal(v2_balance_row[0]) if v2_balance_row else Decimal("0.00")
            v2_migration_balance = (
                self._decimal(v2_migration_balance_row[0])
                if v2_migration_balance_row
                else v2_balance
            )

        self.report.reconciliation = {
            "v1_bets": int(v1_bets),
            "v2_legacy_picks": int(migrated_picks),
            "skipped_bets": int(skipped),
            "bets_matches": int(v1_bets) == int(migrated_picks) + int(skipped),
            "v1_accumulators": int(v1_acc),
            "v2_accumulator_tickets": int(v2_acc),
            "accumulators_matches": int(v1_acc) == int(v2_acc),
            "v1_diary": int(v1_diary),
            "v2_diary_posts": int(v2_diary),
            "diary_matches": int(v1_diary) == int(v2_diary),
            "v1_bankroll": str(v1_balance),
            "v2_bankroll": str(v2_balance),
            "v2_migration_bankroll": str(v2_migration_balance),
            "post_migration_bankroll_delta": str((v2_balance - v2_migration_balance).quantize(Decimal("0.01"))),
            "bankroll_matches": v1_balance == v2_migration_balance,
        }
        for key in ("bets_matches", "accumulators_matches", "diary_matches", "bankroll_matches"):
            if not self.report.reconciliation[key]:
                self.report.blockers.append(f"Migration reconciliation failed: {key}.")

    def _ensure_sport(self, target, name) -> tuple[str, str]:
        sport_name = str(name or "Unknown").strip() or "Unknown"
        slug = self._slug(sport_name)
        existing = target.execute("SELECT id,name FROM sports WHERE slug=?", (slug,)).fetchone()
        if existing:
            return existing["id"], existing["name"]
        sport_id = self._stable("sport", slug)
        target.execute(
            "INSERT INTO sports(id,slug,name) VALUES(?,?,?)",
            (sport_id, slug, sport_name),
        )
        target.execute(
            "INSERT OR IGNORE INTO sport_aliases(sport_id,alias,normalized_alias,source) VALUES(?,?,?,'v1')",
            (sport_id, sport_name, normalize_name(sport_name)),
        )
        return sport_id, sport_name

    def _ensure_bookmaker(self, target, name) -> str | None:
        text = str(name or "").strip()
        if not text:
            return None
        norm = self._slug(text)
        aliases = {
            "sportybet": ("bookmaker_sportybet", "sportybet", "SportyBet"),
            "sporty-bet": ("bookmaker_sportybet", "sportybet", "SportyBet"),
            "bet9ja": ("bookmaker_bet9ja", "bet9ja", "Bet9ja"),
            "bet-9ja": ("bookmaker_bet9ja", "bet9ja", "Bet9ja"),
        }
        canonical = aliases.get(norm)
        slug = canonical[1] if canonical else norm
        existing = target.execute("SELECT id FROM bookmakers WHERE slug=?", (slug,)).fetchone()
        if existing:
            return existing["id"]
        bookmaker_id = canonical[0] if canonical else self._stable("bookmaker_v1", slug)
        display = canonical[2] if canonical else text
        target.execute(
            "INSERT INTO bookmakers(id,slug,name) VALUES(?,?,?)",
            (bookmaker_id, slug, display),
        )
        target.execute(
            "INSERT OR IGNORE INTO bookmaker_aliases(bookmaker_id,alias,normalized_alias) VALUES(?,?,?)",
            (bookmaker_id, text, normalize_name(text)),
        )
        return bookmaker_id

    def _ensure_event(self, target, sport_id: str, sport_name: str, match: str, starts_at: str, outcome: str) -> str:
        event_id = self._stable("event_v1", sport_id, normalize_name(match), starts_at[:16])
        home, away = self._teams(match)
        home_id = self._ensure_participant(target, sport_id, home) if home else None
        away_id = self._ensure_participant(target, sport_id, away) if away else None
        status = "finished" if outcome != "pending" else "scheduled"
        target.execute(
            """INSERT OR IGNORE INTO events(
                   id,sport_id,name,starts_at,home_participant_id,away_participant_id,status
               ) VALUES(?,?,?,?,?,?,?)""",
            (event_id, sport_id, match.strip(), starts_at, home_id, away_id, status),
        )
        target.execute(
            "INSERT OR IGNORE INTO event_source_ids(event_id,source_name,source_event_id) VALUES(?, 'v1', ?)",
            (event_id, event_id),
        )
        return event_id

    def _ensure_participant(self, target, sport_id: str, name: str) -> str:
        participant_id = self._stable("participant_v1", sport_id, normalize_name(name))
        target.execute(
            "INSERT OR IGNORE INTO participants(id,sport_id,participant_type,name) VALUES(?,?, 'team', ?)",
            (participant_id, sport_id, name.strip()),
        )
        target.execute(
            "INSERT OR IGNORE INTO participant_aliases(participant_id,alias,normalized_alias,source) VALUES(?,?,?,'v1')",
            (participant_id, name.strip(), normalize_name(name)),
        )
        return participant_id

    def _ensure_market_selection(self, target, event_id: str, market_name, pick_name) -> tuple[str, str, str]:
        market_text = str(market_name or "").strip() or str(pick_name or "Selection").strip()
        pick_text = str(pick_name or market_text).strip()
        kind = self._market_kind(market_text, pick_text)
        market_id = self._stable("market_v1", event_id, normalize_name(market_text), kind.value)
        selection_id = self._stable("selection_v1", market_id, normalize_name(pick_text))
        target.execute(
            "INSERT OR IGNORE INTO markets(id,event_id,kind,label,period) VALUES(?,?,?,?, 'full_event')",
            (market_id, event_id, kind.value, market_text),
        )
        target.execute(
            "INSERT OR IGNORE INTO selections(id,market_id,label) VALUES(?,?,?)",
            (selection_id, market_id, pick_text),
        )
        return market_id, selection_id, pick_text

    @classmethod
    def _market_kind(cls, market: str, pick: str) -> MarketKind:
        text = f"{market} {pick}".casefold()
        if any(token in text for token in ("double chance", " 1x", " x2", "12 ")):
            return MarketKind.DOUBLE_CHANCE
        if "handicap" in text or re.search(r"[+-]\d+(?:\.\d+)?", text):
            return MarketKind.HANDICAP
        if any(token in text for token in ("corner", "card", "shot", "foul", "offside", "ace", "rebound", "assist")):
            return MarketKind.COUNT
        if any(token in text for token in ("over", "under", "total", "o/u")):
            return MarketKind.TOTAL
        if any(token in text for token in ("set", "map", "frame")):
            return MarketKind.SET_FRAME_MAP
        if any(token in text for token in ("1x2", "match result", "full time result")):
            return MarketKind.WIN_DRAW_LOSE
        if "winner" in text or "to win" in text:
            return MarketKind.WINNER
        return MarketKind.OTHER

    @staticmethod
    def _outcome(value) -> str:
        text = str(value or "").strip().casefold()
        return {
            "win": "won", "won": "won", "w": "won",
            "loss": "lost", "lost": "lost", "lose": "lost", "l": "lost",
            "draw": "draw", "d": "draw",
            "void": "void", "push": "void", "refund": "void", "cancelled": "void", "canceled": "void",
        }.get(text, "pending")

    @staticmethod
    def _ticket_status(value) -> str:
        text = str(value or "pending").strip().casefold()
        return {
            "win": "won", "won": "won",
            "loss": "lost", "lost": "lost",
            "void": "void", "cancelled": "void", "canceled": "void",
            "partial": "partial", "pending": "pending",
        }.get(text, "pending")

    @classmethod
    def _teams(cls, match: str) -> tuple[str | None, str | None]:
        parts = cls._event_split.split(str(match or "").strip(), maxsplit=1)
        if len(parts) != 2:
            return None, None
        return parts[0].strip() or None, parts[1].strip() or None

    @staticmethod
    def _timestamp(value, fallback) -> str:
        candidate = value or fallback
        if candidate is None or not str(candidate).strip():
            return datetime.now(timezone.utc).isoformat()
        text = str(candidate).strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return f"{text}T12:00:00+00:00"
        text = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            return str(candidate)

    @staticmethod
    def _valid_odds(value) -> Decimal | None:
        try:
            odds = Decimal(str(value)).quantize(Decimal("0.001"))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return odds if odds > Decimal("1") else None

    @staticmethod
    def _decimal(value) -> Decimal:
        try:
            return Decimal(str(value or 0)).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0.00")

    @staticmethod
    def _ledger_kind(kind, amount: Decimal) -> str:
        text = str(kind or "").casefold()
        if "refund" in text or "void" in text:
            return "refund"
        if "deposit" in text or "opening" in text or "start" in text or "initial" in text:
            return "deposit" if "deposit" in text else "opening_balance"
        if "withdraw" in text:
            return "withdrawal"
        if "win" in text or amount > 0:
            return "payout"
        if "loss" in text or "stake" in text or amount < 0:
            return "stake"
        return "adjustment"

    @staticmethod
    def _first(*values):
        for value in values:
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    def _slug(value) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
        return slug or "unknown"

    @staticmethod
    def _stable(prefix: str, *parts) -> str:
        raw = "|".join(str(part) for part in parts)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return f"{prefix}_{digest}" if prefix else digest

    @staticmethod
    def _legacy_key(table: str, payload: dict) -> str:
        if payload.get("id") is not None:
            return str(payload["id"])
        if payload.get("key") is not None:
            return str(payload["key"])
        if payload.get("scope") is not None and payload.get("key") is not None:
            return f"{payload['scope']}:{payload['key']}"
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(f"{table}|{raw}".encode("utf-8")).hexdigest()[:32]

    def _require_source(self) -> None:
        if not self.source_path.is_file():
            raise FileNotFoundError(f"V1 database not found: {self.source_path}")

    def _source(self) -> sqlite3.Connection:
        uri = f"file:{self.source_path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _tables(conn) -> set[str]:
        return {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

    @staticmethod
    def _has_table(conn, name: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None

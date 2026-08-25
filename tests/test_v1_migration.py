import sqlite3

from sabiai.migration import V1Migrator
from sabiai.storage import SabiDatabase


def _legacy_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE bets(
          id INTEGER PRIMARY KEY, bet_id TEXT, scan_date TEXT, week TEXT, sport TEXT,
          match TEXT, kickoff TEXT, market TEXT, pick TEXT, odds REAL, bookmaker TEXT,
          ev REAL, our_prob REAL, kelly REAL, model TEXT, outcome TEXT, settled_at TEXT,
          notes TEXT, created_at TEXT, confidence_pct REAL, plain_rationale TEXT,
          scorecard TEXT, closing_odds REAL, clv REAL, result_score TEXT,
          data_completeness REAL, slip_code TEXT, bet_type TEXT, selected INTEGER DEFAULT 0
        );
        CREATE TABLE bankroll(
          id INTEGER PRIMARY KEY, ts TEXT, bet_id TEXT, stake REAL,
          balance REAL, note TEXT, delta REAL, kind TEXT
        );
        CREATE TABLE diary(
          id INTEGER PRIMARY KEY, date TEXT, title TEXT, body TEXT, mood TEXT,
          stats_json TEXT, created_at TEXT
        );
        CREATE TABLE accumulators(
          id INTEGER PRIMARY KEY, slip_code TEXT, created_at TEXT, bookmaker TEXT,
          legs INTEGER, combined_odds REAL, stake REAL, status TEXT,
          payout REAL, settled_at TEXT, notes TEXT
        );
        CREATE TABLE accumulator_legs(
          id INTEGER PRIMARY KEY, acc_id INTEGER, sport TEXT, match TEXT, market TEXT,
          pick TEXT, odds REAL, confidence_pct REAL, outcome TEXT
        );
        CREATE TABLE calibration(
          id INTEGER PRIMARY KEY, computed_at TEXT, sport TEXT, market TEXT,
          bucket TEXT, n INTEGER, predicted REAL, actual REAL
        );
        CREATE TABLE config(key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
        """
    )
    conn.execute(
        """INSERT INTO bets VALUES(
          1,'manual-1','2026-08-20','2026-W34','Football','Arsenal vs Chelsea',
          '2026-08-20T18:00:00Z','1X2','Arsenal to win',1.80,'SportyBet',
          NULL,NULL,NULL,'kelly','win','2026-08-20T20:00:00Z','good read',
          '2026-08-20T10:00:00Z',74,'Arsenal stronger at home',NULL,NULL,NULL,NULL,NULL,
          NULL,'kelly',1
        )"""
    )
    conn.executemany(
        "INSERT INTO bankroll VALUES(?,?,?,?,?,?,?,?)",
        [
            (1,'2026-08-01T10:00:00Z','opening',0,100,'Opening bankroll',100,'opening_balance'),
            (2,'2026-08-20T20:00:00Z','manual-1',10,108,'Winning pick',8,'win'),
        ],
    )
    conn.execute(
        "INSERT INTO diary VALUES(1,'2026-08-20','A good day','I liked how we handled the ticket.','good','{\"won\":1}','2026-08-20T21:00:00Z')"
    )
    conn.execute(
        "INSERT INTO accumulators VALUES(1,'ABC123','2026-08-21T10:00:00Z','Bet9ja',2,3.20,10,'lost',0,'2026-08-21T21:00:00Z','One game killed it')"
    )
    conn.executemany(
        "INSERT INTO accumulator_legs VALUES(?,?,?,?,?,?,?,?,?)",
        [
            (1,1,'Football','Liverpool vs Everton','1X2','Liverpool to win',1.60,72,'win'),
            (2,1,'Football','Leeds vs Wolves','Over 2.5 goals','Over 2.5 goals',2.00,61,'loss'),
        ],
    )
    conn.execute(
        "INSERT INTO calibration VALUES(1,'2026-08-22','Football','1X2','70-79',12,0.74,0.67)"
    )
    conn.execute("INSERT INTO config VALUES('legacy-setting','yes','2026-08-22')")
    conn.commit()
    conn.close()


def test_v1_migration_preserves_history_and_reconciles(tmp_path):
    source = tmp_path / 'bets.db'
    target = tmp_path / 'sabi_v2.db'
    _legacy_db(source)

    report = V1Migrator(source, target).migrate()
    assert report.ready is True
    assert report.reconciliation['bets_matches'] is True
    assert report.reconciliation['accumulators_matches'] is True
    assert report.reconciliation['diary_matches'] is True
    assert report.reconciliation['bankroll_matches'] is True
    assert report.reconciliation['v1_bankroll'] == '108.00'
    assert report.reconciliation['v2_bankroll'] == '108.00'

    db = SabiDatabase(target)
    with db.connect() as conn:
        pick = conn.execute("SELECT * FROM picks_v2 WHERE legacy_bet_id='manual-1'").fetchone()
        assert pick['outcome'] == 'won'
        assert pick['decimal_odds'] == '1.800'
        assert pick['strategy'] == 'kelly'

        ticket = conn.execute("SELECT * FROM tickets WHERE source_type='v1_accumulator'").fetchone()
        assert ticket['booking_code'] == 'ABC123'
        assert ticket['status'] == 'lost'
        assert conn.execute("SELECT COUNT(*) FROM ticket_legs WHERE ticket_id=?", (ticket['id'],)).fetchone()[0] == 2

        post = conn.execute("SELECT * FROM blog_posts WHERE category='V1 Diary'").fetchone()
        assert post['status'] == 'published'
        assert 'handled the ticket' in post['body']

        assert conn.execute("SELECT COUNT(*) FROM legacy_archive WHERE source_table='calibration'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM legacy_archive WHERE source_table='config'").fetchone()[0] == 1


def test_v1_migration_is_repeatable_without_duplicate_history(tmp_path):
    source = tmp_path / 'bets.db'
    target = tmp_path / 'sabi_v2.db'
    _legacy_db(source)

    first = V1Migrator(source, target).migrate()
    second = V1Migrator(source, target).migrate()
    assert first.ready is True
    assert second.ready is True

    db = SabiDatabase(target)
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM picks_v2 WHERE legacy_bet_id='manual-1'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM tickets WHERE source_type='v1_accumulator'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM bankroll_ledger WHERE legacy_bet_id LIKE 'v1-ledger:%'").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM blog_posts WHERE category='V1 Diary'").fetchone()[0] == 1

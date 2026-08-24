-- bets.db schema
CREATE TABLE bets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            bet_id      TEXT UNIQUE,
            scan_date   TEXT NOT NULL,
            week        TEXT NOT NULL,
            sport       TEXT,
            match       TEXT,
            kickoff     TEXT,
            market      TEXT,
            pick        TEXT,
            odds        REAL,
            bookmaker   TEXT,
            ev          REAL,
            our_prob    REAL,
            kelly       REAL,
            model       TEXT,
            outcome     TEXT,       -- NULL | win | loss | void
            settled_at  TEXT,
            notes       TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        , confidence_pct REAL, plain_rationale TEXT, scorecard TEXT, closing_odds REAL, clv REAL, result_score TEXT, data_completeness REAL, slip_code TEXT, bet_type TEXT DEFAULT 'singles', selected INTEGER NOT NULL DEFAULT 0);
CREATE TABLE sqlite_sequence(name,seq);
CREATE INDEX idx_week    ON bets(week);
CREATE INDEX idx_sport   ON bets(sport);
CREATE INDEX idx_outcome ON bets(outcome);
CREATE TABLE bankroll(
      id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, bet_id TEXT,
      stake REAL, balance REAL, note TEXT, delta REAL, kind TEXT);
CREATE TABLE predictions(
      id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT DEFAULT (datetime('now')),
      source TEXT, code TEXT, sport TEXT, match TEXT, kickoff TEXT,
      market TEXT, pick TEXT, odds REAL, confidence_pct REAL,
      plain_rationale TEXT, scorecard TEXT, data_completeness REAL,
      outcome TEXT, settled_at TEXT);
CREATE TABLE calibration(
      id INTEGER PRIMARY KEY AUTOINCREMENT, computed_at TEXT, sport TEXT,
      market TEXT, bucket TEXT, n INTEGER, predicted REAL, actual REAL);
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX idx_bets_sport ON bets(sport);
CREATE INDEX idx_bets_outcome ON bets(outcome);
CREATE INDEX idx_bets_week ON bets(week);
CREATE TABLE config(key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
CREATE TABLE diary(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT UNIQUE, title TEXT, body TEXT, mood TEXT,
      stats_json TEXT, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE accumulators(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      slip_code TEXT, created_at TEXT, bookmaker TEXT,
      legs INTEGER, combined_odds REAL, stake REAL,
      status TEXT DEFAULT 'pending',      -- pending | won | lost | void
      payout REAL, settled_at TEXT, notes TEXT);
CREATE TABLE accumulator_legs(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      acc_id INTEGER, sport TEXT, match TEXT, market TEXT, pick TEXT,
      odds REAL, confidence_pct REAL, outcome TEXT,
      FOREIGN KEY(acc_id) REFERENCES accumulators(id));
CREATE TABLE continuous_bet_state(
  id INTEGER PRIMARY KEY CHECK (id = 1),
  streak_day INTEGER DEFAULT 0,
  starting_stake REAL DEFAULT 1000,
  current_stake REAL DEFAULT 1000,
  total_compounded REAL DEFAULT 0,
  cycle_count INTEGER DEFAULT 0,
  streak_status TEXT DEFAULT 'idle',  -- idle | active | won_30day | restrategy | broken
  last_pick_id INTEGER,
  last_pick_date TEXT,
  last_outcome TEXT,
  restrategy_until TEXT,
  restrategy_started_at TEXT,
  restrategy_reason TEXT,
  started_on TEXT,
  updated_at TEXT
);
CREATE TABLE sabiai_insights(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  generated_at TEXT,
  period_start TEXT,
  period_end TEXT,
  total_bets INTEGER,
  win_rate REAL,
  roi REAL,
  best_sport TEXT,
  worst_sport TEXT,
  best_market TEXT,
  worst_market TEXT,
  best_odds_band TEXT,
  worst_odds_band TEXT,
  calibration_notes TEXT,
  recommendations TEXT,
  raw_json TEXT
);
CREATE TABLE weekly_long_shot(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  week_of TEXT,
  slip_code TEXT,
  created_at TEXT,
  bookmaker TEXT,
  legs INTEGER,
  combined_odds REAL,
  stake REAL DEFAULT 100,
  status TEXT DEFAULT 'pending',
  payout REAL,
  settled_at TEXT,
  notes TEXT
);
CREATE TABLE learned_adjustments(
        scope TEXT, key TEXT,
        confidence_multiplier REAL DEFAULT 1.0,
        status TEXT DEFAULT 'active',
        sample_size INTEGER DEFAULT 0,
        win_rate REAL, roi REAL,
        note TEXT, updated_at TEXT,
        PRIMARY KEY(scope, key));
CREATE TABLE live_bets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, sport TEXT, league TEXT, match TEXT,
        kickoff TEXT, status TEXT DEFAULT 'watch',
        juicy_score INTEGER DEFAULT 0, signals TEXT,
        alerted_at TEXT, outcome TEXT, notes TEXT,
        created_at TEXT DEFAULT (datetime('now')), result TEXT, was_juicy INTEGER DEFAULT 0);

-- sabiai_v2.db schema
CREATE TABLE matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    league TEXT,
                    season TEXT,
                    date TEXT,
                    home TEXT,
                    away TEXT,
                    hg INTEGER,
                    ag INTEGER,
                    result TEXT,
                    shots_h INTEGER,
                    shots_a INTEGER,
                    sot_h INTEGER,
                    sot_a INTEGER,
                    corners_h INTEGER,
                    corners_a INTEGER,
                    cards_h INTEGER,
                    cards_a INTEGER,
                    red_h INTEGER,
                    red_a INTEGER,
                    referee TEXT,
                    odds_h REAL,
                    odds_d REAL,
                    odds_a REAL,
                    ou25_over REAL,
                    ou25_under REAL,
                    UNIQUE(league, season, date, home, away)
                );
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE upcoming (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    league TEXT,
                    season TEXT,
                    date TEXT,
                    home TEXT,
                    away TEXT,
                    odds_h REAL,
                    odds_d REAL,
                    odds_a REAL,
                    ou25_over REAL,
                    ou25_under REAL,
                    scraped_at TEXT,
                    UNIQUE(league, season, date, home, away)
                );
CREATE TABLE update_log (
                    league TEXT,
                    season TEXT,
                    last_updated TEXT,
                    rows_added INTEGER,
                    PRIMARY KEY (league, season)
                );

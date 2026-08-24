#!/usr/bin/env python3
"""setup.py — persist SabiAI onboarding answers and initialise the bankroll.

openclaw runs the onboarding Q&A (see SKILL), then pipes one JSON object here:
{
  "bankroll_start": 50000, "currency": "NGN",
  "staking_style": "percent",            # flat | percent | kelly
  "unit_size": 1000,                      # NGN per unit (flat) OR % of bankroll (percent)
  "kelly_fraction": 0.25,                 # if staking_style=kelly
  "max_exposure_pct": 10,                 # max % of bankroll on one slip
  "sports_focus": ["football","tennis","basketball"],
  "markets_focus": ["over/under goals","both teams to score","corners"],
  "odds_band": "1.50-2.19",
  "bookmakers": ["1xBet","SportyBet"],
  "min_stake": 200, "max_stake": 5000,
  "daily_bet_limit": 5,
  "target_roi_pct": 15,
  "risk_profile": "balanced",             # conservative | balanced | aggressive
  "stop_loss_pct": 30
}
"""
import json, sqlite3, sys
from datetime import datetime, timezone

DB = "~.openclaw/workspace/data/bets.db"
NOW = datetime.now(timezone.utc).isoformat()

def set_cfg(c, k, v):
    if isinstance(v, (list, dict)):
        v = json.dumps(v)
    c.execute("INSERT OR REPLACE INTO config(key,value,updated_at) VALUES(?,?,?)", (k, str(v), NOW))

def main():
    try:
        ans = json.loads(sys.stdin.read())
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"bad JSON: {e}"})); return
    c = sqlite3.connect(DB)
    for k in ["bankroll_start","currency","staking_style","unit_size","kelly_fraction",
              "max_exposure_pct","sports_focus","markets_focus","odds_band","bookmakers",
              "min_stake","max_stake","daily_bet_limit","target_roi_pct","risk_profile",
              "stop_loss_pct"]:
        if k in ans:
            set_cfg(c, k, ans[k])
    # Pass-through: any extra keys (mode, training_period, compound rules, etc.)
    known = {"bankroll_start","currency","staking_style","unit_size","kelly_fraction",
             "max_exposure_pct","sports_focus","markets_focus","odds_band","bookmakers",
             "min_stake","max_stake","daily_bet_limit","target_roi_pct","risk_profile",
             "stop_loss_pct"}
    for k, v in ans.items():
        if k not in known:
            set_cfg(c, k, v)
    # initialise virtual bankroll
    start = float(ans.get("bankroll_start", 0) or 0)
    cur = ans.get("currency", "NGN")
    c.execute("DELETE FROM bankroll")
    c.execute("INSERT INTO bankroll(ts,bet_id,stake,balance,note) VALUES(?,?,?,?,?)",
              (NOW, "", 0, start, f"Starting bankroll ({cur} {start:,.0f})"))
    set_cfg(c, "onboarded", "yes")
    set_cfg(c, "started_on", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    c.commit()
    cfg = {r[0]: r[1] for r in c.execute("SELECT key,value FROM config")}
    c.close()
    print(json.dumps({"ok": True, "bankroll_start": start, "currency": cur,
                      "config_keys": len(cfg)}, indent=2))

if __name__ == "__main__":
    main()

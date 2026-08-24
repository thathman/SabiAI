#!/usr/bin/env bash
# expense_heartbeat.sh — threshold-based expense alerts. No LLM.
# Fires WhatsApp only when: gambling >₦5k, balance drop >₦100k,
# income >₦100k, or unknown transaction. Silent otherwise.
set -euo pipefail
TRACKER=~/.openclaw/workspace/expense-tracker/tracker.py
OC=~/.npm-global/bin/openclaw
WA="+234XXXXXXXXXX"

scan_out=$(python3 "$TRACKER" scan 2>/dev/null || true)
[[ "$scan_out" == "Added 0 new transactions" || -z "$scan_out" ]] && exit 0

alerts=$(python3 - <<'PYEOF'
import sqlite3, os, sys
from datetime import datetime, timedelta, timezone

DB = os.path.expanduser("~/.openclaw/workspace/expense-tracker/data/finance.db")
cutoff = (datetime.now(timezone.utc) - timedelta(minutes=35)).isoformat()

c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
rows = c.execute("""
    SELECT amount, direction, category, merchant, remarks, balance_after
    FROM transactions
    WHERE created_at >= ?
    ORDER BY created_at DESC
""", (cutoff,)).fetchall()
c.close()

for r in rows:
    amt      = abs(r["amount"] or 0)
    cat      = (r["category"] or "").lower()
    dirn     = (r["direction"] or "").lower()
    merchant = r["merchant"] or r["remarks"] or "?"
    bal      = r["balance_after"]
    bal_str  = f" New balance: NGN {bal:,.0f}" if bal else ""

    if cat == "gambling" and amt > 5000:
        print(f"🎰 Large gambling spend: NGN {amt:,.0f} at {merchant}. Is this authorized?")
    elif dirn == "debit" and amt > 100000:
        print(f"💰 Large balance drop: NGN {amt:,.0f} to {merchant}.{bal_str}")
    elif dirn == "credit" and amt > 100000:
        print(f"💵 Income received: NGN {amt:,.0f} from {merchant}.{bal_str}")
    elif cat == "unknown":
        print(f"❓ Unrecognized: NGN {amt:,.0f} at {str(merchant)[:50]}. Reply with category.")
PYEOF
)

[[ -z "$alerts" ]] && exit 0

while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    $OC message send --channel whatsapp --target "$WA" --message "$line"
done <<< "$alerts"

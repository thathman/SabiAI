#!/usr/bin/env python3
"""money.py — Airix Media revenue toolkit: Perfex CRM client, invoice chaser, pipeline metrics.

Direct money wins: surface unpaid / partial / overdue invoices so Clawson can chase them, and
show the agency pipeline on the dashboard. Read-only against Perfex (no destructive calls).

CLI:
  chase           # JSON of invoices to follow up on (overdue/unpaid/partial) — agent drafts the nudge
  summary         # pipeline snapshot (used by dashboard)
  leads           # recent leads
"""
import json, os, sys, urllib.request, urllib.parse
from datetime import date, datetime

BASE = "https://dash.airixmedia.com/rest_api/v1"
TOKEN = os.environ.get("PERFEX_TOKEN", "YOUR_PERFEX_TOKEN_HERE")
STATUS = {1: "Unpaid", 2: "Paid", 3: "Partially Paid", 4: "Overdue", 5: "Cancelled", 6: "Draft"}
OUTSTANDING = {1, 3, 4}  # unpaid, partial, overdue

def _get(endpoint, params=None):
    url = f"{BASE}/{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TOKEN}",
        "User-Agent": "Mozilla/5.0 (SabiAI; Airix money agent)",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
    except Exception as e:
        return {"success": False, "error": str(e), "data": []}
    if isinstance(data, dict):
        return data
    return {"success": True, "data": data}

def _rows(resp):
    d = resp.get("data", resp) if isinstance(resp, dict) else resp
    return d if isinstance(d, list) else []

def invoices():
    return _rows(_get("invoices", {"limit": 500}))

def leads():
    return _rows(_get("leads", {"limit": 100}))

_CLIENT_CACHE = {}
def client_name(clientid):
    if not clientid: return "Unknown client"
    if clientid in _CLIENT_CACHE: return _CLIENT_CACHE[clientid]
    resp = _get(f"clients/{clientid}")
    rows = _rows(resp)
    name = None
    rec = rows[0] if rows else (resp.get("data") if isinstance(resp.get("data"), dict) else None)
    if isinstance(rec, dict):
        name = rec.get("company") or rec.get("name")
    _CLIENT_CACHE[clientid] = name or f"Client {clientid}"
    return _CLIENT_CACHE[clientid]

def _f(x):
    try: return float(x)
    except Exception: return 0.0

def _client_name(inv):
    return inv.get("deleted_customer_name") or client_name(inv.get("clientid"))

def chase_list():
    today = date.today().isoformat()
    out = []
    for inv in invoices():
        st = int(inv.get("status") or 0)
        if st not in OUTSTANDING:
            continue
        due = inv.get("duedate") or ""
        overdue_days = 0
        if due and due < today:
            try:
                overdue_days = (date.today() - datetime.strptime(due, "%Y-%m-%d").date()).days
            except Exception: pass
        out.append({
            "number": inv.get("formatted_number") or inv.get("number"),
            "client": _client_name(inv), "clientid": inv.get("clientid"),
            "total": _f(inv.get("total")), "status": STATUS.get(st, str(st)),
            "duedate": due, "overdue_days": overdue_days,
        })
    # most overdue / largest first
    return sorted(out, key=lambda x: (-x["overdue_days"], -x["total"]))

def summary():
    invs = invoices()
    by_status = {}
    invoiced = paid = outstanding = 0.0
    for inv in invs:
        st = int(inv.get("status") or 0)
        by_status[STATUS.get(st, str(st))] = by_status.get(STATUS.get(st, str(st)), 0) + 1
        tot = _f(inv.get("total"))
        invoiced += tot
        if st == 2: paid += tot
        if st in OUTSTANDING: outstanding += tot
    chase = chase_list()
    lds = leads()
    return {
        "invoices": len(invs), "by_status": by_status,
        "invoiced_total": round(invoiced, 2), "paid_total": round(paid, 2),
        "outstanding_total": round(outstanding, 2),
        "chase_count": len(chase), "chase": chase[:25],
        "overdue_amount": round(sum(c["total"] for c in chase if c["overdue_days"] > 0), 2),
        "leads": len(lds),
        "recent_leads": [{"name": l.get("name"), "status": l.get("status"),
                          "email": l.get("email"), "added": l.get("dateadded")}
                         for l in lds[:10]],
    }

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    if cmd == "chase":
        print(json.dumps(chase_list(), indent=2))
    elif cmd == "leads":
        print(json.dumps(leads()[:20], indent=2, default=str))
    else:
        print(json.dumps(summary(), indent=2))

if __name__ == "__main__":
    main()

#!/bin/bash
# Email check for morning briefing
# Uses himalaya to poll Gmail accounts for urgent emails
# Also checks realclawson@agentmail.to (Clawson primary address)

ACCT="${1:-acct2}"
OUTPUT=$(~/.local/bin/himalaya envelope list --account "$ACCT" --output json 2>/dev/null)

if [ $? -ne 0 ] || [ -z "$OUTPUT" ]; then
    echo "Email: CLI ready but no data fetched"
    AGENTMAIL_OUT=1
else
    AGENTMAIL_OUT=0
    TOTAL=$(echo "$OUTPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d))" 2>/dev/null)
    UNSEEN=$(echo "$OUTPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(sum(1 for e in d if '*' not in e.get('flags',[])))" 2>/dev/null)
    echo "Gmail: $TOTAL in inbox ($UNSEEN unread)"
    echo "$OUTPUT" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for e in d[:3]:
    sender = e['from']['name'] or e['from']['addr']
    subj = e['subject'][:60]
    print(f'  - {sender}: {subj}')
" 2>/dev/null
fi

# --- AgentMail (realclawson@agentmail.to) ---
if [ -f ~.openclaw/workspace/skills/agentmail/data/agentmail_inbox.json ]; then
    AM_STATE=$(cat ~.openclaw/workspace/skills/agentmail/data/agentmail_inbox.json)
    AM_TOTAL=$(echo "$AM_STATE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('total','?'))" 2>/dev/null)
    AM_LAST=$(echo "$AM_STATE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('last_check','?'))" 2>/dev/null)
    echo "AgentMail (realclawson@agentmail.to): $AM_TOTAL total, last check $AM_LAST"
fi


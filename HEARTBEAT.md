# SabiAI V2 heartbeat

Keep heartbeat work lightweight. Exact scheduled scans belong in cron/jobs; heartbeat is for awareness and recovery.

When a heartbeat runs, rotate through useful checks rather than doing everything every time:

- check the AI Spine inbox/board for Sabi-relevant work;
- run V2 `system.health` when V2 is active;
- notice failed/stale Sabi jobs or settlement backlog once those health tools are available;
- resume a clearly active research/ticket task only when there is meaningful new information;
- save durable lessons, not temporary noise;
- stay quiet when there is nothing material to report.

Do not burn paid research/API calls merely because a heartbeat fired.

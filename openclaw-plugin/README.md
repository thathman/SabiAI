# SabiAI V2 OpenClaw Plugin

This package is the native OpenClaw tool surface for SabiAI V2.

The plugin does **not** duplicate Sabi's business logic. It exposes typed OpenClaw tools and forwards each call to the Python V2 domain gateway in `scripts/sabiai_v2_tool.py`.

That keeps one source of truth for market interpretation, sports knowledge, ticket editing, source policy and later record/history logic.

## Current native tools

- `sabiai_system_health`
- `sabiai_sports_list`
- `sabiai_sports_describe`
- `sabiai_research_plan`
- `sabiai_market_interpret`
- `sabiai_market_arbitrage`
- `sabiai_bookmaker_resolve`
- `sabiai_ticket_split`
- `sabiai_ticket_trim`

## Local validation on the Dell

Do not deploy this plugin merely because the source exists in Git.

From this directory on the controlled OpenClaw host:

```bash
npm install
npm run plugin:build
npm run plugin:validate
openclaw plugins inspect sabiai-v2 --runtime --json
```

Then install/enable it using the local plugin workflow appropriate to the installed OpenClaw version and verify the tools appear in Sabi's effective tool catalog.

OpenClaw currently requires tool plugins to ship built JavaScript, `package.json` and `openclaw.plugin.json`; validation must be run after any tool-name or metadata change.

## Configuration

Optional plugin config:

- `rootDirectory` — SabiAI repository/workspace root.
- `pythonExecutable` — defaults to `python3`.

The plugin also accepts `SABIAI_ROOT` and `SABIAI_PYTHON` environment variables.

No API keys belong in this package.

## Security boundary

Current tools are read/compute/edit-in-memory operations. Future tools that persist records, build external bookmaker slips, send messages or otherwise cause side effects must be reviewed separately and should use OpenClaw's optional-tool/permission mechanisms rather than silently becoming always-available write tools.

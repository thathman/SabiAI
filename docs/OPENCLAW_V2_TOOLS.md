# SabiAI V2 — OpenClaw Tool Contract

This document defines the boundary between OpenClaw and the SabiAI V2 domain code.

## Rule

OpenClaw should call a stable Sabi tool contract. New skills should not duplicate business rules or query V2 SQLite directly.

Current bridge:

```bash
python3 scripts/sabiai_v2_tool.py
```

Request:

```json
{"tool":"market.interpret","args":{"text":"X2","home":"Arsenal","away":"Chelsea"}}
```

Response:

```json
{"ok":true,"tool":"market.interpret","data":{...}}
```

## Implemented now

- `system.health`
- `market.interpret`
- `bookmaker.resolve`
- `ticket.split`
- `ticket.trim`

## V2 namespaces to grow behind this same boundary

- `sports.*`
- `research.*`
- `bookmaker.*`
- `market.*`
- `ticket.*`
- `record.*`
- `history.*`
- `blog.*`
- `system.*`

The namespace list is a contract direction, not a claim that every tool already exists.

## Why one gateway

- one canonical interpretation of events/markets/tickets;
- one place to enforce decimal odds and explicit wording;
- one place to apply free-first source policy;
- one place to protect V2 data writes;
- easier testing;
- easier future MCP exposure;
- OpenClaw can change orchestration without changing domain rules.

## Compatibility

V1 scripts remain available during migration. New V2 functionality should prefer this gateway. Any temporary legacy fallback must be explicit and removable once the V2 equivalent exists.

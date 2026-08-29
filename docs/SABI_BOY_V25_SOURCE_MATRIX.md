# Sabi Boy V2.5 source matrix

This matrix describes the approved source expansion on
`feature/v2.5-non-football-coverage`. It is an implementation inventory, not a claim that every
provider is currently configured or live on Dell.

| Source | Role | Cost/class | Runtime configuration | State when absent |
| --- | --- | --- | --- | --- |
| API-Sports | Broad fixtures, stats, evidence and available odds | Metered/free allowance | `SABIAI_API_SPORTS_KEY` | disabled / `not_configured` |
| SportsGameOdds | Structured market/consensus sensor | Metered/free allowance | `SABIAI_SPORTSGAMEODDS_KEY` | disabled / `not_configured` |
| PandaScore | Esports matches, rosters, tournaments and player/team evidence | Authenticated API | `SABIAI_PANDASCORE_TOKEN` | disabled / `not_configured` |
| Jolpica F1 | Public F1 schedule, race, qualifying and standings data | Public/open | no key | available |
| FastF1 | Local F1 timing, telemetry, tyres and weather evidence | Local/open dependency | `SABIAI_FASTF1_CACHE_DIR` and optional `fastf1` install | disabled / `not_configured` |
| Cricsheet | Local historical cricket ball-by-ball analysis | Open dataset | `SABIAI_CRICSHEET_DIR` | disabled / `not_configured` |
| SportsDataIO | Targeted major-sport depth/evidence fallback | Commercial/trial | `SABIAI_SPORTSDATAIO_KEY` | disabled / `not_configured` |
| SportMonks | Cricket and Motorsport API v3 specialist evidence | Authenticated/commercial | `SABIAI_SPORTMONKS_TOKEN` | disabled / `not_configured` |
| StatsBomb / Hudl Open Data | Local historical football events, lineups and calibration | Open dataset | `SABIAI_STATSBOMB_DIR` | disabled / `not_configured` |
| OpenLigaDB | Free football fixture/result corroboration | Public API | no key | available |
| NBA LiveData | Public NBA scoreboard/live/final corroboration | Public endpoint | no key | available |

All adapters use the existing cache-first `SourceService` and retain provider-scoped IDs and
raw provenance. API credentials are sent in request headers where the provider supports that
contract and are never returned by source catalogues, health endpoints or error messages.

Metered providers fail closed behind explicit paid access and runtime request budgets. The
default guardrails are 100 uncached API-Sports requests per UTC day and 10 uncached
SportsGameOdds requests per UTC day; operators can lower or raise these with
`SABIAI_API_SPORTS_DAILY_REQUEST_BUDGET` and `SABIAI_SPORTSGAMEODDS_DAILY_REQUEST_BUDGET`.
Cache reuse does not spend a provider request.

SportsGameOdds is explicitly a market sensor, not an action bookmaker. API-Sports,
SportsDataIO, SportMonks, PandaScore and SportsGameOdds cannot create an executable pick by
themselves. SportyBet and Bet9ja remain the only action-price sources. No adapter contains a
wager-placement operation.

The public contracts used for this implementation are the current SportsGameOdds v2 API,
PandaScore REST API, Jolpica/Ergast-compatible F1 API, FastF1 local client, Cricsheet JSON
format, SportsDataIO APIs, SportMonks Motorsport API v3, OpenLigaDB API and NBA LiveData JSON.
Live provider acceptance is a separate Dell staging gate; normal tests use synthetic provider
responses and do not spend provider credits.

## Dell probe snapshot — 2026-08-29

The isolated Forgejo worktree at `e4f3a17a0efaa4f9870ef97d57fee19c884bc4af` passed the complete
361-test suite and deterministic engine acceptance. No-cost live probes returned one Jolpica F1
current-season record and an OpenLigaDB BL1 fixture response. The NBA LiveData CDN returned HTTP
403 from Dell, so that source is retained as a degraded secondary corroborator. The five keyed
providers are implemented and tested but remain `not_configured` until their credentials are
deliberately installed in the private V2.5 staging environment; they were not copied into the
V2.4 production environment.

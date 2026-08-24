# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## Additional Tools (from prompts)
**Brave Search API** — web search without Google; install: `npm install -g @ brave-search`
**LarryBrain Pro** — 32 skills on demand; check Composio CLI (`npx composio ls`)
**Netlify API** — production deployments; auth via `NETLIFY_AUTH_TOKEN` + `NETLIFY_SITE_ID`
**here.now** — free instant static hosting for prototypes; `npx here-Now` or similar
**Voicebox / Qwen3-TTS** — local voice cloning; not yet installed (Qwen3-TTS via Ollama)
**find-skills** — skill discovery from Vercel-labs repo; `npx @ find-skills` (local use only)

## Mission Control
**Dashboard:** ~/.openclaw/workspace/mission-control/index.html
**Access:** Open in browser at file:// URL or serve locally
**Refreshes:** Auto every 60s, or click ↻ Refresh
**Shows:** OpenClaw, Cobalt, WhatsApp bridge, system stats, cron jobs, agent sessions, business links
§
## Primary Machine

- **Host:** Dell running Ubuntu 24.04.4 LTS
- **SSH:** `ssh hendrix@YOUR_HOST_IP_HERE` or `ssh hendrix@dell.local`
- **Remote access:** Macbook Pro / Windows 11

## TTS / Voice

- **Provider:** ElevenLabs
- **Narrator voice ID:** `cgSgspJ2msm6clMCkdW9`
- **Minor voice ID:** `TVtDNgumMv4lb9zzFzA2`
- **Model:** `eleven_multilingual_v2`

## Messaging

- **WhatsApp allowed numbers:** +234XXXXXXXXXX, +234XXXXXXXXXX
- **Telegram bot:** token in env (`TELEGRAM_BOT_TOKEN`)
- **Telegram home channel:** YOUR_TELEGRAM_CHANNEL_ID_HERE (DM)
- **Discord home channel:** YOUR_DISCORD_CHANNEL_ID_HERE

## Environment

- **OpenClaw config:** `~/.openclaw/openclaw.json`
- **OpenClaw workspace:** `~/.openclaw/workspace/`
- **Hermes (legacy agent):** `~/.hermes/` — NO LONGER RUNNING. Replaced by OpenClaw.

- **Secrets file:** `~/.env` (do not share contents)
- **Gateway port:** 18789 (loopback only)

## Perfex CRM (Airix Media)
**Base URL:** https://dash.airixmedia.com/rest_api/v1
**Auth:** Bearer YOUR_PERFEX_TOKEN_HERE (or X-API-Key header)
**Tables:** clients(tblclients/userid), contacts(tblcontacts/id), tickets(tbltickets/ticketid), projects(tblprojects/id), tasks(tbltasks/id), invoices(tblinvoices/id), estimates, proposals, expenses, contracts, payments, staff(tblstaff/staffid), leads(tblleads/id)
**Read:** GET /ping, /clients, /contacts/{id}, /tickets, /projects, /tasks, /invoices, /estimates, /proposals, /expenses, /contracts, /payments, /staff, /leads
**Write:** POST /create/{resource}, PUT/PATCH/POST /update/{resource}/{id}
**Delete:** POST /update/{resource}/{id} with `{"__op":"delete"}`
**Pagination:** ?limit=100&page=1
**Schema:** GET /schema/{resource} before any write
**Known clients:** Kampala University (44), EFTBHS (43)
**Skill:** skills/crm/airix-media-perfex/
§
## Cobalt Downloader (Video)
**Endpoint:** localhost:9000
**Flow:** POST / with `{"url":"<video_url>","downloadMode":"auto"}` → get tunnel/redirect → download to /tmp/cobalt-downloads/ → deliver via `openclaw message send --channel whatsapp --media /tmp/cobalt-downloads/<file>` (NOT the dead :3000 bridge — that process no longer exists)
**Installed:** ~/.openclaw/workspace/skills/cobalt-downloader/
§

## WhatsApp Delivery (OpenClaw built-in)
**Use:** `openclaw message send --channel whatsapp --target <e164> --message "<text>"`
**Fallback queue:** if CLI fails, write JSON to `~/.openclaw/delivery-queue/agentmail_<ts>.json` for later pickup.
**Do NOT use:** `http://localhost:3000/send` — the bridge process is gone. Any code still pointing at it needs to be migrated to the `openclaw message send` path above.

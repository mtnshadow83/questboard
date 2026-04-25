# Questboard

Agent-native project management. CLI for agents (context-cheap), kanban web UI for humans, JSON API for remote operations.

Built to replace Vikunja after its REST API proved too verbose for agent context windows. Same lineage as Abadar (credentials) and Desna (URLs) — single Python script, SQLite backend, zero dependencies beyond Flask.

## Architecture

```
Rocky (dev machine)                    questboard-ec2 (AWS)
  qb CLI ── QB_REMOTE ──────────────> Flask + JSON API (port 5151)
  Pingle (Win95 popups)                Pingle Push (Web Push)
                                       HTTPS via Tailscale Funnel
                                              │
                                        Pebble (phone)
                                        Push notifications
```

Single SQLite database on EC2. Rocky agents talk to it over HTTPS. Pingle Push watches for blocked tickets on `/pings` and sends push notifications to mobile. Pingle on Rocky fires Win95-styled PyQt5 desktop popups for the same events.

## Quick Start

```bash
# Local mode (direct SQLite)
python questboard.py serve --port 5151
python questboard.py add "Fix the thing" --project myproject

# Remote mode (over HTTPS to EC2)
export QB_REMOTE=https://questboard-ec2.tail7f6073.ts.net
python questboard.py add "Fix the thing" --project pings
python questboard.py list --project pings
python questboard.py block 254 "Waiting on credentials"
```

## CLI Commands

| Command | Usage | Notes |
|---------|-------|-------|
| `add` | `qb add "title" -p project [-a user] [-l label] [--priority N]` | Create ticket |
| `list` | `qb list [-p project] [-s status] [-a user] [--all]` | List tickets |
| `show` | `qb show <id>` | Ticket detail + comments |
| `edit` | `qb edit <id> [--title] [--description] [--priority]` | Edit ticket fields |
| `status` | `qb status <id> <status-name>` | Change status |
| `assign` | `qb assign <id> [<id>...] -u <user>` | Assign (bulk) |
| `move` | `qb move <id> [<id>...] -p <project>` | Move to project (bulk) |
| `done` | `qb done <id> [<id>...]` | Close tickets (bulk) |
| `block` | `qb block <id> ["reason"]` | Block + optional comment |
| `comment` | `qb comment <id> "text" [-u user]` | Add comment |
| `label` | `qb label <id> [<id>...] -l <label>` | Add label (bulk) |
| `unlabel` | `qb unlabel <id> [<id>...] -l <label>` | Remove label (bulk) |
| `promote` | `qb promote <id> [<id>...] [-p project]` | Move from /pings to target |
| `project-add` | `qb project-add "name" [-d description]` | Create project |
| `project-list` | `qb project-list` | List projects |
| `serve` | `qb serve [--port 5151]` | Start web UI |

## JSON API

All endpoints accept and return JSON. Base URL: `https://questboard-ec2.tail7f6073.ts.net`

| Method | Endpoint | Action |
|--------|----------|--------|
| GET | `/api/tickets` | List (query params: project, status, assignee, label, all) |
| POST | `/api/tickets` | Create (`{title, project, priority, assignee, creator, labels, description}`) |
| GET | `/api/tickets/<id>` | Show (includes comments) |
| PUT | `/api/tickets/<id>/status` | Change status (`{status}`) |
| PUT | `/api/tickets/<id>/assign` | Assign (`{assignee}`) |
| PUT | `/api/tickets/<id>/move` | Move (`{project}`) |
| POST | `/api/tickets/<id>/block` | Block (`{reason}`) |
| POST | `/api/tickets/<id>/done` | Close |
| POST | `/api/tickets/<id>/comment` | Comment (`{body, user}`) |
| POST | `/api/tickets/<id>/promote` | Promote (`{project}`) |
| POST | `/api/tickets/<id>/label` | Add label (`{label}`) |
| POST | `/api/tickets/<id>/unlabel` | Remove label (`{label}`) |
| GET | `/api/projects` | List projects |
| GET | `/api/users` | List users |
| GET | `/api/statuses` | List statuses |

## Agent Routing Policy

Agents cannot write directly to the `artificer` project. Tickets from agents are automatically routed to `/pings`. The human operator reviews and promotes tickets via `qb promote <id>`.

Only blocked tickets on `/pings` trigger notifications — no noise on create, move, or close.

## Notifications

**Desktop (Rocky):** Win95-styled PyQt5 popups via Pingle daemon. Top-right stacking, max 3 visible, 30-second auto-dismiss with fade. See `pingle/pingle.py`.

**Mobile (Pebble):** Web Push via VAPID keys and service worker. Pingle Push daemon on EC2 polls for blocked events and sends push notifications. Vibration and lock screen cards enabled.

## Deployment

EC2 instance (`t3.micro`, Ubuntu 22.04) on Tailscale private mesh. Three systemd services:
- `questboard.service` — Flask app
- `pingle-push.service` — Push notification daemon
- Tailscale Funnel — HTTPS proxy (managed by `tailscale serve/funnel --bg`)

Deploy updated code:
```bash
scp -i ~/forge3/questboard-key.pem questboard.py ubuntu@100.83.251.119:/opt/questboard/
ssh -i ~/forge3/questboard-key.pem ubuntu@100.83.251.119 "sudo systemctl restart questboard"
```

Full topology documented at `library/0-system/topology/entity-registry.md`.

## File Layout

```
dev/questboard/
  questboard.py          # Everything: CLI + Flask + API + DB (~2500 lines)
  spec.md                # Original spec (v0.1)
  pingle/
    pingle.py            # Win95 desktop notification daemon
    pinger.pyw           # Dev tool — test button
    build-plan.md        # Historical (v0.1, PowerShell approach)
    ec2-deployment-overview.md
  planning/
    action-plan-2026-04-23.md    # Bug fix batches
    ec2-finalization-plan.md     # EC2 deployment plan (completed)
```

## Build History

| Date | Milestone |
|------|-----------|
| 2026-04-22 | Questboard created. Single-file CLI + Flask + SQLite. Kanban web UI. |
| 2026-04-22 | Vikunja import — 7 projects, 82 tickets migrated. |
| 2026-04-23 | Drag-and-drop kanban. 8 bug fixes + 4 features from user feedback. |
| 2026-04-23 | Pingle v0 — PowerShell toast notifications. Worked but noisy. |
| 2026-04-24 | Pingle v1 — Win95 PyQt5 popups. Frameless, resizable, stackable. |
| 2026-04-24 | Agent routing policy. `/pings` board, blocked-only trigger, `qb promote`. |
| 2026-04-24 | EC2 provisioned. Tailscale mesh (Rocky + EC2 + Pebble). |
| 2026-04-24 | Questboard deployed to EC2. Favicon, mobile CSS, manifest. |
| 2026-04-25 | Tailscale Funnel activated. HTTPS live. |
| 2026-04-25 | Web Push notifications confirmed on Pebble. Vibration + lock screen. |
| 2026-04-25 | Systemd services. Reboot-verified. |
| 2026-04-25 | JSON API (15 endpoints). Remote CLI mode via `QB_REMOTE`. |
| 2026-04-25 | DB consolidated on EC2. Full loop: Rocky -> EC2 -> Pebble. |

## Tech Stack

- Python 3.12 + Flask
- SQLite (WAL mode, foreign keys)
- PyQt5 (desktop notifications)
- pywebpush + VAPID (mobile push)
- Tailscale (mesh networking)
- Tailscale Funnel (HTTPS)
- AWS EC2 t3.micro + systemd

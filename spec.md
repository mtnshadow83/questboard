# Questboard — Spec v0.1

**Purpose:** Lightweight project management tool built for agent workflows. Agents interact via CLI (context-cheap), humans review via local web UI (kanban board on localhost).

**Why not Vikunja:** REST API responses are too verbose — a single task fetch dumps ~60 lines of JSON into agent context. Questboard uses direct SQLite access, zero HTTP overhead for agent operations.

**Lineage:** Same pattern as Abadar (credentials) and Desna (URLs) — single Python script + SQLite DB.

---

## Users

A user is anyone who can be assigned a ticket — human or agent.

| Field | Type | Notes |
|-------|------|-------|
| id | int | auto |
| name | text | unique, e.g. `artificer`, `deskie`, `builder`, `scribe` |
| role | text | `human` or `agent` |
| created_at | datetime | |

Users are created via CLI. No auth — this is a local single-machine tool.

---

## Projects

A project groups related tickets. Tickets can move between projects.

| Field | Type | Notes |
|-------|------|-------|
| id | int | auto |
| name | text | unique |
| description | text | optional |
| created_at | datetime | |
| archived | bool | default false — hides from default views |

---

## Statuses

Statuses are **not hardcoded**. They live in a table and can be created, renamed, reordered, or deleted. Each status has a display order that determines its column position in kanban view.

| Field | Type | Notes |
|-------|------|-------|
| id | int | auto |
| name | text | unique, e.g. `queued`, `in-progress`, `review`, `blocked`, `done`, `n/a` |
| display_order | int | column position in kanban (lower = further left) |
| is_closed | bool | default false — closed statuses don't show in active views |

**Seed statuses** (created on first run, all editable/deletable):

| Order | Name | Closed? |
|-------|------|---------|
| 0 | queued | no |
| 1 | in-progress | no |
| 2 | blocked | no |
| 3 | review | no |
| 4 | done | yes |
| 5 | n/a | yes |

---

## Labels

Freeform tags for cross-cutting concerns. A ticket can have many labels.

| Field | Type | Notes |
|-------|------|-------|
| id | int | auto |
| name | text | unique, e.g. `priority:high`, `type:bug`, `area:auth` |
| color | text | optional hex color for web UI |

---

## Tickets

The core unit. A ticket belongs to one project, has one status, one assignee (optional), and many labels.

| Field | Type | Notes |
|-------|------|-------|
| id | int | auto |
| project_id | int | FK -> projects |
| status_id | int | FK -> statuses |
| assigned_to | int | FK -> users, nullable |
| title | text | required |
| description | text | optional, markdown |
| priority | int | 0=none, 1=low, 2=medium, 3=high, 4=critical |
| created_by | int | FK -> users |
| created_at | datetime | |
| updated_at | datetime | |

### ticket_labels (join table)

| Field | Type |
|-------|------|
| ticket_id | int |
| label_id | int |

---

## Comments

Timestamped notes on a ticket. Agents use these to log status changes, blockers, handoff notes.

| Field | Type | Notes |
|-------|------|-------|
| id | int | auto |
| ticket_id | int | FK -> tickets |
| user_id | int | FK -> users |
| body | text | markdown |
| created_at | datetime | |

---

## CLI Interface

The CLI is the agent-facing interface. Design principle: **every command produces the minimum output needed to confirm the action or answer the query.** No JSON. No envelopes. One line per item on list commands.

### Projects

```
qb project add "Koko Deployment"
  -> Project #1: Koko Deployment

qb project list
  -> #1 Koko Deployment (3 open)
     #2 Library Pipeline (7 open)

qb project archive 1
  -> Archived: Koko Deployment
```

### Tickets

```
qb add "Fix auth token refresh" --project 1 --assign deskie --priority high --label type:bug
  -> #14 Fix auth token refresh [queued] @deskie ●●●

qb list
  -> #12 [ ] Set up Tailscale mesh        @builder  queued     priority:high
     #14 [ ] Fix auth token refresh        @deskie   queued     type:bug priority:high
     #15 [ ] Write onboarding doc          @scribe   in-progress

qb list --project 1 --status in-progress
  -> #15 [ ] Write onboarding doc          @scribe   in-progress

qb show 14
  -> #14 Fix auth token refresh
     Project:  Koko Deployment (#1)
     Status:   queued
     Assigned: deskie
     Priority: high (●●●)
     Labels:   type:bug
     Created:  2026-04-21 by artificer
     ---
     [2026-04-21 14:30] deskie: Blocked on Abadar key rotation, moving to blocked.

qb status 14 in-progress
  -> #14 -> in-progress

qb assign 14 builder
  -> #14 -> @builder

qb move 14 --project 2
  -> #14 moved to Library Pipeline (#2)

qb done 14
  -> #14 -> done

qb comment 14 "Token refresh working after Abadar key rotation."
  -> Comment added to #14

qb label 14 area:auth
  -> Label area:auth added to #14

qb block 14 "Waiting on API key from Abadar"
  -> #14 -> blocked
     Comment added: Waiting on API key from Abadar
```

### Statuses

```
qb status-list
  -> 0: queued
     1: in-progress
     2: blocked
     3: review
     4: done (closed)
     5: n/a (closed)

qb status-add "qa-testing" --order 3
  -> Status added: qa-testing (order 3)

qb status-rename "review" "peer-review"
  -> Status renamed: review -> peer-review

qb status-reorder "blocked" 4
  -> Status reorder: blocked -> position 4
```

### Users

```
qb user add deskie --role agent
  -> User: deskie (agent)

qb user list
  -> artificer  human
     deskie     agent
     builder    agent
     scribe     agent
```

### Labels

```
qb label-add "priority:critical" --color "#ff0000"
  -> Label: priority:critical

qb label-list
  -> type:bug  type:feature  priority:high  priority:critical  area:auth
```

---

## Web UI

`qb serve` launches a local web server on a configurable port (default `localhost:5151`).

### Views

**Kanban board** (default view)
- Columns = statuses, ordered by `display_order`
- Cards = tickets, showing title, assignee, priority dots, labels as colored chips
- Filter bar: project, assignee, label, priority
- Drag-and-drop to change status (nice-to-have, not MVP)

**List view**
- Table of tickets with sortable columns
- Same filter bar as kanban

**Ticket detail** (click a card/row)
- Full ticket info + comment thread
- Edit status, assignee, project, labels, priority inline

**Project switcher**
- Sidebar or dropdown to filter by project
- "All projects" as default

### Tech stack

- Python standard library + one lightweight framework (Flask or Bottle — whichever is already installed, check first)
- HTML/CSS/JS — no build step, no npm, no node
- Inline or single-file static assets
- SQLite via Python's built-in `sqlite3`
- Jinja2 templates (ships with Flask) or string templates

### Design notes

- Dark theme preferred (consistent with agent tooling aesthetic)
- Mobile-friendly is not a priority — this is a desktop localhost tool
- No auth — local only

---

## File Layout

```
dev/questboard/
  spec.md             <- this file
  questboard.py       <- CLI + web server + DB layer, single file
  questboard.db       <- SQLite database (created on first run)
  templates/          <- Jinja2 HTML templates (if needed)
    layout.html
    kanban.html
    list.html
    ticket.html
  static/             <- CSS/JS (minimal)
    style.css
```

On deployment, `questboard.py` also gets symlinked or copied into `library/0-system/claude/toolsets/` as the canonical agent entrypoint. The DB stays in `dev/questboard/`.

---

## Open Questions

1. **Notifications / messageboard integration** — Should status changes post to the existing messageboard in `library/0-system/claude/messageboard/`?
2. **History / audit log** — Track all state changes (status, assignment, project moves) in a separate table?
3. **CLI alias** — Set up `qb` as a shell alias to `python ~/dev/questboard/questboard.py`?
4. **Batch operations** — `qb done 14 15 16` to close multiple tickets at once?
5. **Import from Vikunja** — Migrate existing Vikunja projects/tasks into questboard?
6. **Ticket relationships** — Parent/child, blocks/blocked-by, duplicates?

---

## Non-Goals (v1)

- Multi-machine sync (local SQLite only for now)
- API for external integrations
- Email/Slack notifications
- Time tracking
- File attachments
- Sprints / milestones (can be modeled with labels if needed)

---

*Questboard: because every adventuring party needs a quest board.*

# Questboard Dev — Action Plan

**Created:** 2026-04-23
**Source:** `reports/ticket-audit-2026-04-22.md`
**Executor:** Dev agent (Sonnet) per batch, reviewed by Artificer

---

## Approach

Three batches. Each batch is one dev agent spawn with a self-contained prompt. Artificer reviews and approves between batches. All work targets `dev/questboard/questboard.py` (single file, 1,634 lines).

---

## Batch 1 — Quick Wins

**Goal:** Ship 4 fixes that are small, low-risk, and independently testable.
**Effort:** ~30 min dev agent time
**Risk:** Low — isolated changes, no schema migration

| # | Ticket | What | Lines | Change |
|---|--------|------|-------|--------|
| 167 | UTF-8 crash on `qb show` | Add `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` after imports | ~14 | 1 line |
| 169 | `--status done` returns empty | Skip `is_closed=0` filter when `--status` is explicitly provided | 351-352 | 3 lines |
| 162 | Questboard link dead | Wrap topbar `h1` text in `<a href="/">` | 711 | 1 line |
| 166 | Add `qb edit` subcommand | New `cmd_edit(args)` function + argparse registration | After line 314 | ~35 lines |

**Test plan:**
- `qb show` on a ticket with unicode in comments — no crash
- `qb list --status done` — returns closed tickets
- Open web UI, click "Questboard" text — navigates to kanban
- `qb edit 162 --title "New title"` — title changes, activity logged

**Acceptance:** All 4 tests pass, no regressions on `qb list`, `qb add`, `qb show` for normal cases.

---

## Batch 2 — Web UI Fixes

**Goal:** Fix the two interactive bugs that break the web editing experience.
**Effort:** ~45 min dev agent time
**Risk:** Medium — touches Flask routes and frontend JS

| # | Ticket | What | Lines | Change |
|---|--------|------|-------|--------|
| 164 | Assignee change wipes comment | Convert assignee dropdown to async JS fetch, remove page reload | 1341-1352 | ~30 lines (JS + route) |
| 170 | Comments store `user_id=NULL` | Add user selector to comment form, pass `user_id` on insert | 1354-1363 | ~20 lines |
| 163 | Default assignee filter | Set assignee filter from cookie or first user when no filter selected | 1155-1192 | ~10 lines |

**Test plan:**
- Open ticket detail, type comment, change assignee — comment text survives
- Submit a comment from web UI — check `user_id` is populated in DB
- Open kanban with no filters — assignee defaults to current user

**Acceptance:** Comment box persists across assignee changes. Comments attributed correctly. Kanban filters default sensibly.

---

## Batch 3 — CLI Power Features

**Goal:** Add the CLI features that agents asked for.
**Effort:** ~45 min dev agent time
**Risk:** Low — follows existing patterns, no UI changes

| # | Ticket | What | Lines | Change |
|---|--------|------|-------|--------|
| 174 | Bulk operations | Extend `assign`, `label`, `unlabel`, `move` to accept multiple ticket IDs (copy `cmd_done` pattern) | Argparse + cmd functions | ~80 lines |
| 172 | REST/JSON endpoints | Add JSON routes for list, show, add, comment mirroring CLI commands | After line 1338 | ~100 lines |

**Test plan:**
- `qb assign 162 163 164 -a deskie-g` — all three assigned
- `qb label 162 163 -l urgent` — both labeled
- `curl localhost:5151/api/tickets` — returns JSON ticket list
- `curl -X POST localhost:5151/api/tickets -d '{"title":"test","project":"Questboard Dev"}'` — creates ticket

**Acceptance:** Bulk commands work on 3+ tickets. JSON API returns valid responses for CRUD.

---

## Deferred — Not in This Plan

| # | Ticket | Why |
|---|--------|-----|
| 168 | `-a` silent skip | Needs repro with exact command sequence before coding a fix |
| 171 | Per-project ticket index | Schema migration, needs design decision on display format |
| 173 | Webhooks | Needs config model design (where do webhook URLs live?) |
| 165 | File uploads | Largest feature — new schema, storage, UI. Separate project. |

---

## Execution

1. Artificer approves this plan
2. Deskie-G writes build prompt for Batch 1, spawns dev agent
3. Dev agent delivers, Deskie-G reviews diff
4. Artificer validates on web UI and CLI
5. Repeat for Batch 2, then Batch 3
6. After all batches: `git add`, `git commit`, `git push`

---

## Git Strategy

One commit per batch, or one combined commit after all three. Artificer's call. Repo: `mtnshadow83/questboard`, branch: `master`.

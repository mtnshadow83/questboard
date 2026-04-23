# Questboard Dev — Ticket Audit

**Date:** 2026-04-22
**Auditor:** Deskie-G
**Source:** GitHub issue mtnshadow83/questboard#1 (Chris + Koko feedback)
**Codebase:** `questboard.py` (1,634 lines, single-file Flask + CLI)

---

## Summary

13 tickets filed (#162-174). Audited each against the codebase. 4 are confirmed reproducible bugs, 2 are likely bugs needing repro, 3 are straightforward features, 2 are larger features, and 2 are UI behavior issues.

---

## Bugs — Confirmed in Code

### #167 — `qb show` crash on non-cp1252 characters
**Severity:** Medium
**Root cause:** Line 383-409. `print()` writes to `sys.stdout` which defaults to the Windows console encoding (cp1252). Any comment or title containing characters outside cp1252 (e.g., macOS narrow non-breaking space U+202F) throws `UnicodeEncodeError`.
**Fix:** Add `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` at module top, or wrap the print calls. One-liner fix.
**Effort:** Small

### #169 — `qb list --status done` returns empty
**Severity:** Medium
**Root cause:** Line 351-352. The `cmd_list` function filters `AND s.is_closed = 0` by default when `--all` flag is not set. The "done" status has `is_closed=1` (line 121). So `--status done` matches the status filter but is then excluded by the closed filter. The two filters contradict each other.
**Fix:** When `--status` is explicitly provided, skip the `is_closed` filter. ~3 lines.
**Effort:** Small

### #170 — Web UI comments store `user_id=NULL`
**Severity:** Low
**Root cause:** Line 1359. `add_ticket_comment()` inserts with no `user_id` parameter. The web UI has no session/auth concept — there's no logged-in user to attribute to. Same issue on `log_activity` at line 1360.
**Fix:** Either add a simple session user selector to the web UI, or default to a "web" user. Requires adding a user picker or hardcoding a default.
**Effort:** Medium (needs UI work or a design decision)

### #162 — "Questboard" link should navigate to home/kanban
**Severity:** Low
**Root cause:** Line 711. The topbar `h1` element renders "Questboard" as plain text, not a link. The `@app.route("/")` at line 1194 is the kanban view, so the link target is just `/`.
**Fix:** Change the `h1` in the LAYOUT template from plain text to `<a href="/">Questboard</a>`. One-liner.
**Effort:** Small

---

## Bugs — Likely, Needs Repro

### #168 — `qb add -a` silent skip on first ticket in batch
**Severity:** Medium
**Root cause:** Not obvious from code. The argparse definition at line 1509 is standard (`--assign`, `-a`). The `cmd_add` function at line 282 resolves the user correctly. Possible causes: (a) shell quoting issue where `-a koko` gets swallowed when the title contains special characters, (b) race condition if rapid sequential adds share a DB connection, (c) argparse collision with `-a` being ambiguous (but it's the only `-a` on the `add` subparser). Needs repro with exact command sequence from Koko's session.
**Fix:** Unknown until reproduced. Add debug logging to `cmd_add` to capture resolved args before insert.
**Effort:** Unknown

### #164 — Changing assignee wipes comment box content
**Severity:** Medium
**Root cause:** Line 1341-1352. `update_ticket_assign()` posts a form and redirects to `/ticket/{id}`. If the assignee dropdown triggers a form submit while the comment textarea has unsaved content, the redirect discards it. This is standard HTML form behavior — the assignee change is a separate `<form>` but the page reload clears the comment `<form>`.
**Fix:** Either (a) make assignee update async via JS fetch (no page reload), or (b) combine assignee and comment into one form. Option (a) is cleaner.
**Effort:** Medium

---

## Features — Straightforward

### #166 — `qb edit` subcommand for title/description
**Severity:** N/A (feature)
**Assessment:** No edit command exists. Would need a new `cmd_edit` function taking `ticket_id` + `--title` and/or `--description`, plus an `activity_log` entry. Pattern is identical to existing `cmd_status` and `cmd_comment`.
**Effort:** Small (copy pattern from cmd_status, ~30 lines)

### #174 — Bulk assign, label, unlabel, move
**Severity:** N/A (feature)
**Assessment:** `cmd_done` at line 486 already accepts multiple `ticket_ids` via `nargs="+"`. Same pattern can be applied to `assign`, `label`, `unlabel`, and `move` (status). Argparse change + loop.
**Effort:** Small-Medium (mechanical, ~50 lines per command)

### #163 — Default assignee to current user
**Severity:** N/A (enhancement)
**Assessment:** Web UI only. The filter dropdowns at lines 1155-1192 don't default to any user. Could set a cookie or URL default for the assignee filter. CLI already supports `--assign` filter.
**Effort:** Small

---

## Features — Larger

### #165 — Drag-and-drop file uploads on tickets
**Severity:** N/A (feature)
**Assessment:** No file/attachment model exists in the schema. Would need: (a) new `attachments` table with `ticket_id`, `filename`, `path`, `mime_type`, `created_at`, (b) file upload endpoint, (c) storage directory, (d) UI for drag-and-drop on ticket detail and comment forms, (e) inline display for images. Significant new feature.
**Effort:** Large

### #171 — Per-project local ticket index
**Severity:** N/A (feature)
**Assessment:** Ticket IDs are global auto-increment (line 76, `id INTEGER PRIMARY KEY AUTOINCREMENT`). Adding a per-project index would need: (a) new column `project_seq` on tickets table, (b) compute on insert as `MAX(project_seq)+1 WHERE project_id=X`, (c) display as `#124 / proj-7 #14` in CLI and UI. Schema migration needed for existing data.
**Effort:** Medium

### #172 — REST/JSON endpoint alongside CLI
**Severity:** N/A (feature)
**Assessment:** Partially exists. Line 1318-1338 has `api_update_ticket_status` as a JSON endpoint. The pattern is there but only covers status updates. Extending to full CRUD would mean wrapping each `cmd_*` function as a JSON route. Already running as Flask on `:5151`.
**Effort:** Medium-Large (mechanical but wide surface area)

### #173 — Webhooks on ticket state changes
**Severity:** N/A (feature)
**Assessment:** `post_to_messageboard()` at line 184 is a primitive version of this — it writes a file on state change. Converting to HTTP POST requires: (a) webhook URL config (per-project or global), (b) POST call in `log_activity` or alongside `post_to_messageboard`, (c) retry logic. Could be done as a simple `requests.post` in the existing `post_to_messageboard` function.
**Effort:** Medium

---

## Recommended Priority

### Quick wins (spawn a dev agent, ship in one session)
1. **#167** — UTF-8 encoding fix (one-liner)
2. **#169** — `--status done` filter fix (~3 lines)
3. **#162** — Questboard link to kanban (one-liner)
4. **#166** — `qb edit` subcommand (~30 lines)

### Next batch (medium effort, high value)
5. **#170** — Web UI comment attribution
6. **#164** — Async assignee update (prevent comment wipe)
7. **#174** — Bulk operations
8. **#163** — Default assignee filter

### Needs investigation
9. **#168** — `-a` silent skip (repro first)

### Backlog (larger features)
10. **#172** — REST API expansion
11. **#171** — Per-project ticket index
12. **#173** — Webhooks
13. **#165** — File uploads

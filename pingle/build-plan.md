# Pingle — Build Plan

**Version:** 0.1  
**Operator:** Artificer  
**Agent:** General Utility  
**Timestamp:** 1777068049  
**IP:** 169.254.221.21  

---

## What We Have (v0.0 — Proof of Concept)

Working:
- Python watcher polling Questboard `activity_log` every 3s for `/pings` project events
- Windows native toast notifications via PowerShell + WinRT API
- Custom app ID registered (`Questboard.Notifications`) — toasts brand as "Questboard", not PowerShell
- "Open Ticket" button opens `localhost:5151/ticket/{id}` in browser
- "Dismiss" button closes the toast
- Logging to `notifications.log`

Issues identified from testing:
- Duplicate toasts fired when multiple watcher instances ran simultaneously
- Tkinter approach failed entirely — Claude Code's shell can't sustain a GUI mainloop
- Must launch via `powershell Start-Process -WindowStyle Hidden` for the watcher to persist

---

## What We Want (v0.1 — Shippable)

### Notification Content

Per the preferred styling screenshot:
- **Header:** "Questboard" (with gear icon — this is handled by the app ID registration)
- **Line 1:** `#{id} — {action label}` (e.g. `#222 — New ticket`, `#45 — Status: done`)
- **Line 2:** Ticket title (e.g. `Zug Zug! Job Done!`)
- **Buttons:** "Open Ticket" (opens in browser) | "Dismiss" (closes toast)

This matches what we already have. No content changes needed.

### Position & Size

Per the ideal position screenshot:
- Top-right corner of the laptop (primary) screen
- Windows toast positioning is handled by the OS — toasts always appear top-right on the primary display on Windows 11
- Size is controlled by the OS toast template — current size is correct
- **No action needed** — Windows handles this natively

### Stacking

Per the stacking screenshot:
- Multiple toasts stack downward from top-right
- Oldest on top, newest descends below
- Windows handles this natively for toast notifications
- **Max 3 visible** — Windows Action Center handles overflow; toasts beyond the visible stack go to the notification center
- **No custom slot management needed** — this was only required for the tkinter approach

### Lifecycle

- Toast displays until user dismisses or clicks "Open Ticket"
- Windows `duration="long"` keeps it visible ~25 seconds (OS-controlled)
- Can set `scenario="reminder"` to make it persist until user action — currently set, may want to test whether this is too aggressive
- **Decision needed:** Use `duration="long"` (auto-dismiss ~25s) or `scenario="reminder"` (stays until clicked)? Current build plan: keep `scenario="reminder"` for now since these are important pings

---

## Build Tasks

### Phase 1: Harden the Watcher

**Goal:** Single reliable watcher process, no duplicates, clean startup/shutdown.

- [ ] Add a PID lockfile (`pingle.lock`) to prevent duplicate watcher instances
- [ ] On startup: check lockfile, kill stale process if PID is dead, write own PID
- [ ] On exit: clean up lockfile (atexit handler)
- [ ] Add a `--once` flag for testing (poll once, send any pending toasts, exit)
- [ ] Fix the DB path reference in `notifications.py` to work from `/pingle/` subdirectory (currently hardcoded to toolsets path — should stay pointing there)

### Phase 2: Clean Up Files

**Goal:** Remove test artifacts, keep only production files.

- [ ] Delete `test_popup.py`, `test_popup.log`, `test_popup_err.log`, `test_toast.ps1` — these were proof-of-concept scaffolding
- [ ] Rename `notifications.py` → `pingle.py` (canonical entrypoint)
- [ ] Clear `notifications.log`, rename → `pingle.log`

### Phase 3: Startup Integration

**Goal:** Easy to start, easy to stop.

- [ ] Create `start.bat` — launches `pingle.py` via `powershell Start-Process -WindowStyle Hidden` (the only launch method that works from this environment)
- [ ] Create `stop.bat` — reads `pingle.lock`, kills the process
- [ ] Add CLI: `python pingle.py start` / `python pingle.py stop` / `python pingle.py status`

### Phase 4: Event Filtering

**Goal:** Only notify on meaningful events, avoid noise.

- [ ] Current filter: `action IN ('created', 'status')` — this covers new tickets, status changes, and closes
- [ ] Deduplicate: if the same ticket fires multiple activity_log entries in one poll cycle (e.g. created + label), only send one toast
- [ ] Format the action label clearly:
  - `created` → "New ticket"
  - `status` with `-> done` → "Completed"
  - `status` with `-> blocked` → "Blocked"
  - `status` with other → "Status: {new_status}"

### Phase 5: Copy to forge3

**Goal:** Keep forge3 copy in sync.

- [ ] Copy final `/pingle/` to `C:\Users\ctgau\forge3\questboard\pingle\`

---

## File Layout (Target)

```
dev/questboard/pingle/
  build-plan.md          <- this file
  pingle.py              <- watcher + toast sender, single file
  pingle.log             <- runtime log
  pingle.lock            <- PID lockfile (created at runtime)
  register_toast_app.ps1 <- one-time app ID registration
  start.bat              <- launch script
  stop.bat               <- kill script
```

---

## Non-Goals (v0.1)

- Custom toast visuals beyond what the WinRT template supports (icons, colors, progress bars)
- Sound customization (uses default Windows notification sound)
- Watching multiple boards (only `/pings` for now)
- Notification history/persistence beyond Windows Action Center
- System tray icon

---

## Dependencies

- Python 3 (stdlib only: `sqlite3`, `subprocess`, `time`, `os`)
- PowerShell (ships with Windows 11)
- Questboard DB at `library/0-system/claude/toolsets/questboard/db/questboard.db`
- Questboard web UI running on `localhost:5151` for "Open Ticket" links
- App ID registered via `register_toast_app.ps1` (already done)

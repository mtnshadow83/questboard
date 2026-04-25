# EC2 Finalization Plan

**Created:** 2026-04-25
**Goal:** Reach steady-state posture for Questboard on EC2. After this plan, the system runs unattended, survives reboots, and docs reflect reality.

---

## Current State (confirmed 2026-04-25)

Working:
- Questboard Flask app on EC2 (port 5151)
- HTTPS via Tailscale Funnel (`https://questboard-ec2.tail7f6073.ts.net/`)
- Push notifications to Pebble (confirmed — vibration enabled)
- Pingle desktop popups on Rocky (Win95 style, confirmed)
- Agent routing policy (`/pings` -> `artificer` via `qb promote`)
- Topology shelf (0.0) in library with entity registry

Fragile:
- Funnel and services run in foreground — die on reboot or SSH disconnect
- Two databases (Rocky canonical, EC2 copy) — no sync
- Git repo has uncommitted changes
- Savepoint is stale (pre-EC2)

---

## Final Posture

One database on EC2. All agents (local and remote) talk to it over Tailscale. Services survive reboots via systemd. Docs and savepoint reflect the completed state.

---

## Human Gate (decide first)

**DB access strategy — pick one:**

A. **REST API** — agents use `qb` CLI rewritten to hit `https://questboard-ec2.tail7f6073.ts.net/api/...`. Clean separation. Requires JSON endpoints (action-plan Batch 3).

B. **Single DB on EC2, CLI via SSH** — Rocky agents SSH commands to EC2 (`ssh ubuntu@100.83.251.119 qb add ...`). No new code. Slower per call.

C. **Keep split for now** — Rocky DB stays canonical for local work, EC2 is the "phone-facing" copy. Manual sync via scp when needed. Simplest, but phone notifications only fire for tickets created on EC2.

---

## Tasks

### 1. Systemd services on EC2

Make services survive reboots. No human gate.

- `questboard.service` — Flask app with `QB_HOST=0.0.0.0 QB_STATIC=/opt/questboard/visuals`
- `pingle-push.service` — push notification daemon
- Tailscale Funnel — configure via `tailscale serve` (persists across reboots natively)
- Enable + start all. Verify with `sudo reboot`.

### 2. Consolidate DB (after human gate decision)

Execute whichever strategy was chosen above.

### 3. Git commit and push

Stage all uncommitted changes on Rocky. Commit and push to `origin/master`.

### 4. Update entity registry

Update `library/0-system/topology/entity-registry.md`:
- Add HTTPS Funnel URL
- Clear the Blockers section (HTTPS resolved, push confirmed)
- Add topology history entries for Funnel + push confirmation
- Reflect DB posture decision

### 5. Drop savepoint

Write new savepoint in `forge3/savepoints/` reflecting completed state. Mark old one as superseded.

### 6. Clean up stale docs

- `pingle/build-plan.md` — add header: "v0.1 — historical, superseded by ec2-finalization-plan"
- `pingle/.artificer/create-iam-user.md` — add header: "Completed 2026-04-24"
- `forge3/savepoints/pingle-1777079193.md` — add header: "Superseded by [new savepoint]"

---

## Execution Order

```
0. Human gate: DB strategy decision (A / B / C)
1. Systemd services        — no dependency
2. DB consolidation        — depends on gate
3. Git commit              — after 1 + 2
4. Entity registry update  — after 1 + 2
5. Savepoint               — after all
6. Stale doc cleanup       — after all
```

Tasks 1 and 2 can run in parallel once the gate clears. Tasks 4-6 are documentation and can batch together at the end.

---

## Out of Scope

- Concurrent write handling (SQLite limitation — PostgreSQL migration if needed later)
- Auto-deploy pipeline (scp is fine for single-file app)
- Monitoring / alerting (overkill at current scale)
- Bug fix batches from action-plan-2026-04-23.md (separate effort)
- Muncher tools (already built, no remaining work)

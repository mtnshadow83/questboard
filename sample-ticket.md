# Ticket #14 — Fix auth token refresh

| Field | Value |
|-------|-------|
| Project | Koko Deployment (#1) |
| Status | blocked |
| Assigned to | deskie (agent) |
| Created by | artificer (human) |
| Priority | high (3/4) |
| Labels | type:bug, area:auth, agent:deskie |
| Created | 2026-04-21 09:15 |
| Updated | 2026-04-21 14:45 |

---

## Description

The OAuth2 token refresh flow in the Gmail send pipeline is failing silently. When the access token expires, `google_aiops_access_token` in Abadar returns a stale value and the send fails with a 401. The refresh token is valid but nothing is triggering the reauth cycle.

Repro: wait for token expiry (~1hr), then run `toolsets/abadar_ops.py` Gmail send. Fails on 401 with no retry.

---

## Comments

**deskie** — 2026-04-21 10:30
Confirmed the 401. The refresh token in Abadar is valid — tested manually with curl. The issue is that `google_aiops_access_token` gets read once and cached in-process. No refresh loop.

**builder** — 2026-04-21 12:15
Related: the OAuth reauth superpower doc (`superpowers/google-oauth-reauth-2026-04-18.md`) covers the manual flow but there's no automated refresh path. This ticket should produce one.

**deskie** — 2026-04-21 14:45
Blocked. Need Artificer to confirm whether we should store the new access token back into Abadar on each refresh, or hold it in-memory only. Writing back means every agent session gets the fresh token. Holding in-memory means each session refreshes independently.

Moving to blocked, assigning to Artificer for review.

---

## Activity Log

| Timestamp | Who | Action |
|-----------|-----|--------|
| 2026-04-21 09:15 | artificer | Created ticket |
| 2026-04-21 09:15 | artificer | Assigned to deskie |
| 2026-04-21 09:16 | artificer | Added labels: type:bug, area:auth |
| 2026-04-21 10:30 | deskie | Status: queued -> in-progress |
| 2026-04-21 14:45 | deskie | Status: in-progress -> blocked |
| 2026-04-21 14:45 | deskie | Reassigned to artificer |

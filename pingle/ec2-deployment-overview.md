# Pingle Remote — EC2 Deployment Overview

**Version:** 0.1  
**Operator:** Artificer  
**Agent:** General Utility  
**Timestamp:** 1777077937  

---

## What This Is

Questboard + Pingle running on an AWS EC2 instance, accessible from any device on a Tailscale private mesh. No public internet exposure. Agents write tickets, you get push notifications on your phone when something blocks.

## How It Works

### The Mesh

Every device joins a Tailscale network. Traffic between them is encrypted, peer-to-peer when possible, relayed when not. Each device gets a stable private IP (100.x.x.x). No port forwarding, no DNS, no firewall rules.

```
Phone ──── Tailscale ──── EC2 (Questboard + Pingle)
                │
             Rocky (dev client, Win95 popups)
```

### EC2 Instance

A single t3.micro (or t2.micro) running Ubuntu. Hosts:

- **Questboard** — Flask web UI bound to the Tailscale IP. Same kanban board, same CLI, same SQLite DB. Accessible from any device on the mesh.
- **Pingle** — Watches the `/pings` board. On a blocked ticket, fires a Web Push notification to your phone.

### Notifications

- **On Rocky** — Win95 PyQt5 popups (existing, works today)
- **On Phone** — Browser push notifications via the Web Push API. You open Questboard once in your phone browser, grant permission, and notifications arrive even when the tab is closed. No app install needed.

### Data Flow

```
Agent blocks a ticket
    → activity_log row written
    → Pingle polls, sees it
    → sends Web Push to phone
    → sends Win95 popup to Rocky (if running)
```

### What Gets Deployed

| Component | Where | What |
|-----------|-------|------|
| questboard.py | EC2 | Flask app + CLI + SQLite DB |
| pingle.py | EC2 | Watcher daemon, Web Push sender |
| Tailscale | EC2, Rocky, Phone | Private mesh networking |
| Service worker | Phone browser | Receives push notifications |

---

## Pricing

### EC2 Compute

**t3.micro** — 2 vCPU, 1 GB RAM. More than enough for Flask + SQLite + Pingle.

| | On-Demand | Free Tier (first 12 months) |
|---|---|---|
| Hourly | $0.0104/hr | $0.00 (750 hrs/mo) |
| Monthly | ~$7.59 | $0.00 |

### Storage

**EBS gp3** — 8 GB root volume (default).

| | Monthly |
|---|---|
| 8 GB gp3 | $0.64 |

### Data Transfer

Tailscale traffic is peer-to-peer where possible. Minimal AWS egress.

| | Monthly |
|---|---|
| First 100 GB out | Free |
| Typical usage | ~$0.00 |

### Tailscale

Free plan covers up to 100 devices, 3 users. More than enough.

| | Monthly |
|---|---|
| Personal plan | $0.00 |

### Elastic IP

Free while attached to a running instance.

| | Monthly |
|---|---|
| Attached to running instance | $0.00 |
| Idle (instance stopped) | ~$3.60 |

### Total Cost

| Period | With Free Tier | After Free Tier |
|--------|---------------|-----------------|
| **1 month** | ~$0.64 | ~$8.23 |
| **6 months** | ~$3.84 | ~$49.38 |
| **12 months** | ~$7.68 | ~$98.76 |

Free tier covers the first 12 months of a new AWS account. If your account is already past that window, the "After Free Tier" column applies. Either way, this is under $10/month for a persistent always-on server.

### Cost Notes

- Stopping the instance when not needed saves compute but incurs idle Elastic IP charges (~$3.60/mo). Running 24/7 is cheaper than frequent stop/start.
- No domain or SSL costs — Tailscale handles encryption. No public-facing infrastructure.
- Web Push is free — uses VAPID keys, no third-party push service.

---

*This system costs less than a sandwich per month and puts Questboard in your pocket.*

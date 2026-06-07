# Godot Builder — Project Context

## What This Is

A lightweight self-hosted CI/CD tool for building and deploying Godot 4 HTML5 exports to a local homelab server. Built for fast iteration during development of `vytr/industrial-flow` (Godot 4 mobile game).

## Why It Exists

Godot 4 HTML5 export requires SharedArrayBuffer → needs HTTPS Secure Context → browser won't run without it. This tool automates: git pull → godot headless export → nginx with correct CORS headers.

## Files

| File | Purpose |
|------|---------|
| `app.py` | Flask web UI (port 7777) — branch selector, manual build trigger, live log via SSE, Open Game button |
| `webhook.py` | Flask webhook receiver (port 7778) — GitHub push → auto-build in background thread |
| `build-godot.sh` | git fetch/stash/checkout/pull + `godot --headless --export-release` |
| `godot-builder.service` | systemd unit for app.py |
| `godot-webhook.service` | systemd unit for webhook.py (contains WEBHOOK_SECRET env var) |

## Infrastructure (Homelab)

| What | Detail |
|------|--------|
| Server | HP ProDesk, Ubuntu 24.04, i5-6500T, 16GB, IP `192.168.1.50` |
| DNS | dnsmasq, config `/etc/dnsmasq.conf`, resolves `*.home.local` → `192.168.1.50` |
| nginx | serves game at `https://godot.home.local`, builder UI at `http://build.home.local` |
| SSL | mkcert self-signed, trusted by Chrome via Windows cert store |
| Tunnel | Cloudflare Tunnel (`cloudflared.service`) exposes `webhook.guildbrew.app` publicly |
| SSH key | `~/.ssh/github_deploy` — passwordless deploy key added to GitHub repo (read-only) |

## Ports

| Port | Service | Public URL |
|------|---------|-----------|
| 7777 | godot-builder UI | `http://build.home.local` (local only) |
| 7778 | godot-webhook | `https://webhook.guildbrew.app/webhook` (public via Cloudflare) |
| 443 | nginx — game | `https://godot.home.local` (local only) |

## Live Status Flow
push → GitHub → webhook.guildbrew.app → webhook.py
↓
build-godot.sh <branch>
↓
/tmp/godot-build-status.json
↓
app.py GET /status (SSE stream)
↓
browser updates live



## Key Design Decisions

- No GitHub Actions — builds on homelab, no CI minutes, works without internet
- Webhook public, UI local — only webhook exposed via Cloudflare
- `git stash` before checkout — prevents `.import` file conflicts on branch switch
- Fallback `export_presets.cfg` — if branch missing it, script pulls from `main`
- SSE for live log — both manual and webhook builds stream to open browser tab
- `/tmp/godot-build-status.json` — shared state file, persists last build result across page reloads

## Game Project

| What | Detail |
|------|--------|
| Repo | `git@github.com:vytr/industrial-flow.git` |
| Cloned at | `~/industrial-flow` |
| Export preset | `Web` |
| Output | `/var/www/godot-game/index.html` |
| Godot version | 4.4.1 stable at `/usr/local/bin/godot` |
| Templates | `~/.local/share/godot/export_templates/4.4.1.stable/` |

## nginx — godot.home.local

```nginx
server {
    listen 443 ssl;
    server_name godot.home.local;
    ssl_certificate /etc/ssl/certs/godot.home.local.crt;
    ssl_certificate_key /etc/ssl/private/godot.home.local.key;
    root /var/www/godot-game;
    index index.html;
    add_header Cross-Origin-Opener-Policy "same-origin";
    add_header Cross-Origin-Embedder-Policy "require-corp";
    location / { try_files $uri $uri/ =404; }
}

Cloudflare Tunnel (/etc/cloudflared/config.yml)
tunnel: 7afb6415-d5f6-4837-9d1b-7831eb28de7c
credentials-file: /etc/cloudflared/7afb6415-d5f6-4837-9d1b-7831eb28de7c.json
ingress:
  - hostname: webhook.guildbrew.app
    service: http://localhost:7778
  - hostname: guildbrew.app
    service: http://localhost:8503
  # ... other services
  - service: http_status:404
GitHub Webhook Settings
URL: https://webhook.guildbrew.app/webhook
Content type: application/json
Secret: matches WEBHOOK_SECRET in godot-webhook.service
Events: Just the push event

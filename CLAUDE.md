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
```

## Cloudflare Tunnel (`/etc/cloudflared/config.yml`)

```yaml
tunnel: 7afb6415-d5f6-4837-9d1b-7831eb28de7c
credentials-file: /etc/cloudflared/7afb6415-d5f6-4837-9d1b-7831eb28de7c.json
ingress:
  - hostname: webhook.guildbrew.app
    service: http://localhost:7778
  - hostname: guildbrew.app
    service: http://localhost:8503
  # ... other services
  - service: http_status:404
```

## GitHub Webhook Settings

| Setting | Value |
|---------|-------|
| URL | `https://webhook.guildbrew.app/webhook` |
| Content type | `application/json` |
| Secret | matches `WEBHOOK_SECRET` in `godot-webhook.service` |
| Events | Just the push event |

---

## Task List (Priority Order)

Найдено при аудите 2026-08-03. Префикс `B-` — чтобы не путать с `T-` из Industrial Flow.

### Критично — безопасность

**B-01 — Проверка подписи вебхука отключается сама**
`webhook.py:33` — `if SECRET:`. `SECRET` читается как `os.environ.get('WEBHOOK_SECRET', '')`, дефолт пустой. Если переменная не задана или юнит перезапущен без неё, HMAC-проверка молча пропускается, и публичный эндпоинт `https://webhook.guildbrew.app/webhook` принимает запросы от кого угодно.
*Фикс:* падать на старте, если `WEBHOOK_SECRET` пуст (fail-closed), а не пропускать проверку.

**B-02 — UI слушает `0.0.0.0` без аутентификации**
`app.py:257` — `app.run(host='0.0.0.0', port=7777)`. Проверено: `LISTEN 0.0.0.0:7777`. Любой в локальной сети может открыть UI и запустить сборку любой ветки. В этом же файле выше указано «UI local only» — расходится с фактом. Сборка выполняет `git checkout` произвольной ветки и запускает Godot на её содержимом, то есть по сути исполняет код проекта.
*Фикс:* слушать `127.0.0.1`, наружу отдавать через nginx с basic-auth; либо закрыть порт файрволом. Вебхук на `127.0.0.1:7778` сделан правильно — взять за образец.

### Важно — надёжность

**B-03 — Блокировка сборки не атомарна (TOCTOU)**
`build-godot.sh:12` и `app.py:234` — «проверить существование → создать». Между шагами вклинивается второй процесс; два push подряд дают две параллельные сборки в одном рабочем каталоге. Коммит `f40566b` правил гонку, но эта осталась.
*Фикс:* `mkdir "$LOCK"` вместо `touch` (атомарно), либо `flock`. Плюс TTL на лок, иначе после падения сборки блокируются навсегда.

**B-04 — Недостижимая обработка таймаута**
`build-godot.sh:34` — `if [ $? -eq 124 ]` после `timeout`. В начале скрипта `set -e`, поэтому при коде 124 скрипт завершается ещё на строке 33 и проверка не выполняется никогда. В логе вместо «Build timed out» просто обрыв.
*Фикс:* `timeout ... || rc=$?` с явной проверкой, либо снять `set -e` на этом участке.

**B-05 — Предсказуемые пути в `/tmp` на многопользовательской машине**
`/tmp/godot-build.lock` и `/tmp/godot-build-status.json` — общий каталог, известные имена. Любой локальный пользователь может создать файл блокировки и остановить все сборки до ручного вмешательства. Симлинк-атака закрыта (`protected_symlinks=1`, `protected_regular=2`), но эти же настройки дают второй вектор: если создать файл статуса от чужого имени, процесс сборки не сможет в него записать и упадёт.
*Фикс:* перенести в `/run/godot-builder/` (через `RuntimeDirectory=` в systemd-юните) или в `~/.local/state/godot-builder/`.

### Мелочи

**B-06 — `git stash` копится бесконечно**
`build-godot.sh:22` — стеш создаётся каждую сборку и никогда не разбирается. Список растёт неограниченно.
*Фикс:* `git stash drop` после успешного checkout, либо `git checkout -f` / `git clean -fd` вместо стеша.

**B-07 — Расхождение путей к ключу**
`app.py:180` жёстко прописывает `/home/hpserver/.ssh/github_deploy`, `build-godot.sh:3` использует `~/.ssh/github_deploy`. При запуске от другого пользователя разъедется.
*Фикс:* единая переменная окружения в обоих systemd-юнитах.

**B-08 — `StrictHostKeyChecking=no`**
`build-godot.sh:3` и `app.py:180` — проверка ключа хоста отключена в обоих местах.
*Фикс:* закрепить ключ GitHub в `known_hosts` и включить строгую проверку.

### Замечание по репозиторию

Репозиторий держать **приватным**. В отличие от Industrial Flow, здесь описана инфраструктура: UUID Cloudflare-туннеля, внутренние хосты, порты, пути, схема развёртывания. Это не учётные данные, но готовая карта для поиска слабых мест.

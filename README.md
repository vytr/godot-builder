# Godot Builder

Web UI + webhook server for building Godot 4 HTML5 exports automatically.

## What it does

- `app.py` — web UI at `http://build.home.local`: select branch, trigger build, see live log, open game
- `webhook.py` — listens for GitHub push webhooks, auto-builds the pushed branch
- `build-godot.sh` — pulls the branch and runs `godot --headless --export-release`

## Requirements

- Godot 4 installed at `/usr/local/bin/godot`
- Godot export templates installed at `~/.local/share/godot/export_templates/`
- nginx serving `/var/www/godot-game` at `https://godot.home.local`
- Python 3 + Flask (`pip3 install flask`)
- SSH deploy key at `~/.ssh/github_deploy` added to GitHub repo

## Setup

```bash
# 1. Clone this repo
git clone git@github.com:vytr/godot-builder.git ~/godot-builder

# 2. Copy build script
cp ~/godot-builder/build-godot.sh ~/build-godot.sh
chmod +x ~/build-godot.sh

# 3. Install systemd services
sudo cp ~/godot-builder/godot-builder.service /etc/systemd/system/
sudo cp ~/godot-builder/godot-webhook.service /etc/systemd/system/

# 4. Set your webhook secret
sudo nano /etc/systemd/system/godot-webhook.service
# Replace: Environment=WEBHOOK_SECRET=your_secret_here

# 5. Enable and start
sudo systemctl daemon-reload
sudo systemctl enable godot-builder godot-webhook
sudo systemctl start godot-builder godot-webhook

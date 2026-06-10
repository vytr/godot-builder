#!/bin/bash
set -e
export GIT_SSH_COMMAND="ssh -i ~/.ssh/github_deploy -o StrictHostKeyChecking=no"

REPO=~/industrial-flow
BRANCH=${1:-main}
OUT=/var/www/godot-game
LOCK=/tmp/godot-build.lock
TIMEOUT=300

# Prevent parallel builds
if [ -f "$LOCK" ]; then
    echo "=== Build already in progress, aborting ==="
    exit 1
fi
touch "$LOCK"
trap "rm -f $LOCK" EXIT

echo "=== Switching to branch: $BRANCH ==="
cd $REPO
git fetch origin
git stash
git checkout $BRANCH
git reset --hard origin/$BRANCH

# Use export_presets.cfg from main if missing in branch
if [ ! -f "$REPO/export_presets.cfg" ]; then
    git -C $REPO show main:export_presets.cfg > $REPO/export_presets.cfg
fi

echo "=== Building HTML5 ==="
mkdir -p $OUT
timeout $TIMEOUT godot --headless --export-release "Web" $OUT/index.html
if [ $? -eq 124 ]; then
    echo "=== Build timed out after ${TIMEOUT}s ==="
    exit 1
fi

echo "=== Done! ==="

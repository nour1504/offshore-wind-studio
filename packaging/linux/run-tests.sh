#!/bin/bash
# Runs the server tests inside the build distribution (OffshoreWindStudio-Build), on a copy of the
# sources in the Linux file system: about a minute, against half an hour under Git Bash, where
# the exported scripts start thousands of small programs.
# Usage: run-tests.sh <repository folder seen from Linux> [pytest arguments]
set -euo pipefail
REPO="$1"
shift
WORK=/root/owsbuild/tests
rm -rf "$WORK"
mkdir -p "$WORK"
tar -C "$REPO" --exclude=backend/.venv --exclude=backend/.mypy_cache --exclude=backend/.ruff_cache \
    --exclude=__pycache__ -cf - backend | tar -C "$WORK" -xf -
find "$WORK/backend" -type f -exec chmod 0644 {} +
cd "$WORK/backend"
status=0
PYTHONPATH=src /opt/owsbuild/env/bin/python -B -m pytest -q -p no:cacheprovider --disable-warnings "$@" || status=$?
cd /
rm -rf "$WORK"
exit "$status"

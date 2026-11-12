#!/bin/bash
# Runs the server tests in the build distribution (OffshoreWindStudio-Build) on a copy of the
# sources in the Linux file system: about a minute, against half an hour under Git Bash. The
# interface sources and its example files come along for the tests that read them.
# Usage: run-tests.sh <repository folder seen from Linux> [pytest arguments]
set -euo pipefail
REPO="$1"
shift
WORK=/root/owsbuild/tests
rm -rf "$WORK"
mkdir -p "$WORK"
tar -C "$REPO" --exclude=backend/.venv --exclude=backend/.mypy_cache --exclude=backend/.ruff_cache \
    --exclude=__pycache__ -cf - backend frontend/src frontend/public/examples | tar -C "$WORK" -xf -
find "$WORK/backend" -type f -exec chmod 0644 {} +
cd "$WORK/backend"
status=0
PYTHONPATH=src /opt/owsbuild/env/bin/python -B -m pytest -q -p no:cacheprovider --disable-warnings "$@" || status=$?
cd /
rm -rf "$WORK"
exit "$status"

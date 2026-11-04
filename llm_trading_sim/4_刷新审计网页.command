#!/bin/sh
cd "$(dirname "$0")" || exit 1
set --
for name in 20261014_234547 20261014_234649 20261015_000510 20261015_000618; do
    archive="$HOME/Desktop/$name.zip"
    if [ -f "$archive" ]; then set -- "$@" --archive "$archive"; fi
done
.venv/bin/python scripts/audit_replication.py "$@" || exit 1
open audit/dashboard/index.html

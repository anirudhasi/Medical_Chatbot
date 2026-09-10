#!/usr/bin/env bash
# Usage: bash tests/run.sh [host]
# Runs every numbered question in questions.md against the running app.
HOST="${1:-http://127.0.0.1:8080}"
grep -oE '^[0-9]+\. .+' tests/questions.md | while IFS= read -r line; do
  n="${line%%.*}"; q="${line#*. }"
  printf '\n--- Q%s: %s\n' "$n" "$q"
  curl -s -m 90 -X POST --data-urlencode "msg=$q" "$HOST/get" | head -c 400
  printf '\n'
done

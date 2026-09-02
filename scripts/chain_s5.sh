#!/usr/bin/env bash
# Wait for the in-flight arm, then run the rest sequentially. Sequential on
# purpose: parallel runs would compete for the same account quota and distort
# the turn, token and timing numbers this benchmark reports.
set -u
BENCH="$(cd "$(dirname "$0")/.." && pwd)"
while pgrep -f "run_s5.sh cursor_bd" >/dev/null; do sleep 20; done
echo "cursor_bd finished $(date -u +%FT%TZ)"
for cond in cursor_nobd claude_nobd claude_bd; do
  echo "=== $cond start $(date -u +%FT%TZ) ==="
  "$BENCH/scripts/run_s5.sh" "$cond"
  echo "=== $cond end   $(date -u +%FT%TZ) ==="
done
echo "ALL FOUR ARMS DONE $(date -u +%FT%TZ)"

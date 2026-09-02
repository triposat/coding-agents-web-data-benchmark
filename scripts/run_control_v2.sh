#!/usr/bin/env bash
# Control run. Identical prompt, but the agent's PATH excludes the directory
# holding the bdata CLI, so no Bright Data path is reachable from the shell.
set -u
BENCH="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$BENCH/runs/claude_nobd_v2"
CLEAN_PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
START=$(date -u +%s)
( cd "$DIR" && PATH="$CLEAN_PATH" claude \
    -p "$(cat "$DIR/TASK_PROMPT.md")" \
    --output-format json --permission-mode bypassPermissions \
    --strict-mcp-config --mcp-config "$DIR/mcp.json" \
  ) > "$DIR/result.json" 2> "$DIR/stderr.txt"
RC=$?; END=$(date -u +%s)
printf '{"condition":"claude_nobd_v2","with_brightdata":0,"path_restricted":true,"wall_clock_s":%s,"exit_code":%s}\n' \
  "$((END-START))" "$RC" > "$DIR/meta.json"
echo "control_v2 done rc=$RC in $((END-START))s"

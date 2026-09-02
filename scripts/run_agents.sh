#!/usr/bin/env bash
# Both conditions run in an IDENTICAL environment. The only difference is
# whether the Bright Data MCP server is attached. --strict-mcp-config keeps
# every other MCP server (Apify etc.) out of both runs.
set -u
BENCH="$(cd "$(dirname "$0")/.." && pwd)"
for spec in "claude_nobd:0" "claude_bd:1"; do
  COND="${spec%%:*}"; WITH_BD="${spec##*:}"
  DIR="$BENCH/runs/$COND"
  echo "=== $COND (brightdata=$WITH_BD) start $(date -u +%FT%TZ) ==="
  START=$(date -u +%s)
  ( cd "$DIR" && claude \
      -p "$(cat "$DIR/TASK_PROMPT.md")" \
      --output-format json \
      --permission-mode bypassPermissions \
      --strict-mcp-config --mcp-config "$DIR/mcp.json" \
    ) > "$DIR/result.json" 2> "$DIR/stderr.txt"
  RC=$?; END=$(date -u +%s)
  printf '{"condition":"%s","with_brightdata":%s,"wall_clock_s":%s,"exit_code":%s}\n' \
    "$COND" "$WITH_BD" "$((END-START))" "$RC" > "$DIR/meta.json"
  echo "=== $COND done rc=$RC in $((END-START))s ==="
done

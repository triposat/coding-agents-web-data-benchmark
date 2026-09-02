#!/usr/bin/env bash
# Daniel's brief, run properly: same model, same prompt, same task across all arms.
# Cursor gets claude-sonnet-5-high, Claude Code gets claude-sonnet-5 (both plain
# Sonnet 5). The BD key is injected at run time and scrubbed afterwards, so it is
# never committed. --strict-mcp-config keeps every unrelated MCP server out.
set -u
COND="$1"
BENCH="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$BENCH/runs_s5/$COND"
[ -d "$DIR" ] || { echo "no such condition: $COND" >&2; exit 1; }

restore() {
  for f in "$DIR/.cursor/mcp.json" "$DIR/mcp.json"; do
    [ -f "$f" ] && sed -i '' 's|token=[A-Za-z0-9-]\{36\}|token=YOUR_BRIGHT_DATA_API_KEY|g' "$f"
  done
}
trap restore EXIT INT TERM

case "$COND" in *_bd)
  [ -n "${BD_KEY:-}" ] || { echo "BD_KEY unset" >&2; exit 1; }
  for f in "$DIR/.cursor/mcp.json" "$DIR/mcp.json"; do
    sed -i '' "s|YOUR_BRIGHT_DATA_API_KEY|$BD_KEY|g" "$f"
  done ;;
esac

START=$(date -u +%s)
case "$COND" in
  cursor_*)
    MODEL="claude-sonnet-5-high"
    ( cd "$DIR" && cursor-agent --print --output-format stream-json --force \
        --approve-mcps --trust --workspace "$DIR" --model "$MODEL" \
        "$(cat "$DIR/TASK_PROMPT.md")" ) \
      > "$DIR/transcript.jsonl" 2> "$DIR/stderr.txt" ;;
  claude_*)
    MODEL="claude-sonnet-5"
    ( cd "$DIR" && claude -p "$(cat "$DIR/TASK_PROMPT.md")" \
        --model "$MODEL" --output-format stream-json --verbose \
        --permission-mode bypassPermissions --add-dir "$DIR" \
        --strict-mcp-config --mcp-config "$DIR/mcp.json" ) \
      > "$DIR/transcript.jsonl" 2> "$DIR/stderr.txt" ;;
esac
RC=$?; END=$(date -u +%s)
printf '{"condition":"%s","model":"%s","wall_clock_s":%s,"exit_code":%s,"started_utc":"%s"}\n' \
  "$COND" "$MODEL" "$((END-START))" "$RC" "$(date -u -r "$START" +%FT%TZ)" > "$DIR/meta.json"
echo "$COND done rc=$RC in $((END-START))s"

#!/usr/bin/env bash
# Run one agent condition. Usage: run_agent.sh <condition> <agent> <with_bd:0|1>
set -u
COND="$1"; AGENT="$2"; WITH_BD="$3"
DIR="$(cd "$(dirname "$0")/.." && pwd)/runs/$COND"
LOG="$DIR/transcript.jsonl"; META="$DIR/meta.json"
PROMPT="$(cat "$DIR/TASK_PROMPT.md")"
START=$(date -u +%s)
echo "{\"condition\":\"$COND\",\"agent\":\"$AGENT\",\"with_brightdata\":$WITH_BD,\"started_utc\":\"$(date -u +%FT%TZ)\"}" > "$META"

if [ "$AGENT" = "codex" ]; then
  ARGS=(exec --json --skip-git-repo-check --full-auto -C "$DIR"
        --output-last-message "$DIR/last_message.txt")
  if [ "$WITH_BD" = "1" ]; then
    ARGS+=(-c "mcp_servers.brightdata.command=\"mcp\""
           -c "mcp_servers.brightdata.env={API_TOKEN=\"$BD_KEY\"}")
  fi
  codex "${ARGS[@]}" "$PROMPT" > "$LOG" 2>"$DIR/stderr.txt"
  RC=$?
else
  CLAUDE_ARGS=(-p "$PROMPT" --output-format stream-json --verbose
               --permission-mode bypassPermissions --add-dir "$DIR")
  if [ "$WITH_BD" = "1" ]; then
    CLAUDE_ARGS+=(--mcp-config "$DIR/mcp.json" --allowedTools "mcp__brightdata")
  fi
  (cd "$DIR" && claude "${CLAUDE_ARGS[@]}") > "$LOG" 2>"$DIR/stderr.txt"
  RC=$?
fi
END=$(date -u +%s)
python3 - "$META" "$START" "$END" "$RC" <<'PY'
import json,sys
m=json.load(open(sys.argv[1])); m.update(wall_clock_s=int(sys.argv[3])-int(sys.argv[2]), exit_code=int(sys.argv[4]))
json.dump(m,open(sys.argv[1],"w"),indent=2); print(json.dumps(m))
PY

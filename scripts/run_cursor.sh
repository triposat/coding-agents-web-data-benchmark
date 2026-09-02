#!/usr/bin/env bash
# Daniel's arms A and Control, in cursor-agent, non-interactive, transcripts saved.
#   run_cursor.sh cursor_bd   <model>
#   run_cursor.sh cursor_nobd <model>
set -u
COND="$1"; MODEL="${2:-}"
BENCH="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$BENCH/runs/$COND"
export PATH="$HOME/.local/bin:$PATH"

ARGS=(--print --output-format stream-json --force --approve-mcps --trust --workspace "$DIR")
[ -n "$MODEL" ] && ARGS+=(--model "$MODEL")

START=$(date -u +%s)
( cd "$DIR" && cursor-agent "${ARGS[@]}" "$(cat "$DIR/TASK_PROMPT.md")" ) \
  > "$DIR/transcript.jsonl" 2> "$DIR/stderr.txt"
RC=$?; END=$(date -u +%s)
printf '{"condition":"%s","agent":"cursor-agent","model":"%s","wall_clock_s":%s,"exit_code":%s}\n' \
  "$COND" "$MODEL" "$((END-START))" "$RC" > "$DIR/meta.json"
echo "$COND done rc=$RC in $((END-START))s -> $DIR/transcript.jsonl"

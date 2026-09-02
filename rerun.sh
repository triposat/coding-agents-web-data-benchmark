#!/usr/bin/env bash
# Durability re-run. Executes each generated tracker UNTOUCHED against the same frozen
# skus.json, plus the three fetch arms, into data/rerun_<UTC date>/ so originals survive.
#
# Targets runs_isolated/, which is the measurement the post reports. It used to point at
# runs/, which is the superseded first pass; re-running that would have measured the wrong
# thing on the right day.
#
#   BD_KEY=... ./rerun.sh
#
# The generated trackers write results.json in place, and the fetch arms overwrite
# data/arm*.json. Those files ARE the measurement the post reports and verify.py
# scores against, so this script snapshots every one of them first and restores
# them on exit, including on Ctrl-C. The re-run's own output lives only in OUT.
set -u
BENCH="$(cd "$(dirname "$0")" && pwd)"
OUT="$BENCH/data/rerun_$(date -u +%Y%m%d_%H%M)"
mkdir -p "$OUT"

# snapshot everything the re-run would clobber, and put it back afterwards
SNAP="$(mktemp -d)"
snapshot(){
  for r in cursor_bd cursor_nobd claude_nobd claude_bd; do
    [ -f "$BENCH/runs_isolated/$r/results.json" ] && \
      cp "$BENCH/runs_isolated/$r/results.json" "$SNAP/${r}_results.json"
  done
  for f in arm1_plain_http arm2_local_browser arm3_brightdata_mcp; do
    [ -f "$BENCH/data/$f.json" ] && cp "$BENCH/data/$f.json" "$SNAP/$f.json"
  done
}
restore(){
  for r in cursor_bd cursor_nobd claude_nobd claude_bd; do
    [ -f "$SNAP/${r}_results.json" ] && \
      cp "$SNAP/${r}_results.json" "$BENCH/runs_isolated/$r/results.json"
  done
  for f in arm1_plain_http arm2_local_browser arm3_brightdata_mcp; do
    [ -f "$SNAP/$f.json" ] && cp "$SNAP/$f.json" "$BENCH/data/$f.json"
  done
  rm -rf "$SNAP"
  echo "originals restored; re-run output is in $OUT"
}
snapshot
trap restore EXIT INT TERM
echo "durability re-run $(date -u +%FT%TZ) -> $OUT"
[ -z "${BD_KEY:-}" ] && echo "BD_KEY unset: the Bright Data arm will be skipped." >&2

# 1. each agent-generated tracker, run as-is, no edits
for run in cursor_bd cursor_nobd claude_nobd claude_bd; do
  d="$BENCH/runs_isolated/$run"
  # each agent named and placed its entry point differently, so look for all of them
  entry=""
  for cand in tracker.py track.py track_prices.py run.py scripts/scrape.py scripts/fetch.py; do
    [ -f "$d/$cand" ] && entry="$cand" && break
  done
  if [ -n "$entry" ]; then
    echo "-- $run/$entry"
    cp "$d/results.json" "$OUT/${run}_results_before.json" 2>/dev/null || true
    # Trackers resolve a key from BRIGHTDATA_API_KEY first, falling back to the
    # ?token= in mcp.json, which this repo ships sanitised. Export it rather than
    # editing their code: the brief says re-run each tracker untouched.
    ( cd "$d" && BRIGHTDATA_API_KEY="${BD_KEY:-}" BRIGHT_DATA_API_KEY="${BD_KEY:-}" \
      python3 "$entry" ) > "$OUT/${run}.log" 2>&1
    cp "$d/results.json" "$OUT/${run}_results_after.json" 2>/dev/null || true
    # put the published result back immediately, not at exit: a long run must never
    # leave the measured files overwritten while it is still working
    [ -f "$SNAP/${run}_results.json" ] && cp "$SNAP/${run}_results.json" "$d/results.json"
  else
    echo "-- $run: no tracker script (it called MCP directly), nothing to re-run"
  fi
done

# 2. the three fetch arms
echo "-- fetch arms"
( cd "$BENCH" && python3 scripts/run_arm_local.py ) > "$OUT/local_arms.log" 2>&1
[ -n "${BD_KEY:-}" ] && ( cd "$BENCH" && python3 scripts/run_arm_bd.py ) > "$OUT/arm_bd.log" 2>&1
for f in arm1_plain_http arm2_local_browser arm3_brightdata_mcp; do
  [ -f "$BENCH/data/$f.json" ] && cp "$BENCH/data/$f.json" "$OUT/$f.json"
done

# 3. score, including provenance
( cd "$BENCH" && python3 scripts/analyze_arms.py ) > "$OUT/summary.txt" 2>&1
( cd "$BENCH" && python3 scripts/score_provenance.py ) >> "$OUT/summary.txt" 2>&1
echo "done -> $OUT/summary.txt"

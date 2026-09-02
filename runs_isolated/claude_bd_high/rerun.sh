#!/usr/bin/env bash
# Single-command rerun of the competitor price tracker.
#
# Scraping bestbuy.com/target.com/amazon.com etc. requires getting past bot
# protection, which this sandbox can only do through the Bright Data MCP
# server (configured in mcp.json) — there is no standalone API key available
# here. So the "single command" invokes Claude Code itself, non-interactively,
# with that MCP server attached, and hands it the scraping + extraction
# instructions in rerun_prompt.md.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

claude -p \
  --mcp-config mcp.json \
  --strict-mcp-config \
  --allowedTools "mcp__brightdata__scrape_as_markdown,mcp__brightdata__scrape_batch,mcp__brightdata__search_engine,mcp__brightdata__search_engine_batch,Read,Write,Edit,Bash,Glob,Grep" \
  "$(cat rerun_prompt.md)"

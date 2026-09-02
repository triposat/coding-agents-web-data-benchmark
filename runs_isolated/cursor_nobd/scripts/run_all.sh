#!/usr/bin/env bash
# Single-command entry point for the competitor price tracker.
# Re-fetches every page in skus.json and refreshes results.json + new_listings.json.
set -e
cd "$(dirname "$0")/.."
python3 scripts/scrape.py
python3 scripts/new_listings.py
echo ""
echo "Done. Open dashboard.html (via a local server, see README.md) to view results.json."

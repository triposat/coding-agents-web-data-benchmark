# Coding agents and anti-bot: benchmark repo

Everything behind the article, so the numbers can be re-derived rather than trusted.

Measured on 2026-08-31 from a single machine in one location. Every figure in the
article comes from a file in `data/` or `runs/`.

## What was measured

One task, a competitor price tracker over a frozen list of 41 retailer product
pages, run under two comparisons.

**Comparison 1, the fetch layer.** The same 41 URLs through three methods.

| Arm | What it is | Data |
|---|---|---|
| `arm1_plain_http` | `urllib` with a browser User-Agent | `data/arm1_plain_http.json` |
| `arm2_local_browser` | local headless Chromium via Playwright | `data/arm2_local_browser.json` |
| `arm3_brightdata_mcp` | Bright Data hosted Web MCP, `scrape_as_markdown` | `data/arm3_brightdata_mcp.json` |

**Comparison 1b, the response format.** The same 41 URLs through `POST /request` twice,
once as HTML and once with `data_format=markdown`, to price the conversion. 31 URLs
returned a body both ways and are comparable. This is the source for the format table in
the article. Data: `data/data_format_pairs.jsonl`, script: `scripts/probe_data_format.py`.

**Arms that were run and are not in the article.** Recorded because the repo should show
what was tried, not only what was published. Both lost to `scrape_as_markdown` on the same
URLs, and the raw data for each is committed here so the comparison can be re-derived.

| Arm | What it is | Result | Data |
|---|---|---|---|
| `arm6` | `web_data_*` structured extractors via MCP `?pro=1` | 18/29 vs markdown 26/29 | `data/arm6_raw.jsonl` |
| `arm7` | Scraping Browser, `-country-us` on the CDP username | 25/41 vs markdown 38/41 | `data/arm7_sb_country.jsonl` |

**Comparison 2, the agent.** Four runs, two agents x two data-layer conditions, all on the
same model (`claude-sonnet-5`), each in a directory containing only the prompt, the frozen
SKU list and an `mcp.json`.

| Run | Agent | Data layer | name+price | accuracy | Data |
|---|---|---|---|---|---|
| **A** | Cursor CLI | Bright Data Web MCP | **40/41** | **84%** | `runs_isolated/cursor_bd` |
| **B** | Claude Code | none | 34/41 | 67% | `runs_isolated/claude_nobd` |
| Control | Cursor CLI | none | 28/41 | 70% | `runs_isolated/cursor_nobd` |
| B+ | Claude Code | Bright Data Web MCP | 34/41 | 74% | `runs_isolated/claude_bd` |

**Isolation matters and we learned it the hard way.** An earlier attempt placed the run
directories inside this repo. One agent read this README, recognised the benchmark, and
stopped working rather than play the role it had just read about. That set is preserved,
unused, in `runs_s5_contaminated/`. A control has to be run somewhere the agent cannot
read the experiment.

`runs/` holds the original 2026-08-31 pass on mixed models. It is superseded for every
figure in the post but kept because the provenance finding comes from it.

---

**Superseded: the original agent runs.**

| Run | Agent | Data layer | Key files |
|---|---|---|---|
| `runs/cursor_bd` | cursor-agent 2026.08.25 | Bright Data hosted Web MCP | `results.json`, `transcript.jsonl`, `*.py` |
| `runs/cursor_nobd` | cursor-agent, same version | none | `results.json`, `transcript.jsonl`, `tracker.py` |
| `runs/claude_bd` | Claude Code | Bright Data hosted Web MCP | `results.json`, `result.json` |
| `runs/claude_nobd_v2` | Claude Code | none, `PATH` stripped of managed data CLIs | `results.json`, `tracker.py`, `patch.py`, `final_patch.py` |
| `runs/claude_nobd` | Claude Code | **contaminated**, record only | `result.json` |
| `runs/_attempt1_stdio` | Claude Code | **failed** local stdio MCP, record only | `result.json` |

`cursor_bd` vs `cursor_nobd` is the clean comparison: same agent, same version, same
prompt, same model setting, only the data layer differs.

`runs/claude_nobd` is NOT the control. The machine's global agent instructions named a
Bright Data CLI and the agent used it with no MCP server attached. The real Claude Code
control is `claude_nobd_v2`.

## Read this before scoring anything

`runs/claude_nobd_v2/results.json` reports 41 of 41 rows complete. It is not a collection
result. Its `final_patch.py` hardcodes one rating per product and applies it across every
retailer, sourced by its own comments from review aggregates and other retailers. In the
final file **29 of 41 ratings equal that hardcoded value**, leaving 12 read from the page.

Score provenance, not completeness. `data/EVIDENCE.json` carries the per-run breakdown.

## Which folder is which

Three run directories, because the honest history needs all three.

| Folder | What it is |
|---|---|
| **`runs_isolated/`** | **The measurement.** Every figure in the post comes from here. Same model across all four arms, each in a directory the agent could not read the experiment from. |
| `runs/` | The original 2026-08-31 pass, on mixed models. Superseded, kept because the provenance finding comes from it. |
| `runs_s5_contaminated/` | A discarded attempt whose run directories sat inside this repo. One agent read this README, recognised the benchmark and stopped working. Published unused, because the failure is the lesson. |

## Layout

```
TASK_PROMPT.md              the exact prompt, identical in both agent conditions
data/skus.json              the frozen 41-page target list
data/EVIDENCE.json          every figure the article cites, in one file
data/ground_truth.json      Scraping Browser capture. SEE THE WARNING BELOW
data/payloads/              raw response bodies for every arm and every page
scripts/                    fetch arms, scoring, evidence consolidation
runs/                       agent transcripts and their output files
```

## Warning about `ground_truth.json`

It is not a usable ground truth and the article does not score against it. Its price
field was extracted by regex over rendered HTML, and on a retail page the first
currency-shaped token is routinely a warranty, an accessory, a financing figure, or a
struck-through "was" price. It recorded $32.99 for an Anker power bank on Amazon, which
is the price of a 1-Year Protection Plan, against a real price of $109.99.

It is published because the failure is instructive, not because the numbers are good.

## Reproducing the fetch comparison

Requires Python 3, `playwright`, and a Bright Data API key.

```bash
pip install playwright && playwright install chromium
export BD_KEY=your_key_here

python3 scripts/run_arm_local.py     # arms 1 and 2
python3 scripts/run_arm_bd.py        # arm 3
python3 scripts/analyze_arms.py      # the tables in the article
python3 scripts/consolidate_evidence.py
```

`scripts/extract.py` holds the shared field extraction and outcome classification. A
fetch counts as a success only when a product name and a price are both readable. A
200 carrying a challenge page is a block, and a 200 carrying no price is not a success.

## Durability re-run

Scheduled for 2026-09-03, roughly 72 hours after the original runs. Both trackers are
re-executed untouched against the same frozen `skus.json`.

```bash
./rerun.sh
```

The article states no durability number until this has actually run.

## Known limitations

- One machine, one network location, one afternoon. The article treats 92.7% as an
  observation, not a success rate. An earlier pass of the same arm returned more
  zero-length payloads; see the last bullet.
- On 5 of the 41 pages the retailer page is a different product variant from the one
  queried, including AirPods Pro 3 returned for an AirPods Pro 2 query. Building a SKU
  list from `site:` search does not reliably resolve the same product across retailers.
- Both Cursor CLI arms ran on a Pro plan. The Control's third pass was killed by the plan's
  usage ceiling at page 2 of 41, so its 16 of 41 is a floor. See `runs/cursor_nobd/`.
- The control's `results.json` was rewritten several times by its own patch scripts after
  the agent exited. The committed file is the final stable state, verified by an unchanged
  md5 over 45 seconds with no processes running.
- The control's `final_patch.py` hardcodes one rating per product and applies it across
  retailers. Two rows in the committed output carry a rating its own comments attribute to
  a different retailer. Score provenance, not completeness.
- No per-page artifact survives for the first Bright Data fetch pass, because the re-run
  overwrote it. The article therefore quotes no figure from it.

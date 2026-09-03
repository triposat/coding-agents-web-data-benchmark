# Coding agents and anti-bot: benchmark repo

The data and scripts behind the article's published figures, so the numbers can be re-derived rather than trusted.

```bash
python3 verify.py            # print the figures from the data
python3 verify.py post.md    # check a copy of the post against them
```

With no argument it prints the figures it checks straight from the data. Given an
article file it re-derives each one and checks the article still says it. No network
and no credentials either way. For table figures it compares specific cells, so a wrong cell fails even when the right
number appears elsewhere; prose figures are checked by presence. It also fails if any of
the four credentials used during the benchmark appears in a `.py`, `.sh`, `.json`, `.md`,
`.txt` or `.jsonl` file in the tree. It does not scan for other keys.

`claims.json` carries the per-arm figures as data: 39 claims, each with the file it came
from and the script that computed it, so an agent can check those figures in the post
without parsing prose. The blocked counts, the Best Buy count and the line counts are
checked by `verify.py` only. Regenerate with `python3 scripts/emit_claims.py > claims.json`.

The fetch arms were measured on 2026-08-31 and the agent runs on 2026-09-01 and
2026-09-02, from a single machine in one location. Every measured figure in the article
comes from a file in `data/` or `runs_isolated/`, except the provenance finding, which
comes from `runs/claude_nobd_v2`; the third-party statistics it cites are linked to their
sources.

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

**Other Bright Data surfaces, run but not used for the article's numbers.**

| Arm | What it is | Data |
|---|---|---|
| `arm6` | `web_data_*` structured extractors via MCP `?pro=1` | `data/arm6_raw.jsonl`, retested in `data/web_data_retest.json` |
| `arm7` | Scraping Browser, `-country-us` on the CDP username | `data/arm7_sb_country.jsonl` |

**`arm6_raw.jsonl` records 18 of 29 and is superseded.** `web_data_*` calls start
asynchronous collection jobs, and that pass capped the client at 180 seconds; three pages
returned at 201, 234 and 308 seconds. With a 10-minute ceiling the same calls returned
**26 of 29, exactly what `scrape_as_markdown` read on the same retailers**, recorded in
`data/web_data_retest.json`. The article uses the markdown path because it is one call
with no polling, not because the structured path collected less.

`arm7` was capped the same way at 150 seconds. No figure from it appears in the article.

**Comparison 2, the agent.** Four runs, two agents x two data-layer conditions, plus an
effort-matched fifth, all on the same model (`claude-sonnet-5`), each in a directory containing only the prompt, the frozen
SKU list and an `mcp.json`.

| Run | Agent | Data layer | name+price | accuracy | Data |
|---|---|---|---|---|---|
| **A** | Cursor CLI | Bright Data Web MCP | **40/41** | **89%** | `runs_isolated/cursor_bd` |
| **B** | Claude Code | none | 34/41 | 72% | `runs_isolated/claude_nobd` |
| Control | Cursor CLI | none | 28/41 | 74% | `runs_isolated/cursor_nobd` |
| B+ | Claude Code | Bright Data Web MCP | 34/41 | 78% | `runs_isolated/claude_bd` |
| B+ matched | Claude Code, `--effort high` | Bright Data Web MCP | 35/41 | 88% | `runs_isolated/claude_bd_high` |

Accuracy is scored against `data/ground_truth_hand.json`, 41 pages and 100 hand-adjudicated
values. `python3 verify.py` prints this table from the data and fails if the rows above
have drifted from it, so a drift between this table and the post fails the check.

**A control has to run where the agent cannot read the experiment.** An earlier set put
the run directories inside this repo; one agent read this README, recognised the benchmark
and stopped. That set is in `runs_s5_contaminated/` and no figure comes from it.

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

Within that superseded set, `cursor_bd` vs `cursor_nobd` is the like-for-like pair: same
agent, same version, same prompt, same model setting, only the data layer differs.

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

Three run directories.

| Folder | What it is |
|---|---|
| **`runs_isolated/`** | **The measurement.** Every agent-run figure in the post comes from here. Same model across all four arms, each in a directory the agent could not read the experiment from. |
| `runs/` | The original 2026-08-31 pass, on mixed models. Superseded; the provenance finding comes from it. |
| `runs_s5_contaminated/` | Run directories that sat inside this repo, where one agent read this README, recognised the benchmark and stopped. No figure comes from it. |

## Layout

```
verify.py                   re-derives 40 published figures; run it first
claims.json                 the same figures as data, 39 of them, with provenance
TASK_PROMPT.md              the exact prompt, identical in every agent condition
rerun.sh                    re-executes the trackers untouched, for durability

runs_isolated/              THE MEASUREMENT. five arms, transcripts and results
runs/                       the superseded 2026-08-31 pass on mixed models
runs_s5_contaminated/       runs that could read the experiment; unused

data/skus.json              the frozen 41-page target list
data/ground_truth_hand.json 41 pages, 100 hand-adjudicated values, and the corrections
data/EVIDENCE_isolated.json per-arm rollup for the runs the article scores
data/EVIDENCE.json          the same, for the superseded runs/ pass
data/ground_truth.json      an early regex capture. SEE THE WARNING BELOW
data/payloads/              the captures the published figures are scored from:
                            gt__ for the hand-adjudicated ground truth, arm3__ for
                            the token counts. The other arms' captures are not
                            republished; the collection scripts regenerate them
scripts/                    fetch arms, probes, scoring, evidence consolidation
demo/, demo-control/        the IDE walkthrough behind the article's screenshots
images/                     the seven screenshots the article publishes
```

## Warning about `ground_truth.json`

It is not a usable ground truth and the article does not score against it. Its price
field was extracted by regex over rendered HTML, and on a retail page the first
currency-shaped token is routinely a warranty, an accessory, a financing figure, or a
struck-through "was" price. It recorded $32.99 for an Anker power bank on Amazon, which
is the price of a 1-Year Protection Plan, against a real price of $109.99.

## Measuring the refusal layer, not just the outcome

Two probes ask *why* a site refuses rather than *whether* it did.

| Script | Question | Data |
|---|---|---|
| `scripts/probe_fingerprints.py` | what does a server actually see from each client | `data/fingerprints.json` |
| `scripts/probe_refusal_layer.py` | at which layer do 15 sites refuse | `data/refusal_layer.json` |
| `scripts/probe_ip_vs_fingerprint.py` | does changing the egress move what hardening could not | same file |
| `scripts/probe_tool_groups.py` | what the MCP server's `GROUPS` selector exposes | — |

The first two need no credentials. The third needs `BD_KEY`.

Headline: in this probe, three Chromium variants, default, hardened and headful, produced a byte-identical
HTTP/2 fingerprint, and JA3 was not stable enough across those clients to serve as a key. Across 15
sites, 11 treated all three local clients the same.

## Reproducing the fetch comparison

Requires Python 3, the packages in `requirements.txt`, and a Bright Data API key.
`verify.py` needs only Python 3: no packages and no key.

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

Both Cursor trackers are re-executed untouched against the same frozen `skus.json`.

```bash
./rerun.sh
```

It snapshots each run directory first and restores it afterwards, because the trackers
write `results.json` in place and that file is the measurement.

The article publishes a 24-hour checkpoint from this: 40 to 35 pages for A, 28 to 20 for
the Control, with Best Buy the only retailer that moved in either arm. It labels that as
the checkpoint it is. A 24-hour window catches the fastest-moving defence and nothing
slower, so nothing here is a settled durability number.

## Known limitations

- One machine, one network location, one afternoon. Every figure here is an observation
  from a single vantage point, not a success rate, and the same arm run twice on the same
  afternoon did not return an identical number.
- On 5 of the 41 pages the retailer page is a different product variant from the one
  queried, including AirPods Pro 3 returned for an AirPods Pro 2 query. Building a SKU
  list from `site:` search did not reliably resolve the same product across retailers here.
- In the superseded `runs/` pass, the Control's third attempt was killed by a plan usage
  ceiling at page 2 of 41, so the 16 of 41 in `runs/cursor_nobd/` is a floor rather than a
  result. The article's Control is the isolated re-run, `runs_isolated/cursor_nobd`, at 28
  of 41. Don't read the two as the same arm.
- The control's `results.json` was rewritten several times by its own patch scripts after
  the agent exited. The committed file is the final state.
- The control's `final_patch.py` hardcodes one rating per product and applies it across
  retailers. Two rows in the committed output carry a rating its own comments attribute to
  a different retailer.
- No per-page artifact survives for the first Bright Data fetch pass, because the re-run
  overwrote it. The article therefore quotes no figure from it.

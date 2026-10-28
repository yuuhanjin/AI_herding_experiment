# Curated research data

This directory contains the small, versioned evidence package used by the
offline analyses and reports in this repository. It lets every team member
reproduce the published tables and figures without access to another person's
local `logs/` directory or API key.

## What is included

- `runs/fig6_*`: the four 15-round Figure 6--7 runs (two baseline and two
  market-maker prompt contrasts).
- `runs/prompt_probe_*`: three repeats of each one-round prompt-hierarchy arm.
- `traces/`: the full three-arm comparison trace for each probe repeat.
- `manifest.json`: stable run IDs, provenance, file sizes, and SHA-256 hashes.

Each curated run retains the parameters, metadata and token usage; rendered
system/user prompts; structured agent decisions; accepted orders; trades;
market records; dividends; agent records; and the order-state audit needed by
the analyses. The latter is stored as `order_state.txt` so Git does not hide it
under the repository-wide `*.log` rule. Empty trade files are intentional: they show that a run had no
executed trades.

## What is not included

The complete simulator logs, caches, plots, and temporary files remain under
the Git-ignored `logs/` directory. `.env` and API credentials are never copied.
The curated package is research evidence, not a replacement for raw archival
storage.

## Rebuild from local raw logs

From the repository root:

```bash
python scripts/prepare_curated_data.py
```

The source paths are declared explicitly in that script. After rebuilding,
review `data/manifest.json` and the Git diff before committing changes.

## Reproduce the offline outputs

These commands make no API calls:

```bash
python scripts/analyze_fig6_fig7_canonical.py
python scripts/analyze_prompt_hierarchy_probe.py
python scripts/build_report_price_panels.py
```

Generated figures and summary tables are written to `docs/figures/` and
`docs/tables/`.

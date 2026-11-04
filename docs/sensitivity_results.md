# Sensitivity Test Results (reduced design + replications)

Run on 2026-11-04 with the course OpenAI key. 30 paid 15-round runs plus 2 pipeline tests, 3,840 LLM calls, all successful. Total cost: $18.03.

Setup: these runs used Xinyi's earlier `upload-ai-herding` code plus a local order-size cap, preserved exactly on branch `ruixin/sensitivity-runs` (commit `98b4e1d`):
- `max_order_size = 1000` was shown in each agent's prompt and oversized orders were **clipped** to 1,000 shares (logged with the requested size). Only 11 orders were clipped across all runs (at most 3 per run).
- Xinyi's current branch implements the cap differently (`order_size_mode = "enforced"` rejects oversized orders instead of clipping). This PR drops the local cap code in favour of hers, and `run_sensitivity.py` now sets `enforced` mode, so future reruns follow her rule. Given how few orders were affected, this should change little, but reruns will not match these runs exactly.
- Every run replays one of three fixed dividend paths (D1 to D3) with a fixed order seed (`DIVIDEND_CONTROL` replay mode). The dividend audit passed in every run.

Baseline: `gpt-4o-2024-11-20`, temperature 0, original prompts, 8 agents (2 default, 2 optimistic, 2 market maker, 2 speculator), 15 rounds, V = $28. The primary price is the last executed trade (`last_execution_price_to_date`); "no trade" means no transaction in all 15 rounds.

Reproduce: `scripts/run_sensitivity.py --design reduced --blocks pilot A B C D E R` and `scripts/analyze_sensitivity.py`. Per-run outputs: `docs/tables/sensitivity_summary.csv`, figure `docs/figures/sensitivity_summary.png`.

## Results by block

| Block | Runs | Trades per run | Last trade at round 15 | Converged (PE < 10%) |
|---|---|---|---|---|
| Baseline $56 (pilot ×2, A D1–D3, R seeds 2–5) | 9 | 0 in 8 runs; 14 in 1 | none, or $50.40 | 0 / 9 |
| Baseline $14 (A D1–D3, R seeds 2–5) | 7 | 0 in 5 runs; 6 and 27 in 2 | none, $16.30, $30.01 | 1 / 7 |
| B: start $35 | 1 | 30 | $33.55 | No |
| B: start $21 | 1 | 0 | none | No |
| C: temperature 1.0, $56 / $14 | 2 | 15 / 21 | $54.89 / $14.67 | No / No |
| D: paraphrase p1, p2 at $56 | 2 | 0 / 4 | none / $50.40 | No / No |
| D: paraphrase p1, p2 at $14 | 2 | 21 / 10 | $16.10 / $16.20 | No / No |
| E: gpt-4o-mini at $56 (D1–D3) | 3 | 28, 46, 25 | $49.00, $37.00, $54.00 | 0 / 3 |
| E: gpt-4o-mini at $14 (D1–D3) | 3 | 55, 26, 58 | $16.75, $16.85, $15.40 | 0 / 3 |

## Findings

1. **Run-to-run noise is large at temperature 0.** The two pilot runs used identical settings (model, temperature, LLM seed, dividend path, order seed). One had no trades, the other 14. Across the seven $14 baseline runs, outcomes ranged from no trades to convergence at $30.01. Single runs per setting cannot separate treatment effects from this noise.

2. **The overpriced market does not converge (robust).** None of the 15 runs starting at $56 converged, across dividend paths, seeds, temperature, prompt wording and model. At baseline, market makers never bid (buy share 0% in all 9 runs) and 8 of 9 runs had no trade. The recorded price still fell to $45–52 through the quote fallback.

3. **The underpriced market usually does not converge (paper's claim not supported).** Only 1 of 12 runs starting at $14 converged (baseline, D2). In 5 of 7 baseline runs nobody traded: every agent, including market makers (buy share 91% on average), valued the asset at $28 and only placed bids. In the converging run, bids ratcheted the recorded price up without trades until default agents sold at about $30.

4. **The no-trade outcome is sensitive to temperature, wording and model.** At temperature 1.0, with some paraphrased prompts, and with gpt-4o-mini, markets did trade (10 to 58 trades) and market makers quoted both sides more often. Prices still stayed near the starting level, so more trading did not produce price discovery.

5. **Smaller mispricing:** from $35 the market traded and moved about 19% of the way toward $28; from $21 nothing traded. One run each, so this is descriptive.

6. **Belief homogeneity is robust within GPT-4o, not across models.** Every GPT-4o run had a median non-optimist valuation of $28. gpt-4o-mini sometimes reported $14 or $20 at the $14 start.

## Status of the protocol's conclusions

| ID | Conclusion | Result |
|---|---|---|
| C1 | Overpriced market does not converge in 15 rounds | Robust: 0 of 15 runs |
| C2 | Underpriced market converges toward $28 | Not supported: 1 of 12 runs |
| C3 | Correction from below exceeds correction from above | Inconclusive: most baseline runs have no trades in either direction |
| C4 | At $56 no trades occur because no agent bids | Holds at baseline (8 of 9), fragile to temperature, wording and model |
| C5 | Market makers quote both sides more than directional agents | Fragile: market makers rarely quote both sides at baseline (0% at $56, 10% at $14) |
| C6 | Non-optimistic agents report a $28 valuation | Robust within GPT-4o; not across models |

## Caveats

- Blocks B to E have one run per setting. Given the noise in finding 1, differences between these single runs and the baseline are descriptive, not causal.
- These runs use Xinyi's code plus the order-size cap, not the code behind the October runs. In October the $14 baseline had 23 trades; here most $14 baseline runs had none. We cannot yet tell whether this comes from the code version, the cap shown in the prompt, or run-to-run noise.
- Market makers start with 20 times the other agents' cash and shares.

# Sensitivity-Test Protocol

**Goal.** Our 10/15 conclusions each rest on one GPT-4o run. This protocol tests whether they survive changes in dividend path, LLM seed, temperature, prompt wording, model and starting price (Q4), and which conclusions are robust (Q5). Setting: 15-round infinite-horizon market, 8 agents (2 default, 2 optimistic, 2 market maker, 2 speculator), V = $28, no short selling, baseline `gpt-4o-2024-11-20`, T = 0, original prompts.

## Gates before running

**Gate 1: Price measure.** `src/market/data_recorder.py` already records the last executed trade and post-match midpoint. With no trade, the simulator records the best ask as the price, so our $56 runs fell from $56 to $46 with zero volume. Primary outcome: **last executed trade price** (carried forward). Secondary: post-match bid-ask midpoint when both sides are quoted. The simulator's recorded price is reported only for comparison with the paper.

**Gate 2: Dividend control.** Dividend draws used to share Python's global random stream with the agent and order shuffles. Because the number of draws the shuffles use depends on how many orders the LLM submits, our two seed-42 $56 runs had different dividend paths from round 5 (cumulative dividends $19.6 vs $23.6).

Implemented on branch `ruixin/sensitivity`: setting `DIVIDEND_SEED` gives dividend and shock draws their own generator (`src/services/random_streams.py`), while `RANDOM_SEED` keeps controlling agent and order sequencing and `LLM_SEED` the API seed. Leaving `DIVIDEND_SEED` unset keeps the old behaviour. Offline checks: `tests/test_dividend_seed_isolation.py` passes; `scripts/matched_seed_regression.py` shows all 13 existing seeded scenarios unchanged; and a 15-round deterministic run with a different agent mix gives an identical dividend path with `DIVIDEND_SEED` set but diverges from round 7 without it. Dividend paths D1 to D3 below correspond to `DIVIDEND_SEED` 1 to 3.

## Experimental design

Each block changes one factor and holds the rest at baseline. Within a block, all levels use the same dividend paths (D1 to D3), so differences can be attributed to the factor.

| Block | Varies | Grid | Runs | Question |
|---|---|---|---|---|
| Pilot | Nothing | Baseline cell ($56, D1, seed 1) run twice | 2 | Noise floor: how much GPT-4o varies at T = 0 with a fixed seed |
| A | Dividend path, LLM seed | {$56, $14} × {D1, D2, D3} × seed {1, 2} | 12 | Is variation driven by dividend luck or LLM sampling? |
| B | Starting price | {$35, $21} × {D1, D2, D3}, seed 1 | 6 | Does smaller mispricing converge? Is correction symmetric? |
| C | Temperature | {0.5, 1.0} × {$56, $14} × D1 × seed {1, 2} | 8 | Q4 temperature (T = 0 from Block A) |
| D | Prompt wording | Paraphrase families p1 to p4 × {$56, $14} × D1, seed 1 | 8 | Q4 wording (p0 = original, from Block A) |
| E | Model | `gpt-4o-mini` × {$56, $14} × {D1, D2, D3}, seed 1 | 6 | Q4 model |

Total: 42 runs, about $26 (about $0.72 per GPT-4o run from our 10/15 usage logs; `gpt-4o-mini` under $1 in total), under 2 hours sequentially.

### Cost-saving version

| Block | Varies | Reduced grid | Runs |
|---|---|---|---|
| Pilot | Nothing | Baseline cell run twice | 2 |
| A | Dividend path | {$56, $14} × {D1, D2, D3}, seed 1 only | 6 |
| B | Starting price | {$35, $21}, D1 only | 2 |
| C | Temperature | T = 1.0 only × {$56, $14} | 2 |
| D | Prompt wording | 2 paraphrase families × {$56, $14} | 4 |
| E | Model | `gpt-4o-mini` × {$56, $14} × {D1, D2, D3} | 6 |

Total: 22 runs (16 GPT-4o, 6 GPT-4o-mini), about $12. With one run per setting, results can only be compared descriptively; the 80% robustness rule below needs the full design.

In either version, we first test the pipeline with `gpt-4o-mini` (about $0.04 per run), then run GPT-4o in two batches: the pilot and Block A first, and the remaining blocks only if the first batch shows enough variation to justify them.

## Outcomes (fixed in advance)

The run is the unit of analysis.

- **Price discovery** (last-trade price): PE_15 = |P_15 − 28| / 28; converged if PE_15 < 0.10; number of zero-volume rounds; total volume.
- **Behaviour** (existing `q2_q3_analysis.py`): market-maker two-sided share, directionality, depth share; agents' reported valuations.

## Robustness rule

A conclusion is **robust** if it holds in at least 80% of runs at every level of every factor, and **fragile** if any factor level reverses it in most runs.

| ID | Conclusion tested |
|---|---|
| C1 | The overpriced ($56) market does not converge within 15 rounds |
| C2 | The underpriced ($14) market converges toward $28 (paper's claim; our 10/15 runs disagree) |
| C3 | Correction from below is larger than from above |
| C4 | At $56, no trades occur because no agent bids |
| C5 | Market makers quote both sides more often than directional agents |
| C6 | All non-optimistic agents report a valuation of $28 |

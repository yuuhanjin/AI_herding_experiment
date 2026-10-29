# Q2/Q3: Persona Behaviour and Market-Maker Liquidity (preliminary)

Data: the four Figure 6 runs in `data/runs/fig6_*` (GPT-4o, T = 0, seed 42, 8 agents, 15 rounds, V = $28). No LLM calls.
Reproduce with `python scripts/analyze_q2_q3_persona_liquidity.py`. Outputs: `docs/tables/q2_q3_metrics_by_persona.csv`, `docs/tables/q2_q3_tests.csv`, `docs/figures/q2_q3_by_persona.png`, `docs/figures/q3_book_depth_by_side.png`.

Metric definitions are in the script docstring. All counts use accepted orders (holds excluded).

## Key numbers

| Run | Persona | Orders | Limit % | Two-sided % | Dist. to price % | Directionality | Buy % | Depth share % |
|---|---|---|---|---|---|---|---|---|
| $56 baseline | Market maker | 56 | 100 | 0 | 2.17 | 1.00 | 0 | 72.8 |
| $56 prompt adjusted | Market maker | 73 | 100 | 0 | 2.18 | 1.00 | 0 | 68.9 |
| $14 baseline | Market maker | 67 | 100 | 50 | 1.00 | 0.51 | 75 | 46.3 |
| $14 baseline | Default / Spec. / Opt. | 52 / 40 / 30 | 100 / 95 / 0 | 0 | 0.67 / 0.84 / – | 1.00 | 100 | 17.5 / 36.2 / 0 |
| $14 prompt adjusted | Market maker | 82 | 100 | 100 | 2.93 | 0.04 | 51 | 62.7 |
| $14 prompt adjusted | Default / Spec. / Opt. | 26 / 25 / 30 | 100 / 96 / 0 | 0 | 2.83 / 2.89 / – | 1.00 | 100 | 19.5 / 17.9 / 0 |

At $56 every persona only sells, so every persona has directionality 1.00 and buy share 0%.

## Q2: Are personas distinguishable?

Partly. Order type differs by persona (chi-square p < 0.001 in both the $56 and $14 runs), mainly because optimistic agents use market orders at $14 while the others use limit orders. Trade direction barely differs: at $56 everyone sells, and at $14 every non-market-maker persona only buys. All non-optimistic agents report the same $28 valuation, so the persona labels change order style more than trading direction.

## Q3: Do market makers provide more liquidity?

| Expected behaviour | Result |
|---|---|
| Larger share of limit orders | Weak: market makers 100%, but default and speculator agents already 95–100% |
| Orders on both sides of the book | Only at $14: 50% of rounds (baseline), 100% (prompt adjusted); 0% at $56 |
| Quotes closer to best bid/ask | No: market makers ladder several levels and quote farther from the price (one-sided Mann-Whitney p = 0.96 at $14) |
| Disproportionate depth | Yes: 2 of 8 agents hold 46–73% of resting book quantity |
| Less directional | Yes at $14 (0.51 and 0.04 vs 1.00, p < 0.001); no at $56 |

The no-short-selling wording made market makers clearly two-sided at $14 (51% buys, directionality 0.04) but did not change their behaviour at $56, where their $28 valuation keeps them from bidding.

## Caveats

- One seed per scenario, two agents per persona; agent-rounds are treated as independent in the tests, so p-values overstate confidence.
- Market makers start with 20x the cash and shares of other agents, so part of their depth share reflects inventory.
- The paired baseline and prompt-adjusted runs had different dividend paths (see `docs/sensitivity_protocol.md`, Gate 2).
- These runs use the paper's default / optimistic / speculator / market-maker mix, not the project's value / momentum / market-maker design.

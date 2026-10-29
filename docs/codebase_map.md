# Team Codebase Map

This guide is the shared starting point for the AI Herding experiment. It is
written for both technical and non-technical project members: start with the
overview, then follow the links relevant to your role.

## 1. Repository names and branches

To avoid ambiguity, use these names in meetings and notes:

| Name | Meaning |
|---|---|
| **LLMTS upstream** | The paper author's public repository, `alejandroll10/llm_trading_sim` |
| **AHE** | Our collaborative repository, `yuuhanjin/AI_herding_experiment` |
| **AHE `main`** | An unchanged baseline copied from the current LLMTS upstream commit |
| **AHE `Yuhan`** | Yuhan's research branch: instrumentation, experiments, curated data, analyses, and reports |

The paper predates the earliest visible public LLMTS commit. Therefore, the
current repository is useful for computational replication, but it is not
proof that we possess the exact code and prompts used to create the paper's
figures.

## 2. Start here by role

| If you want to... | Read or run... |
|---|---|
| Understand the research result | `docs/prompt_mechanism_findings.html` and `docs/fig6_fig7_canonical_analysis.md` |
| Understand the paper | `docs/paper_summary.md` |
| Inspect the exact evidence | `data/README.md`, then `data/manifest.json` |
| Rebuild figures and tables | `scripts/analyze_fig6_fig7_canonical.py` and `scripts/analyze_prompt_hierarchy_probe.py` |
| Understand a simulation round | Sections 4--6 of this document |
| Change a scenario | `src/scenarios/`, especially `src/scenarios/paper_scenarios.py` |
| Study prompts or agent behavior | `src/agents/prompts/`, `src/agents/LLMs/`, and the rendered prompts in `data/runs/` |
| Study matching and prices | `src/market/engine/`, `src/market/orders/`, and `src/market/data_recorder.py` |
| Run a new paid experiment | Read Section 9 first; then use the relevant runner in `scripts/` |

## 3. Repository layout

```text
llm_trading_sim/
├── src/                         Simulator source code
│   ├── run_base_sim.py          Main command-line entry point
│   ├── base_sim.py              Round orchestration
│   ├── scenarios/               Experimental configurations
│   ├── agents/                  Agent types, prompts, decisions, portfolios
│   ├── market/                  Order book, matching, trades, price updates
│   ├── analysis/                General estimators
│   └── visualization/           Simulator plotting utilities
├── scripts/                     Research runners and offline analyses
├── tests/                       Simulator and research regression tests
├── data/                        Small, versioned, auditable evidence package
│   ├── runs/                    Stable run IDs (no timestamp lookup required)
│   ├── traces/                  Prompt-intervention traces
│   └── manifest.json            Provenance and SHA-256 checksums
├── docs/                        Reports, figures, tables, and presentation page
├── logs/                        Full local run output; ignored by Git
├── README.md                    Original simulator documentation
└── .env                         Local API configuration; ignored by Git
```

`data/` and `logs/` have different purposes. `data/` contains the minimum
evidence that collaborators need to audit the reported findings. `logs/`
contains large raw local outputs and is not shared through Git. Secrets belong
only in `.env`; they must never appear in either directory.

## 4. What happens in one simulation round

The central controller is `src/base_sim.py`. One round follows this sequence:

```text
scenario parameters
       │
       ▼
update market state and information
       │
       ▼
build one prompt per agent ──► call the LLM ──► structured decision
       │                                           │
       │                                           ▼
       └──────────────────────────────────── validate/create orders
                                                   │
                                                   ▼
                                         match against the order book
                                                   │
                         ┌─────────────────────────┴──────────────────────┐
                         ▼                                                ▼
                 executed trades                                  resting orders
                         └─────────────────────────┬──────────────────────┘
                                                   ▼
                                update recorded price and market state
                                                   │
                                                   ▼
                         record prompts, decisions, orders, trades, prices
```

The simulator repeats this lifecycle for `NUM_ROUNDS`. In the Figure 6--7
setup there are eight agents and 15 rounds, so a completed scenario contains
120 agent-round decisions.

## 5. How an agent prompt and decision are created

The main path is:

1. `src/scenarios/*.py` supplies the agent composition, model settings,
   capital, inventory, and market parameters.
2. `src/agents/agent_factory.py` creates each agent.
3. `src/agents/LLMs/llm_agent.py` selects the agent type's system prompt and
   formats its user-prompt template with current market and portfolio data.
4. Optional memory, social, and self-modification sections are appended by
   `src/agents/LLMs/services/prompt_builder.py`.
5. `src/agents/LLMs/services/llm_services.py` sends system and user messages
   to the configured model and validates the structured response schema.
6. The exact rendered pair is saved to `data/rendered_prompts.jsonl` in each
   run, allowing later verification of what the model actually saw.

Important distinction: a scenario parameter is not automatically an LLM
instruction. For example, `BASE_MAX_ORDER_SIZE = 1000` is present in scenario
defaults, but our prompt probe found an accepted 100,000-share order under the
earliest-public prompt. When studying implementation compliance, verify all
three layers separately:

- what the scenario declares;
- what the rendered prompt tells the model;
- what the order-validation code enforces.

## 6. From decisions to orders, trades, and prices

### Orders and matching

Agent decisions become orders through the services under
`src/agents/agent_manager/services/`. Portfolio constraints can reject an
order before it reaches the market. Accepted orders then enter the matching
engine in `src/market/engine/match_engine.py`.

The order book uses price-time priority: a more competitive price is matched
first, and an earlier order has priority among orders at the same price. An
order can be fully filled, partially filled, or remain unfilled. Market orders
can match one another or walk resting liquidity; crossing limit orders can
also execute against the book.

### Recorded price

The recorded price is not always a transaction price. The rule in
`src/market/engine/services/trade_processing_service.py` is:

1. if trades occur, use the final trade price;
2. otherwise, call the order-book price rule;
3. if the book has no usable quote, keep the previous price.

`src/market/orders/order_book/order_book_queries.py` currently returns the
best ask when sell orders exist (including a two-sided book), or the best bid
when only buy orders exist. This explains why the recorded price can move in a
round with zero trades. Such a move is quote-driven, not transaction-driven.

For research, keep these measures separate:

| Measure | Meaning |
|---|---|
| Recorded price | Simulator state; may be updated from an order-book quote |
| Last executed trade | Price at which shares actually changed hands |
| Best bid / best ask | Highest resting buy quote / lowest resting sell quote |
| Midpoint | Average of best bid and best ask when both exist |
| Volume | Number of shares executed, not merely submitted |

The added fields in `src/market/data_recorder.py` preserve synchronized
pre-match quotes, post-match quotes, and the last real execution. Regression
tests are in `tests/test_price_mechanism_audit.py`.

## 7. Figure 6--7 research assets

### Versioned runs

Stable run IDs are under `data/runs/`:

- `fig6_above_baseline` and `fig6_below_baseline`;
- `fig6_above_prompt_adjusted` and `fig6_below_prompt_adjusted`;
- `prompt_probe_r{1,2,3}_{current,earliest_public,mandatory_two_sided}`.

The manifest records each run's role and every included file checksum. Exact
rendered prompts are included because prompt provenance is part of the research
question. See `data/README.md` for the inclusion policy.

### Offline analyses (free to run)

```bash
python scripts/analyze_fig6_fig7_canonical.py
python scripts/analyze_prompt_hierarchy_probe.py
python scripts/build_report_price_panels.py
```

These scripts read only `data/` and do not call an LLM. They regenerate the
research tables and figures under `docs/` on any team member's clone.

### Paid experiment runners

- `scripts/run_prompt_contrast.py`: repeats a full above/below scenario after
  changing only the market-maker no-short-selling wording.
- `scripts/run_prompt_hierarchy_probe.py`: runs a one-round, three-arm prompt
  hierarchy diagnostic.

Both write full new output to the ignored `logs/` directory. Before running
them, confirm the model, scenario, prompt hash, expected call count, and soft
budget. Do not treat `temperature=0` or a fixed seed as a guarantee of
identical provider output.

## 8. Reports and interpretation

The most useful research documents are:

- `docs/replication_status.md`: initial Figure 6--7 replication status;
- `docs/fig6_fig7_canonical_analysis.md`: price, order-flow, execution, and
  valuation audit;
- `docs/prompt_hierarchy_mechanism_report.md`: prompt hierarchy, order-size
  compliance, fill mechanics, and stochasticity;
- `docs/prompt_mechanism_findings.html`: presentation-ready synthesis;
- `docs/ai_herding_research_direction.md`: broader research design;
- `docs/q2_q3_persona_liquidity.md`: persona behaviour and market-maker
  liquidity metrics (Q2/Q3);
- `docs/sensitivity_protocol.md`: sensitivity-test design, gates, and budget.

Current evidence supports narrower mechanism statements than “AI agents cause
a market crash.” In the high-price runs, agents generated one-sided sell
pressure and lower quotes, while no transaction occurred. That is evidence of
correlated order flow and quote-driven recorded-price movement. It is not yet
evidence of transaction-driven price impact or systemic risk.

## 9. Safe team workflow

1. Sync `main` to inspect the unchanged upstream baseline.
2. Create or use a named personal branch for research changes.
3. Never commit `.env`, API keys, or the full `logs/` tree.
4. Save paid-run parameters, rendered prompts, model usage, and traces.
5. Add only the evidence required for a reported result to `data/`.
6. Regenerate offline outputs and run relevant tests before opening a pull
   request.
7. State whether a finding concerns model behavior, order validation, matching,
   price measurement, or a market-level outcome. Do not collapse these layers.

To rebuild the curated package from the designated local raw runs:

```bash
python scripts/prepare_curated_data.py
```

## 10. Short glossary

- **Agent valuation:** the value an agent reports in its structured response;
  it is not automatically an executable order price.
- **Accepted order:** an order that passes simulator checks and enters market
  processing; it may still remain unfilled.
- **Fill:** execution of some or all of an order against the opposite side.
- **Fundamental value:** the model-implied benchmark value of the asset; $28 in
  the Figure 6--7 scenarios.
- **Order imbalance:** asymmetry between buy and sell interest.
- **Prompt arm:** one prompt treatment in a controlled comparison.
- **Quote-driven movement:** a recorded-price change caused by resting bids or
  asks without a trade.
- **Transaction-driven movement:** a price change supported by an executed
  trade.

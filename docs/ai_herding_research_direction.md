# Initial AI Herding Research Direction

## Scope and terminology

This document interprets “AI Hiring” in the request as **AI Herding**, which is the project topic described in the meeting summary. The proposal is intentionally preliminary. It is meant for discussion and supervisor feedback after the paper and codebase have been understood; it is not yet a finalized experiment or implementation plan.

## 1. Proposed research question

> When trading agents become more similar in their model, prompt, or information, do their decisions become more correlated, and does that correlation create measurable effects on market stability?

The key distinction is between:

- **individual-level similarity:** agents choose the same action, order type, direction, or size;
- **market-level impact:** the similarity changes prices, volatility, liquidity, price impact, or the frequency of extreme market outcomes.

Correlated trading alone should not be described as systemic risk. The project should test whether correlation propagates through the market mechanism into materially different market outcomes.

## 2. Recommended first experiment

### Experiment A: prompt similarity under a common model

Hold the following constant:

- underlying LLM model;
- temperature and random-seed policy;
- initial price and fundamental value;
- dividend process and interest rate;
- number of agents and rounds;
- initial cash and shares;
- market rules and information access.

Vary only the system prompts:

| Condition | Agent prompts | Purpose |
|---|---|---|
| Heterogeneous prompt condition | Different strategy prompts, such as value, momentum, market maker, and contrarian | Baseline diversity |
| Similar prompt condition | Same or near-identical prompt across agents | Increased behavioral similarity |
| Paraphrase condition | Semantically equivalent prompt variants | Test sensitivity to wording rather than strategy |

The first comparison should use the same market scenario and multiple random seeds. The purpose is not to optimize returns but to estimate whether prompt homogenization changes decision correlation and market quality.

## 3. Follow-up experiments

After Experiment A is understood, vary one additional dimension at a time:

### Model similarity

- all agents use the same model;
- agents use a mixture of models;
- model composition changes while prompts remain fixed.

### Information similarity

- all agents receive the same market information;
- agents receive different information subsets or delayed information;
- agents receive the same information but have different visibility into fundamentals or order-book depth.

### Population composition

- 25%, 50%, 75%, and 100% AI agents;
- AI agents mixed with deterministic benchmark agents;
- different proportions of highly similar agents and heterogeneous agents.

These should be treated as separate experiments, not changed simultaneously in the first stage.

## 4. Outcome measures

### Agent-level correlation

Measure similarity by round and agent pair using:

- Buy/Sell/Hold agreement rate;
- pairwise action correlation;
- correlation in signed order direction;
- order-type agreement, market versus limit;
- correlation in normalized order size;
- similarity in price targets or valuations;
- synchronization of decisions after a common signal.

The analysis should report both raw agreement and agreement adjusted for the base rate of each action. For example, if almost every agent holds because the market is inactive, a high agreement rate may not represent meaningful herding.

### Market-level outcomes

Track:

- return volatility;
- absolute price change and maximum drawdown;
- deviation from fundamental value;
- trading volume and turnover;
- bid-ask spread;
- order-book depth and liquidity;
- price impact per unit of signed order flow;
- frequency and severity of price jumps;
- convergence speed in price-discovery scenarios;
- dispersion of agent wealth and positions.

### Suggested primary hypotheses

- **H1:** More similar prompts increase cross-agent decision correlation.
- **H2:** Higher decision correlation increases the concentration of signed order flow.
- **H3:** Concentrated order flow increases volatility or price impact under stressed or mispriced initial conditions.
- **H4:** Market makers and heterogeneous benchmark agents may dampen the market impact of correlated LLM behavior.

These are testable hypotheses, not conclusions.

## 5. Experimental controls

To make the results interpretable:

- use the same scenario parameters across treatment and control conditions;
- run several random seeds rather than relying on one trajectory;
- record model name, prompt version, temperature, seed, scenario, and information mode;
- separate prompt similarity from model similarity in the first experiment;
- include deterministic agents as a non-LLM benchmark where practical;
- distinguish decision correlation before execution from correlation in executed trades;
- report failed, invalid, or missing LLM decisions rather than silently dropping them;
- avoid claiming systemic risk unless market-level effects are statistically and economically meaningful.

## 6. Recommended staged plan

### Stage 1 — Baseline understanding

Select one paper scenario and document its parameters, expected outputs, and market lifecycle. Confirm which figure or result will be the baseline comparison.

### Stage 2 — Measurement prototype

Use existing logs to calculate simple action-agreement and signed-order-flow measures. Confirm that agent IDs, rounds, orders, prices, and prompt metadata are available.

### Stage 3 — Prompt-similarity experiment

Compare heterogeneous prompts with identical or paraphrased prompts while holding the model and market configuration fixed.

### Stage 4 — Market-impact analysis

Compare volatility, liquidity, price impact, price-fundamental deviation, and extreme-event frequency across the prompt conditions.

### Stage 5 — Supervisor-approved extension

Only after the first results are reviewed should the team vary models, information sets, AI population share, leverage, short selling, or social messaging.

## Appendix A — Questions to confirm with supervisors

### Baseline and paper scope

1. Is the paper version linked in the repository the definitive version for our replication?
2. Which scenario, figure, or table should be treated as the required baseline?
3. Is reproducing one representative result sufficient for Week Two, or is a broader reproduction expected?
4. If the repository has evolved beyond the paper, should we reproduce the historical paper configuration or use the current codebase?

### Experimental design

5. Should the first herding experiment vary prompt similarity, model similarity, or information similarity?
6. Should the first experiment use all LLM agents, or include deterministic agents as controls?
7. What level of prompt paraphrasing counts as “similar” while preserving the same strategy?
8. Should the initial experiment use one market scenario or compare normal and stressed scenarios?
9. How many random seeds or repeated runs are expected before drawing conclusions?

### Measurement and systemic risk

10. Which primary herding measure should be prioritized: action agreement, signed-order correlation, order-size correlation, or another measure?
11. Which market outcomes should define economically meaningful instability: volatility, liquidity loss, price impact, drawdown, or extreme price moves?
12. How should the team distinguish correlation caused by common market information from correlation caused by similar agents?
13. What evidence would be sufficient to describe an outcome as a systemic-risk concern rather than simply correlated trading?

### Practical constraints

14. Which models, API endpoints, temperature settings, and computational resources are approved?
15. What is the expected format and deadline for the progress report before each meeting?
16. If baseline results cannot be reproduced, should the team pause extension work or proceed with a documented limitation?
17. How should the team divide paper analysis, code analysis, experiment design, and future implementation work?


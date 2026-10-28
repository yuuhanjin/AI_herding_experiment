# Paper Summary

## Paper identification

**Title:** *Can Large Language Models Trade? Testing Financial Theories with LLM Agents in Market Simulations*  
**Author:** Alejandro Lopez-Lira  
**Date listed in the repository:** April 14, 2025  
**Sources:** [arXiv:2504.10789](https://arxiv.org/abs/2504.10789), [SSRN:5217340](https://ssrn.com/abstract=5217340), and the repository README.

## 1. Research question and motivation

The paper asks whether large language models can function as autonomous trading agents inside a controlled financial market. More specifically, it studies whether LLM agents can follow distinct trading instructions, process market information, place executable orders, and generate market-level outcomes that resemble those observed in real financial markets.

The motivation is broader than testing whether an LLM can make profitable trades. If many market participants use similar models or prompts, their responses to the same information may become correlated. Such correlation could affect price discovery, liquidity, volatility, and market stability. The paper therefore provides a simulation framework that can later be used to study correlated AI behavior and systemic risk.

## 2. Experimental environment

The authors build an agent-based stock-market simulation with a persistent order book and a continuous double-auction mechanism implemented in discrete trading rounds. The main market features are:

- market and limit orders;
- price-time priority and partial fills;
- market-to-market and market-to-order-book matching;
- cash and share constraints before execution;
- dividends and risk-free interest on cash;
- finite- and infinite-horizon markets;
- heterogeneous information, strategies, and endowments;
- detailed logging of orders, trades, prices, positions, and reasoning.

The baseline calibration uses an expected dividend of 1.40 and a risk-free interest rate of 5%, giving an infinite-horizon fundamental value of 28.00 through the dividend-discount relationship:

`fundamental value = expected dividend / interest rate = 1.40 / 0.05 = 28.00`.

The paper describes typical baseline runs as having approximately 8 agents and 15–20 rounds, with the exact configuration varying by scenario. GPT-4o is used as the decision-making model in the reported scenarios.

## 3. Agent design

Agent strategy is primarily encoded in a system prompt. The same underlying LLM can therefore be assigned different trading roles without changing the market mechanism. The paper discusses, among others:

- value investors, who compare price with fundamental value;
- momentum traders, who follow price trends and volume;
- market makers, who provide liquidity using bid and ask orders;
- contrarian traders, who trade against excessive movements;
- optimistic and pessimistic traders, who hold systematically different beliefs;
- speculators and retail-style traders;
- deterministic rule-based agents used as controls or benchmarks.

The user prompt supplies the current market state, including price, volume, order-book information, position, cash, dividend information, and available trading options. Agents return structured decisions containing valuation reasoning, valuation, price target, orders, order type, quantity, limit price when needed, and an explanation of the decision. Pydantic-style schema validation converts the LLM output into executable orders.

This separation between strategic instructions and current market information is important for the future AI Herding project: prompt similarity, model similarity, and information similarity can be varied independently.

## 4. Experimental design and main findings

### Strategy adherence

LLM agents generally follow the strategy specified in their prompts. Value investors tend to buy when prices are below their estimated fundamental value and sell when prices are above it. Momentum traders respond more strongly to price trends than to fundamental mispricing. Market makers tend to post bid and ask orders to provide liquidity.

The paper emphasizes that LLM agents are instruction-following systems rather than intrinsically profit-maximizing decision makers. They can react to market information while maintaining a prescribed strategy even when following that strategy is not profitable.

### Price discovery

The paper tests markets that begin above or below the fundamental value. In the infinite-horizon scenarios, the below-fundamental market tends to converge toward the 28.00 benchmark within the simulation horizon. The above-fundamental market shows more persistent overvaluation and does not fully converge downward during the reported period. This asymmetry suggests that the simulated agents correct undervaluation more effectively than overvaluation under the tested conditions.

### Market-level behavior

Interactions among heterogeneous agents generate market phenomena that resemble real-market behavior, including price discovery, bubbles, underreaction, and strategic liquidity provision. The outcome depends on the composition of the agent population, initial price, information available to agents, and the strategies encoded in prompts.

### Systematic decision analysis

The framework also varies the price-to-fundamental ratio while holding other conditions constant. This creates decision-response maps similar to partial-dependence analysis: researchers can observe how the probability of buying, selling, or holding, order size, order type, valuation, and price target change as market conditions vary.

## 5. Relevance to the AI Herding project

The paper is a baseline platform rather than a completed systemic-risk study. Its most relevant contribution to our project is the controlled separation of:

1. the model used to generate decisions;
2. the system prompt that defines the strategy;
3. the information shown in the user prompt;
4. the composition of the agent population;
5. the market mechanism that translates orders into prices and liquidity.

This makes it possible to ask a more focused follow-up question: when agents become more similar along one or more of these dimensions, do their decisions become more correlated, and do those correlations create measurable market effects?

## 6. Critical assessment and limitations

- The environment is a controlled simulation, not an empirical test using real trading activity.
- LLM behavior depends on the model version, temperature, API implementation, prompt wording, and structured-output behavior.
- Results may be sensitive to the random seed, order-submission sequence, initial endowments, initial price, and number of rounds.
- The baseline market is stylized: transaction costs, participant objectives, information access, and short-selling rules may differ from real markets depending on the scenario.
- “Correlated decisions” do not automatically demonstrate systemic risk. A systemic-risk claim requires showing that similarity changes market-level outcomes such as volatility, liquidity, price impact, or the probability of extreme events.
- The paper’s results should be reproduced under the exact repository version and configuration before being used as the baseline for extensions.

## 7. Key takeaways for the next meeting

1. The paper demonstrates a reusable LLM-agent market simulation, not a final answer about AI systemic risk.
2. Prompt-defined heterogeneity is central: different strategies can be created with the same underlying model.
3. The order book and matching engine matter because individual decision similarity only becomes economically meaningful when it affects executions and prices.
4. The most natural extension is a controlled similarity experiment with one changed dimension at a time.
5. Before extending the project, we should identify which paper scenario and which reported figure or table will serve as the baseline reproduction target.


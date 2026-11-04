# 真实 GPT 验证报告：零成交基线与受控交易链路测试

Xinyi Yang (xy2769) · 2026-11-04

## 第一阶段：保留的零成交基线结果

第一阶段真实 GPT 调用和订单提交链路通过，但该阶段没有成交，不能验证实际成交或价格收敛。原始零成交数据保持不变；后续独立 controlled execution test 见下文。

- Endpoint：OpenRouter；请求和返回模型：openai/gpt-4o-2024-11-20。
- 低估场景，初始价 $14，基本面约 $28，8 agents × 2 rounds。
- max_order_size=1000，order_size_mode=enforced，temperature=0，单并发，无自动重试，固定 dividend replay。
- 16/16 次实际 API 调用成功。每次最终请求都核对了 user prompt 中的明确上限以及 schema quantity.maximum=1000。
- 输入 tokens：22002；输出 tokens：3147。
- OpenRouter 每次响应 usage.cost 合计 **$0.082155**。这来自提供商返回费用，不是仓库静态价格表的估算；最终账单以 OpenRouter 为准。status.json 的 reserved_usd 是保守预留，不能当成实际花费。
- 20 笔 proposed orders 全部为 1000 股，全部为买单。最终 20 笔 active，0 trades，0 executed volume，未触发超限拒绝。
- recorded price：14 → 15.40 → 15.41，但两轮 execution price 均缺失，且没有 ask，midpoint 也缺失。这是 fallback quote 更新，不是成交带动的收敛。
- 2 次真实分红支付事件与固定路径一致，完整性检查通过。

## 本次额外发现：剩余数量减少不等于部分成交

5 笔 market buy 从原始 quantity=1000 变成 remaining_quantity=909，但 filled_quantity=0。代码 conversion_service.py 在提高报价后按已冻结现金重新计算可承受数量：floor(14000 / 15.40)=909。这不是成交 91 股，不能使用原始数量减剩余数量直接推算 filled quantity。

因此，逐单审计必须将成交量与价格转换/数量调整分开；order_data.csv 中 market 类型记录还可能带有转换后的价格，不宜把它当作未经修改的原始模型指令。原始模型输出保存在 api_calls.jsonl，订单生命周期保存在 order_lifecycle.json，真实成交以 trade records 核对。

## 可以和不可以声称的内容

可以说：该 OpenRouter/GPT-4o 调用路径在本次 16 次请求中接受了包含数量上限的结构化输出请求，返回订单均合规，生产订单入口和分红重放正常完成。

不可以说：GPT 在 prompt-only 条件下也必然服从；上限已改善流动性；enforced 模式导致了本次单边买入；已复现论文的收敛结论。本次 schema 和 prompt 同时施加限制，没有对照组，只有两轮。运行时超限拒绝已在此前合成测试验证，本次真实返回没有超限订单，因此未实际触发该分支。

本次还设置了 max_tokens=2048 作为费用控制，16 个返回的 finish_reason 均为 stop，没有输出截断；该设置应随配置一同披露。

## 第一阶段后的计划与当前状态

保留当前结果作为 live compatibility smoke test。下一批若要判断 prompt 的作用，应使用同一分红路径、相同模型/信息设置的小型 legacy vs prompt vs enforced 对照，并做同配置重复来衡量输出波动。正式 15 轮批次仍未启动。后续仅按授权增加了下文的两轮受控交易链路测试。缺少卖单导致本次没有交易，不应为获得成交而在本次结果中临时改变角色提示词。

## English report paragraph

I completed a two-round live compatibility pilot with eight agents using GPT-4o-2024-11-20 through OpenRouter. All 16 API calls succeeded, and the final prompts and output schemas included the 1,000-share per-order cap. All 20 proposed orders satisfied the cap. Provider-reported usage costs totaled $0.082155, and the two dividend payments matched the replayed path. However, all orders were buys and no trades occurred. The recorded price rose from $14 to $15.41 through fallback pricing, while transaction prices remained missing. This validates request compatibility and order admission, not convergence or a causal liquidity effect. Five orders also had their remaining quantity reduced during market-to-limit conversion without any fills, reinforcing the need to distinguish quantity adjustments from executions.

## Evidence

- api_calls.jsonl：实际发送的 messages、schema、返回结果、模型名称、token usage 和 provider cost；不包含 API key。
- order_lifecycle.json：逐单 ID、原始数量、剩余数量、成交量和状态历史。
- summary.json：机器可读统计。
- 原始运行目录：/Users/xinyi/Desktop/ColumbiaU/Q1/IEORE4742 Deep Learning for FE & OR/AI Herding/llm_trading_sim/logs/live_gpt_size_enforced_20261104/20261104_004020
- [OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat)：用于核对结构化输出接口；OpenRouter 兼容性结论来自本次实测。


---

## 第二阶段：Controlled Execution Test（新增，独立于原始复现）

### 目的与预先设定

检查真实 GPT 提交的订单能否与固定对手方成交，以及部分成交、现金转移、持仓转移和逐单记录是否一致。该试验是 implementation validation，不是论文原始设置的复现，也不是外生流动性效果的因果实验。

保留 8 个原有角色 agents（default、optimistic、market_maker、speculator 各 2 个），仍调用 OpenRouter 的 openai/gpt-4o-2024-11-20。新增一个不调用 LLM、不发布消息的固定流动性账户（agent 8），初始现金 $1,000,000、股票 10,000 股。该账户在 GPT 第一次决策前提交：

| 方向 | 数量 | 价格 |
|---|---:|---:|
| Buy limit | 500 | $12.50 |
| Sell limit | 500 | $13.00 |
| Sell limit | 250 | $13.01 |

两轮内不刷新、不根据 GPT 输出改价或补单。所有 seed orders 均不超过 1000 股。原始角色 system prompts 未改写，但订单簿、参与者数量、初始总资源及后续市场历史与零成交基线不同。

继续使用 initial price=$14、fundamental value≈$28、enforced cap=1000、temperature=0、单并发、两轮固定 dividend replay，以及每次最多 2048 output tokens。与第一阶段的分红路径哈希完全相同。新增 16 次真实调用，无自动重试；调用费用上限控制与第一阶段一致。

### 预演中发现的校验问题及报价调整

最初离线预演使用 bid=$13.50、asks=$14.00/$14.01。原有代码先按当前价格冻结市价买单现金，后续又按卖盘和缓冲计算所需承诺，导致合成市价买单被拒绝（例如已冻结 $14,000，但校验要求 $14,352.50）。

因此，在任何本次真实调用之前，把固定报价调整到上表的 $12.50/$13.00/$13.01，以便测试后续成交和记账链路。未修改生产撮合算法、资金校验或 GPT 角色 prompt。调整前后离线预演均保留，不能把这一工程测试报价选择当作预注册的经济研究处理。

### 真实结果

| 指标 | 第一阶段：原零成交运行 | 第二阶段：固定流动性测试 |
|---|---:|---:|
| GPT agents / 额外固定账户 | 8 / 0 | 8 / 1 |
| 轮数 | 2 | 2 |
| 成功真实 API 调用 | 16/16 | 16/16 |
| GPT proposed orders | 20 | 20 |
| GPT 订单数量 | 20 笔 × 1000 | 16 笔 × 1000；4 笔 × 500 |
| 超过 1000 股的 GPT 订单 | 0 | 0 |
| 成交笔数 | 0 | 2 |
| 成交总量（单边计数） | 0 | 750 股 |
| 第一轮 / 第二轮成交价 | 缺失 / 缺失 | $13.00 / $13.01 |
| Recorded price（两轮结束） | $15.40 / $15.41 | $13.00 / $13.01 |
| Provider-reported cost | $0.082155 | $0.084815 |

两阶段合计费用 **$0.166970**，不包含历史其他实验。费用来自 OpenRouter 响应的 usage.cost，最终账单以提供商为准。

具体成交：

1. 第 1 轮：GPT agent 7（speculator）买入固定账户 8 的 500 股，成交价 $13.00，交易金额 $6,500。原始买单 1000 股，成交 500、剩余 500；对应固定卖单全部成交。
2. 第 2 轮：GPT agent 0（default）买入固定账户 8 的 250 股，成交价 $13.01，交易金额 $3,252.50。原始买单 1000 股，成交 250、剩余 750；对应固定卖单全部成交。

**逐笔资金和持仓核对通过**：每笔买方现金减少与卖方现金增加对应，买方股票增加与卖方股票减少对应；本次费用率为零，成交涉及的总现金和总股数守恒。核对在每次 execute_trade 前后采样，避免把分红和未成交订单冻结金额误计为交易现金流。现金口径为可用现金加冻结现金，持仓口径为可用股数加冻结股数。

所有订单的 filled quantity 也逐单与 trade records 的 buyer_order_id / seller_order_id 汇总一致。两次分红支付与指定路径一致。

### 部分成交状态的解释

两笔 GPT 买单确实经过 partially_filled 状态，但挂回订单簿后最终状态为 active，分别保留 filled=500 / remaining=500，以及 filled=250 / remaining=750。因此：

- 最终 active 并不意味着从未成交；
- 必须结合 filled quantity、remaining quantity、trade IDs 和状态历史识别部分成交；
- 原零成交运行中 remaining 从 1000 降为 909 属于数量调整，仍不能解释为部分成交。

本轮没有修改原有状态命名或 CSV 语义，避免改变待验证的实现。

### 可以得出的结论与限制

可以说：在提供固定可成交对手方的受控环境中，真实 GPT 订单完成了部分成交，卖方订单完成了全部成交，且逐笔账户变化和订单成交量核对通过。此前零成交不是“撮合引擎永远不能成交”的证据。

不能说：固定流动性显著改善了市场效率、让价格向基本面收敛，或已拓展验证论文结论。成交价格由人为挂单明显约束，而且 $13/$13.01 比初始 $14 距离 $28 更远。两次运行的参与者数、资源、订单簿及 LLM 输出不同，也未保持严格的同序决策和未处理 agents 输出重放，因此不是可靠的因果 A/B 对照。此次只覆盖实际出现的交易路径，并非所有撮合、取消、卖空或杠杆分支的全面验证。

### 可加入组报告的英文段落

I retained the original zero-trade pilot and conducted a separate controlled execution test with the same eight GPT-4o agents and one deterministic liquidity account. Fixed bids and asks were seeded before model decisions and were not refreshed. All 16 additional API calls succeeded, and all 20 GPT orders respected the 1,000-share cap. Two trades executed against the fixed seller: 500 shares at $13.00 and 250 shares at $13.01. Both GPT buy orders were partially filled, while the corresponding seeded sell orders were fully filled. Per-trade cash and share changes and order-level fill totals reconciled successfully. The additional provider-reported cost was $0.084815. This validates the observed execution and accounting paths; it is not a replication of the paper or evidence that external liquidity improves convergence. The original zero-trade results remain unchanged.

### 口头汇报补充

我保留了之前的 zero-trade result，然后另外做了一个 controlled execution test。这个测试加了一个固定对手方，提前挂好买卖单，不根据 GPT 的决定调整。真实 GPT 这次产生了两笔成交，总共 750 股。两笔买单都是 partial fills，资金和持仓变化都核对通过。所以现在可以说我们验证了真实模型到交易执行的链路，但不能把它说成论文复现成功，因为流动性是人为加入的，而且成交价也是受到固定报价约束的。

### 新增证据位置

- 完整运行：/Users/xinyi/Desktop/ColumbiaU/Q1/IEORE4742 Deep Learning for FE & OR/AI Herding/llm_trading_sim/logs/controlled_execution_20261104_live/20261104_024550
- fixed_liquidity.json：固定账户 ID、seed order IDs、预定报价和不刷新规则。
- api_calls.jsonl：实际请求、schema、响应及提供商费用。
- trade_account_checks.json：每笔成交前后的账户快照和验证结果。
- order_lifecycle.json：逐单状态、成交量、剩余量及历史。
- summary.json：独立统计及一致性检查结果。
- 运行包装脚本保存在 controlled_execution_20261104/run_controlled_test.py；干预仅在该测试进程内安装，未修改项目生产撮合代码。

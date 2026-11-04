# 真实 GPT 小规模验证结果

Xinyi Yang (xy2769) · 2026-11-04

## 结论

真实 GPT 调用和订单提交链路通过；本次没有成交，因此没有验证真实 LLM 驱动的成交链路或价格收敛。没有进行第二批付费实验。

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

## 下一步

保留当前结果作为 live compatibility smoke test。下一批若要判断 prompt 的作用，应使用同一分红路径、相同模型/信息设置的小型 legacy vs prompt vs enforced 对照，并做同配置重复来衡量输出波动。正式 15 轮批次仍未启动。缺少卖单导致本次没有交易，不应为获得成交而在本次结果中临时改变角色提示词。

## English report paragraph

I completed a two-round live compatibility pilot with eight agents using GPT-4o-2024-11-20 through OpenRouter. All 16 API calls succeeded, and the final prompts and output schemas included the 1,000-share per-order cap. All 20 proposed orders satisfied the cap. Provider-reported usage costs totaled $0.082155, and the two dividend payments matched the replayed path. However, all orders were buys and no trades occurred. The recorded price rose from $14 to $15.41 through fallback pricing, while transaction prices remained missing. This validates request compatibility and order admission, not convergence or a causal liquidity effect. Five orders also had their remaining quantity reduced during market-to-limit conversion without any fills, reinforcing the need to distinguish quantity adjustments from executions.

## Evidence

- api_calls.jsonl：实际发送的 messages、schema、返回结果、模型名称、token usage 和 provider cost；不包含 API key。
- order_lifecycle.json：逐单 ID、原始数量、剩余数量、成交量和状态历史。
- summary.json：机器可读统计。
- 原始运行目录：/Users/xinyi/Desktop/ColumbiaU/Q1/IEORE4742 Deep Learning for FE & OR/AI Herding/llm_trading_sim/logs/live_gpt_size_enforced_20261104/20261104_004020
- [OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat)：用于核对结构化输出接口；OpenRouter 兼容性结论来自本次实测。

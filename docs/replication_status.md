# Figure 6–7 初阶段复现状态（当前代码，seed 42）

后续机制边界、提示词对照及 trace 见 [mechanism_boundary_validation.md](mechanism_boundary_validation.md)。其中还更正了一个重要口径：代码中的 `public_info['last_trade']['price']` 会被无成交改价覆盖，**不能**代替从 `trade_data.csv` 重建的最后真实成交价；原报告的成交笔数和成交价续接分析均以真实成交 CSV 为准。

## 结论与证据边界

本次完成了论文两组无限期价格发现情景各 15 轮的**当前代码计算复现**。`paper_price_discovery_above` 的记录价格保持在基本价值 $28 以上，与论文 Figure 6 左图的方向部分一致；但全程 **0 笔成交**，因此不能把价格下降解读为成交驱动的价格发现。`paper_price_discovery_below` 从 $14 升至 $15.35，只弥合了通往 $28 的初始差距的 **9.6%**，没有重现论文所称的 15 轮内明显收敛。两场景的 agent 估值中位数每轮均为 $28，也没有重现 Figure 7 所描述的动态调整。论文原文：[arXiv:2504.10789，§3.2.3，Figures 6–7](https://arxiv.org/html/2504.10789)。

这是**单个 seed、当前仓库版本**的结果，不是对论文原始代码的严格复跑，也不足以断言论文结论错误。运行前另做的两轮 smoke test 只确认了 pipeline，未纳入共享证据包；本报告仅使用下面两次完整运行作为 Figure 6–7 的比较对象。

| 比较对象 | 论文描述 | 本次观察 | 判定 |
| --- | --- | --- | --- |
| Figure 6 左：$56 起点 | 15 轮内仍显著高于 $28 | 末轮记录价 $46；但 15 轮均无成交，最后实际成交价不存在 | 部分一致；价格发现机制无法由该路径支持 |
| Figure 6 右：$14 起点 | 明显向 $28 收敛 | 末轮 $15.35，离 $28 仍有 45.2%；23 笔成交 | 不一致 |
| Figure 7 左：估值 | 多名 agent 的高估值持续 | 每轮中位数 $28；仅 2 名 Optimistic agent 固定报 $41.60 | 不一致于所述整体估值轨迹 |
| Figure 7 右：估值 | agent 估值逐渐向 $28 上调 | 每轮中位数从一开始就是 $28，未呈上调过程 | 不一致 |

论文没有提供可直接逐点比较的原始数值序列；以上是方向、终点和机制层面的比较，不是像素或逐点复刻。

## 运行配置与数据质量

代码固定在 commit `a09d51b48ff7ac02b127e0fdcf0cc530f9ead90d`（当时的工作分支后来更名为 `Yuhan`）。论文于 2025 年 4 月提交；当前仓库可见的最早提交在 2025 年 6 月，因此版本差异必须保留在解释中。运行沿用 [`paper_scenarios.py`](../src/scenarios/paper_scenarios.py) 的 15 轮、8 agent：Default、Optimistic、Market Maker、Speculator 各 2 名；Market Maker 的现金和持股为普通 agent 的 20 倍；禁止做空；`FUNDAMENTAL_INFO_MODE=process_only`；基本价值 $28；`RANDOM_SEED=42`、`LLM_SEED=42`、temperature 0、模型 `gpt-4o-2024-11-20`。仅改变输出目录标签，没有改模拟代码或场景参数。为限制失败重试，进程环境设 `LLM_MAX_RETRIES=2`；本次实际均无重试。

运行环境：Python 3.12.0、`openai` 2.45.0、Pydantic 2.12.5、NumPy 2.2.6、Matplotlib 3.11.1、WordCloud 1.9.6。仓库 `requirements.txt` 钉住的 WordCloud 为 1.9.4；本机安装 1.9.6 才解决导入问题。这一差异不改变交易逻辑，但复现环境不是完全锁定的历史环境。

| 人设提示词文件 | SHA-256 |
| --- | --- |
| `src/agents/prompts/default.md` | `41B765C51F095A314C7346297889F1321CBCDF0FE3E398BBF634445B92E0067A` |
| `src/agents/prompts/optimistic.md` | `29617958085C51803DC937CDE5E56821E52BB65D4142E776F35418CF3FA044DC` |
| `src/agents/prompts/market_maker.md` | `16AB5611B5EF04EFD8CD8BD32F3202590955A09BF2B041AD75F02468F8A7D1FE` |
| `src/agents/prompts/speculator.md` | `7DA9F42B72B71340067FC284671F5D996507C510BE1864C64F325828EB1F6F01` |

| 数据核验 | Above | Below |
| --- | ---: | ---: |
| 市场记录 | 15/15 轮 | 15/15 轮 |
| 成功模型调用 / 应有调用 | 120/120 | 120/120 |
| 失败调用 / 额外尝试 | 0 / 0 | 0 / 0 |
| 实际提示词记录 | 120 | 120 |
| 唯一 agent–轮估值记录 | 120 | 120 |
| 验证错误记录 | 0 | 0 |
| 成交笔数 / 总成交股数 | 0 / 0 | 23 / 13,999 |
| 模型输入 / 输出 tokens | 183,172 / 25,591 | 199,046 / 25,452 |
| 仓库估算 API 费用 | $0.713845 | $0.752137 |

两组共 240 次成功调用、382,218 输入 tokens、51,043 输出 tokens，**估算费用 $1.465982**，低于事先设定的 $5 软预算。这是仓库按用量计算的估算，不等同于 API 账户账单。`structured_decisions.csv` 以订单/决策明细记录，可能一名 agent 一轮占多行；估值统计按 `(round, agent_id)` 去重，不能把 151/190 个明细行误当作独立 agent 决策。共享的审计数据分别在 [Above](../data/runs/fig6_above_baseline/) 和 [Below](../data/runs/fig6_below_baseline/)；逐次模型费用见各自的 `data/llm_usage.csv`。

## Figure 6：价格、成交与报价口径

辅助判据“进入 $28 的 ±10% 区间”由本研究事先提出，**不是论文判据**。末轮 Above 的相对偏差为 `|46−28|/28 = 64.3%`，Below 为 `|15.35−28|/28 = 45.2%`，均未进入该区间。Below 的 $1.35 上涨只占初始 $14 缺口的 9.6%。

| 轮次 | Above 记录价 | Above 成交笔数/股数 | Below 记录价 | Below 成交笔数/股数 |
| ---: | ---: | ---: | ---: | ---: |
| 0（起点） | 56.00 | — | 14.00 | — |
| 1 | 50.40 | 0 / 0 | 14.50 | 1 / 1,000 |
| 2 | 50.40 | 0 / 0 | 14.75 | 0 / 0 |
| 3 | 45.36 | 0 / 0 | 15.00 | 3 / 1,998 |
| 4 | 45.36 | 0 / 0 | 15.00 | 0 / 0 |
| 5 | 45.36 | 0 / 0 | 15.00 | 0 / 0 |
| 6 | 45.36 | 0 / 0 | 15.00 | 0 / 0 |
| 7 | 45.36 | 0 / 0 | 15.00 | 1 / 2 |
| 8 | 45.36 | 0 / 0 | 15.10 | 2 / 2,000 |
| 9 | 45.36 | 0 / 0 | 15.15 | 1 / 1,000 |
| 10 | 46.00 | 0 / 0 | 15.20 | 3 / 1,999 |
| 11 | 46.00 | 0 / 0 | 15.25 | 5 / 1,999 |
| 12 | 46.00 | 0 / 0 | 15.25 | 2 / 1,000 |
| 13 | 46.00 | 0 / 0 | 15.25 | 1 / 2 |
| 14 | 46.00 | 0 / 0 | 15.30 | 0 / 0 |
| 15 | 46.00 | 0 / 0 | 15.35 | 4 / 2,999 |

Above 的记录价在无成交的第 1、3、10 轮分别变动 −$5.60、−$5.04、+$0.64；全部记录价格变动都发生于零成交轮。若采用“最后实际成交价，没有成交则延续起点”的口径，Above 的 15 轮序列恒为 $56。当前引擎在无成交时可使用订单簿报价估价，见 [`calculate_new_price`](../src/market/engine/services/trade_processing_service.py) 与 [`calculate_price_from_book`](../src/market/orders/order_book/order_book_queries.py)。代码检查还定位了一个**日志时间口径混合**：[`execute_round`](../src/base_sim.py) 在撮合前取得 `market_state`，撮合后将它传给 [`_record_market_data`](../src/market/data_recorder.py)；CSV 的 `price` 取撮合后的 `context.current_price`，而 `best_bid`、`best_ask`、`market_depth` 取撮合前的 `market_state`。因此不能用同一行报价直接重建同一行价格，也不能把这些报价称为该轮期末报价。这是当前实现的记录口径问题，不足以单独证明论文原始版本有相同问题。

Below 有 5 个零成交轮；其中第 2、14 轮记录价分别上涨 $0.25、$0.05，占全部绝对价格变动 $1.35 的 22.2%。采用最后成交价延续口径时，Below 末轮仍为 $15.35；记录的第 15 轮**撮合前**双边报价中间价约 $15.285，也远低于 $28，但不能将它与该轮**撮合后**成交价视为同步报价。Above 的市场记录中没有任何双边报价同时存在的轮次，因此其中间价不可计算；不能把缺失报价填作零或强行计算 spread。逐轮买卖报价、市场深度及成交量可核查 [Above market_data.csv](../data/runs/fig6_above_baseline/data/market_data.csv)、[Below market_data.csv](../data/runs/fig6_below_baseline/data/market_data.csv) 和两组 `trade_data.csv`；共享图见 [`canonical_price_audit.png`](figures/canonical_price_audit.png)。

## Figure 7：估值与外生路径

每轮 8 个 agent 的估值中位数在两场景中均为 $28，15 轮未变。Above：Default、Market Maker、Speculator 六名 agent 均始终报 $28；两名 Optimistic agent 始终报 $41.60。Below：前六名同样始终报 $28；两名 Optimistic agent 的报值落在 $40.00 或 $41.60，仍无逐轮向 $28 收敛的轨迹。估值是模型在结构化回答中的自报字段，不能直接当成经行为独立验证的信念。原始记录见两组的 `structured_decisions.csv`；共享图见 [`canonical_valuation_quote_gap.png`](figures/canonical_valuation_quote_gap.png)。

两场景虽都使用 seed 42，但实际股息支付在第 5、6、11、14、15 轮不同（第 2–15 轮共有 14 条支付记录）。因此不能把这对运行解释为外生股息路径完全配对的因果比较；先核查随机数流/事件顺序，再开展后续处理效应实验。原始记录见各自的 `data/dividend_data.csv`。模型 temperature 0 和固定 seed 也不保证不同日期的 API 输出完全一致。

## 下一阶段机制检验：完成情况与待办

- **M1（本轮已完成的离线初筛）：** 成立为重要的测量风险。Above 的价格变化 100% 发生在无成交轮，按实际成交价口径没有价格发现；Below 的部分变动也来自无成交轮，但更换为成交价口径后仍远未收敛。已定位 CSV 同行价格（撮合后）和报价（撮合前）的时间口径不一致；若要研究同步报价，下一步须从撮合后订单簿状态另行提取。不能断言论文原始版本存在相同问题。
- **M2（待审阅后运行）：** 在无限期设置下，以 $42/$14 等幅起点对照当前 $56/$14；其余参数和模型固定。先解决或显式控制股息路径不配对问题，再评价上下行幅度效应。
- **M3（待审阅后运行）：** 仅将两名 Optimistic 改为两名 Default agent，保留 8 人总数、20 倍做市商资金、禁做空和其余机制；比较订单方向、成交活跃度及价格路径。不得同时改变短卖或撮合规则。

**停止点：** 已完成约定的一对完整运行与 M1 离线初筛。多种子重复、M2/M3 及其他付费实验均未启动；应先审阅本报告并核实版本/随机路径差异，不应据这一次结果直接宣称论文“有漏洞”或 AI herding 导致系统性风险。

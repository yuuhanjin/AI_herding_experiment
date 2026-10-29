# 第二阶段：估值复核与可控分红

更新日期：2026-10-28。没有调用收费 API，没有覆盖旧实验。

## 1. Figure 7 分析

双击 `4_刷新审计网页.command` 即可重新分析旧运行。长期看板入口为 `audit/dashboard/index.html`。

新增输出：
- `figure7_findings.md`：可用于报告的结果与限制。
- `figure7_valuation_audit.png` / `.svg`：按运行绘制的个体估值轨迹。
- 每组 `_agent_rounds.csv`：一个 agent 每轮一行的信念与限价报价差距。
- 每组 `_limit_quotes.csv`：原始有效限价报价层面的数据。
- 每组 `_round_summary.csv`、`_role_summary.csv`：按轮和按角色的统计。

原 structured_decisions.csv 是按订单展开的；因此每组原始行数超过 120。估值按 (round, agent_id) 合并，不把同一人的多张订单重复当作多个信念。冲突记录、缺失/非正估值明确标记；市价单的参考价不算限价报价。报价差距先在每个 agent-round 内平均，再汇总，避免订单多的角色得到更多权重。

旧决策轮次为 0–14，展示为 1–15。与报价比较的参考价是初始价/上一轮 recorded_price，不一定是真实成交价。描述性距离不是价格锚定的因果证明，也不构成羊群效应检验。

## 2. 三种分红模式

- legacy（默认）：原共享随机数逻辑保留，用于历史对照。
- independent：分红和订单排序使用不同 random.Random 实例；分红 seed 与 order_seed 分开保存。
- replay：固定每个支付轮次的实际分红，使用事先生成的 JSON。验证模型、时长、支付频率、索引、重复/遗漏、数值范围，保存文件及内容哈希。

当前仅支持平稳单股票、不启用额外因子冲击的受控运行。不支持的场景在构建模拟之前报错。独立随机数不意味着跨实验订单排序严格一致，也不能保证远程模型确定性。

## 3. 支付轮次非常重要

路径使用引擎的零基支付轮次 payment_round_zero_based。当前无限期 15 轮、每轮支付的场景在轮次 0–14 支付，共 15 次。

旧 dividend_data.csv 是轮初观察到的上一轮支付，只有展示轮次 2–15 的 14 行。不能逐行直接作为 15 轮支付路径；最后一轮支付通常不在该旧文件中。

新增 `data/dividend_payment_events.csv` 直接在实际支付处记录，包含支付轮次、展示轮次、每股分红、模式和支付成功状态。`dividend_control_check.json` 检查支付轮次是否完整，以及 replay 实际值是否与路径一致。

## 4. 已生成的离线路径

`audit/paths/dividends_seed42_15rounds.json` 可用于高估与低估场景，也可用于 baseline / prompt 调整的严格分红匹配。它是新生成的受控路径，不冒充任何历史运行路径。

只生成路径（不调用 API）：

```sh
.venv/bin/python scripts/prepare_dividend_path.py --seed 7 --output audit/paths/dividends_seed7_15rounds.json
```

两轮 pilot 需要两轮路径，15 轮路径会被拒绝：

```sh
.venv/bin/python scripts/prepare_dividend_path.py --rounds 2 --seed 42 --output audit/paths/dividends_seed42_2rounds.json
```

以下命令会调用收费 API，本次没有执行：

```sh
.venv/bin/python replicate.py pilot --dividend-mode independent --dividend-seed 42 --order-seed 42
.venv/bin/python replicate.py above --dividend-mode replay --dividend-path audit/paths/dividends_seed42_15rounds.json
.venv/bin/python replicate.py below --dividend-mode replay --dividend-path audit/paths/dividends_seed42_15rounds.json
```

受控运行使用新的目录标签（例如 replication_above_replay），与旧 legacy 输出分开。完整 prompt 配对实验还需由实验设计负责人确定变化因素和重复次数。

## 5. 已执行的离线验证

- 72 项相关测试通过，包含真实 AgentRepository 的 15 轮支付到账核对，没有 LLM 调用。
- 订单数量变化不影响独立分红流。
- 固定路径没有消耗全局随机流；实际支付值和路径逐轮一致。
- 重复支付、缺失路径、非有限值、错误时长/模型/轮次、未完成支付均触发错误。
- 有限期最终轮不支付分红、非每轮支付频率均按原引擎规则测试。
- 单独的机制演示：seed42、每轮 8 vs 20 个模拟订单时，legacy 分红有 7 轮不同，independent 为 0。该演示不证明已有历史对照的差异恰好由同一路径造成。
- 六组旧结果每组 120 个 agent-round，无重复冲突或缺失计数问题。

尚未做真实 GPT 端到端验证。网页脚本做语法/模拟 DOM 测试；此前本地 file:// 浏览器预览被安全策略阻止，未声称完成浏览器视觉验收。

## 6. 文件与恢复

第二阶段修改前备份位于 `audit_backups/20261028_phase2`。第一阶段备份仍保留。

新增模块：`src/dividend_controls.py`、`src/valuation_audit.py`、`src/figure7_report.py`。
修改入口与支付服务：`replicate.py`、`src/run_base_sim.py`、`src/market/state/services/dividend_service.py`、`src/market/engine/services/order_processing_service.py`。
分析/网页：`scripts/audit_replication.py`、`scripts/audit_dashboard.html`。
离线工具：`scripts/prepare_dividend_path.py`、`scripts/verify_dividend_isolation.py`。

旧报告中“尚未实现分红路径重放”的描述属于 10 月 27 日状态；从 10 月 28 日起以本说明和长期看板为准。作者原图代码版本及原始数据仍未补齐。

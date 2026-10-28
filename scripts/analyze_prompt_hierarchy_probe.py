"""Summarize the three-repeat market-maker prompt hierarchy probe.

This script is offline: it reads existing trace and CSV files, makes no API
calls, and writes auditable tables and one presentation-ready figure.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
TABLE_DIR = ROOT / "docs" / "tables"
FIGURE_DIR = ROOT / "docs" / "figures"
TRACE_PATHS = [
    DATA_ROOT / "traces" / "prompt_hierarchy_repeat_1.json",
    DATA_ROOT / "traces" / "prompt_hierarchy_repeat_2.json",
    DATA_ROOT / "traces" / "prompt_hierarchy_repeat_3.json",
]
ARMS = ["current", "earliest_public", "mandatory_two_sided"]
ARM_LABELS = {
    "current": "Current",
    "earliest_public": "Earliest public",
    "mandatory_two_sided": "Mandatory two-sided",
}
COLORS = {
    "current": "#5B6573",
    "earliest_public": "#D99035",
    "mandatory_two_sided": "#2A9D8F",
}
RUN_IDS = {
    (repeat, arm): f"prompt_probe_r{repeat}_{arm}"
    for repeat in range(1, 4)
    for arm in ARMS
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size <= 2:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"No rows to write: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def prompt_hashes(path: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        payload = record["system_prompt"] + "\0" + record["user_prompt"]
        hashes[str(record["agent_id"])] = hashlib.sha256(payload.encode()).hexdigest()
    return hashes


def decision_signature(rows: list[dict[str, str]]) -> str:
    parts = []
    for row in sorted(
        rows,
        key=lambda item: (
            item.get("decision", ""),
            item.get("order_type", ""),
            item.get("quantity", ""),
            item.get("price_limit", ""),
        ),
    ):
        parts.append(
            ":".join(
                [
                    row.get("decision", ""),
                    row.get("order_type", ""),
                    row.get("quantity", ""),
                    row.get("price_limit", ""),
                    row.get("valuation", ""),
                ]
            )
        )
    return " | ".join(parts)


def main() -> None:
    run_rows: list[dict] = []
    fill_rows: list[dict] = []
    agent_observations: dict[str, list[dict]] = defaultdict(list)

    for repeat, trace_path in enumerate(TRACE_PATHS, start=1):
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        for arm in ARMS:
            arm_data = trace["arms"][arm]
            result = arm_data["result"]
            run_id = RUN_IDS[(repeat, arm)]
            run_dir = DATA_ROOT / "runs" / run_id
            decisions = read_csv(run_dir / "structured_decisions.csv")
            orders = read_csv(run_dir / "data" / "order_data.csv")
            trades = read_csv(run_dir / "data" / "trade_data.csv")
            hashes = prompt_hashes(run_dir / "data" / "rendered_prompts.jsonl")

            decisions_by_agent: dict[str, list[dict[str, str]]] = defaultdict(list)
            agent_type: dict[str, str] = {}
            for row in decisions:
                agent_id = row["agent_id"]
                decisions_by_agent[agent_id].append(row)
                agent_type[agent_id] = row["agent_type"]

            mm_ids = {
                agent_id
                for agent_id, label in agent_type.items()
                if "market maker" in label.lower()
            }
            mm_involved_trades = sum(
                row.get("buyer_id") in mm_ids or row.get("seller_id") in mm_ids
                for row in trades
            )
            mm_bid_trades = sum(row.get("buyer_id") in mm_ids for row in trades)
            max_quantity = max((int(float(row["quantity"])) for row in orders), default=0)
            buy_orders = [row for row in orders if row["decision"].lower() == "buy"]
            sell_orders = [row for row in orders if row["decision"].lower() == "sell"]
            buy_quantity = sum(int(float(row["quantity"])) for row in buy_orders)
            sell_quantity = sum(int(float(row["quantity"])) for row in sell_orders)
            trade_volume = sum(int(float(row["quantity"])) for row in trades)
            mm_order_quantity = sum(
                int(float(row["quantity"])) for row in orders if row["agent_id"] in mm_ids
            )
            mm_executed_leg_quantity = sum(
                int(float(row["quantity"]))
                * ((row.get("buyer_id") in mm_ids) + (row.get("seller_id") in mm_ids))
                for row in trades
            )

            # In these one-round probes every transaction is 1,000 shares, and
            # the corresponding submitted buy and sell orders are also 1,000
            # shares. The order-state logs contain no PARTIALLY_FILLED state, so
            # each trade consumes two complete order legs.
            order_state_text = (run_dir / "order_state.txt").read_text(
                encoding="utf-8", errors="replace"
            ).lower()
            partial_fill_logged = any(
                token in order_state_text
                for token in ("partially_filled", "partially filled")
            )
            if partial_fill_logged:
                raise ValueError(f"Unexpected partial fill in {run_dir}")
            if any(int(float(row["quantity"])) != 1000 for row in trades):
                raise ValueError(f"Unexpected transaction size in {run_dir}")

            fully_filled_order_legs = 2 * len(trades)
            unfilled_orders = len(orders) - fully_filled_order_legs
            accepted_quantity = buy_quantity + sell_quantity
            fill_rows.append(
                {
                    "repeat": repeat,
                    "arm": arm,
                    "arm_label": ARM_LABELS[arm],
                    "accepted_orders": len(orders),
                    "accepted_buy_orders": len(buy_orders),
                    "accepted_sell_orders": len(sell_orders),
                    "accepted_order_quantity": accepted_quantity,
                    "accepted_buy_quantity": buy_quantity,
                    "accepted_sell_quantity": sell_quantity,
                    "executed_trades": len(trades),
                    "transaction_volume": trade_volume,
                    "fully_filled_order_legs": fully_filled_order_legs,
                    "partially_filled_orders": 0,
                    "unfilled_orders": unfilled_orders,
                    "buy_side_fill_rate": trade_volume / buy_quantity if buy_quantity else "",
                    "sell_side_fill_rate": trade_volume / sell_quantity if sell_quantity else 0.0,
                    "all_order_leg_fill_rate": (
                        2 * trade_volume / accepted_quantity if accepted_quantity else 0.0
                    ),
                    "market_maker_accepted_quantity": mm_order_quantity,
                    "market_maker_executed_leg_quantity": mm_executed_leg_quantity,
                    "market_maker_order_leg_fill_rate": (
                        mm_executed_leg_quantity / mm_order_quantity if mm_order_quantity else ""
                    ),
                    "partial_fill_state_logged": False,
                    "run_directory": run_dir.relative_to(ROOT).as_posix(),
                }
            )

            run_rows.append(
                {
                    "repeat": repeat,
                    "arm": arm,
                    "arm_label": ARM_LABELS[arm],
                    "market_maker_agent_decisions": len(mm_ids),
                    "market_makers_quoting_both_sides": result[
                        "mm_agents_quoting_both_sides"
                    ],
                    "market_maker_buy_orders": result["mm_proposed_buys"],
                    "market_maker_sell_orders": result["mm_proposed_sells"],
                    "all_buy_orders": result["all_proposed_buys"],
                    "all_sell_orders": result["all_proposed_sells"],
                    "trades": result["trades"],
                    "trade_volume": result["trade_volume"],
                    "market_maker_involved_trades": mm_involved_trades,
                    "market_maker_bid_trades": mm_bid_trades,
                    "final_recorded_price": result["final_recorded_price"],
                    "last_trade_price": (
                        "" if result["last_trade_price"] is None else result["last_trade_price"]
                    ),
                    "maximum_accepted_order_quantity": max_quantity,
                    "configured_max_order_size": 1000,
                    "cost_usd": result["cost_usd"],
                    "run_directory": run_dir.relative_to(ROOT).as_posix(),
                    "prompt_sha256": arm_data["system_prompt_sha256"],
                }
            )

            for agent_id, rows in decisions_by_agent.items():
                agent_observations[agent_id].append(
                    {
                        "arm": arm,
                        "repeat": repeat,
                        "agent_type": agent_type[agent_id],
                        "prompt_hash": hashes[agent_id],
                        "signature": decision_signature(rows),
                        "sides": "/".join(
                            sorted(
                                {
                                    row["decision"]
                                    for row in rows
                                    if row.get("decision")
                                }
                            )
                        ),
                        "valuations": "/".join(
                            sorted(
                                {
                                    row["valuation"]
                                    for row in rows
                                    if row.get("valuation")
                                }
                            )
                        ),
                    }
                )

    aggregate_rows: list[dict] = []
    for arm in ARMS:
        rows = [row for row in run_rows if row["arm"] == arm]
        final_prices = sorted({float(row["final_recorded_price"]) for row in rows})
        aggregate_rows.append(
            {
                "arm": arm,
                "arm_label": ARM_LABELS[arm],
                "repeats": len(rows),
                "market_maker_agent_decisions": sum(
                    row["market_maker_agent_decisions"] for row in rows
                ),
                "market_makers_quoting_both_sides": sum(
                    row["market_makers_quoting_both_sides"] for row in rows
                ),
                "two_sided_compliance_rate": sum(
                    row["market_makers_quoting_both_sides"] for row in rows
                )
                / sum(row["market_maker_agent_decisions"] for row in rows),
                "market_maker_buy_orders": sum(row["market_maker_buy_orders"] for row in rows),
                "runs_with_any_trade": sum(row["trades"] > 0 for row in rows),
                "total_trades": sum(row["trades"] for row in rows),
                "total_trade_volume": sum(row["trade_volume"] for row in rows),
                "market_maker_involved_trades": sum(
                    row["market_maker_involved_trades"] for row in rows
                ),
                "market_maker_bid_trades": sum(row["market_maker_bid_trades"] for row in rows),
                "maximum_accepted_order_quantity": max(
                    row["maximum_accepted_order_quantity"] for row in rows
                ),
                "configured_max_order_size": 1000,
                "distinct_final_recorded_prices": "/".join(
                    f"{price:.2f}" for price in final_prices
                ),
                "cost_usd": sum(float(row["cost_usd"]) for row in rows),
            }
        )

    fill_aggregate_rows: list[dict] = []
    for arm in ARMS:
        rows = [row for row in fill_rows if row["arm"] == arm]
        accepted_quantity = sum(row["accepted_order_quantity"] for row in rows)
        buy_quantity = sum(row["accepted_buy_quantity"] for row in rows)
        sell_quantity = sum(row["accepted_sell_quantity"] for row in rows)
        transaction_volume = sum(row["transaction_volume"] for row in rows)
        mm_quantity = sum(row["market_maker_accepted_quantity"] for row in rows)
        mm_executed = sum(row["market_maker_executed_leg_quantity"] for row in rows)
        fill_aggregate_rows.append(
            {
                "arm": arm,
                "arm_label": ARM_LABELS[arm],
                "repeats": len(rows),
                "accepted_orders": sum(row["accepted_orders"] for row in rows),
                "accepted_order_quantity": accepted_quantity,
                "accepted_buy_quantity": buy_quantity,
                "accepted_sell_quantity": sell_quantity,
                "executed_trades": sum(row["executed_trades"] for row in rows),
                "transaction_volume": transaction_volume,
                "fully_filled_order_legs": sum(
                    row["fully_filled_order_legs"] for row in rows
                ),
                "partially_filled_orders": 0,
                "unfilled_orders": sum(row["unfilled_orders"] for row in rows),
                "buy_side_fill_rate": transaction_volume / buy_quantity if buy_quantity else "",
                "sell_side_fill_rate": transaction_volume / sell_quantity if sell_quantity else 0.0,
                "all_order_leg_fill_rate": (
                    2 * transaction_volume / accepted_quantity if accepted_quantity else 0.0
                ),
                "market_maker_accepted_quantity": mm_quantity,
                "market_maker_executed_leg_quantity": mm_executed,
                "market_maker_order_leg_fill_rate": (
                    mm_executed / mm_quantity if mm_quantity else ""
                ),
            }
        )

    stability_rows: list[dict] = []
    for agent_id in sorted(agent_observations, key=int):
        observations = agent_observations[agent_id]
        prompt_hash_set = {row["prompt_hash"] for row in observations}
        signature_set = {row["signature"] for row in observations}
        sides = sorted({side for row in observations for side in row["sides"].split("/")})
        valuations = sorted(
            {value for row in observations for value in row["valuations"].split("/")},
            key=lambda value: float(value),
        )
        stability_rows.append(
            {
                "agent_id": agent_id,
                "agent_type": observations[0]["agent_type"],
                "observations": len(observations),
                "unique_exact_rendered_prompts": len(prompt_hash_set),
                "unique_structured_decisions": len(signature_set),
                "sides_observed": "/".join(filter(None, sides)),
                "valuations_observed": "/".join(filter(None, valuations)),
                "prompt_sha256": (
                    next(iter(prompt_hash_set)) if len(prompt_hash_set) == 1 else "multiple"
                ),
            }
        )

    write_csv(TABLE_DIR / "prompt_hierarchy_probe_runs.csv", run_rows)
    write_csv(TABLE_DIR / "prompt_hierarchy_probe_aggregate.csv", aggregate_rows)
    write_csv(TABLE_DIR / "prompt_hierarchy_agent_stability.csv", stability_rows)
    write_csv(TABLE_DIR / "prompt_hierarchy_fill_audit.csv", fill_rows)
    write_csv(TABLE_DIR / "prompt_hierarchy_fill_aggregate.csv", fill_aggregate_rows)

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.2))
    x = np.arange(len(ARMS))
    labels = [ARM_LABELS[arm] for arm in ARMS]
    colors = [COLORS[arm] for arm in ARMS]

    compliance = [
        next(row for row in aggregate_rows if row["arm"] == arm)[
            "market_makers_quoting_both_sides"
        ]
        for arm in ARMS
    ]
    axes[0].bar(x, compliance, color=colors)
    axes[0].axhline(6, color="#333333", linestyle="--", linewidth=1)
    axes[0].set_xticks(x, labels, rotation=18, ha="right")
    axes[0].set_ylim(0, 6.6)
    axes[0].set_ylabel("Market-maker decisions (out of 6)")
    axes[0].set_title("A. Two-sided role compliance")
    for index, value in enumerate(compliance):
        axes[0].text(index, value + 0.15, f"{value}/6", ha="center", fontsize=9)

    width = 0.23
    for repeat in range(1, 4):
        values = [
            next(
                row
                for row in run_rows
                if row["arm"] == arm and row["repeat"] == repeat
            )["trades"]
            for arm in ARMS
        ]
        axes[1].bar(
            x + (repeat - 2) * width,
            values,
            width,
            label=f"Repeat {repeat}",
            alpha=0.9,
        )
    axes[1].set_xticks(x, labels, rotation=18, ha="right")
    axes[1].set_ylabel("Executed trades")
    axes[1].set_title("B. Executed trades by repeat\n(missing bar = zero trades)")
    axes[1].legend(frameon=False, fontsize=8)

    max_quantities = [
        next(row for row in aggregate_rows if row["arm"] == arm)[
            "maximum_accepted_order_quantity"
        ]
        for arm in ARMS
    ]
    axes[2].bar(x, max_quantities, color=colors)
    axes[2].axhline(1000, color="#B42318", linestyle="--", linewidth=1.4, label="Configured cap")
    axes[2].set_yscale("log")
    axes[2].set_xticks(x, labels, rotation=18, ha="right")
    axes[2].set_ylabel("Maximum accepted quantity (log scale)")
    axes[2].set_title("C. Accepted size vs configured maximum")
    axes[2].legend(frameon=False, fontsize=8)
    for index, value in enumerate(max_quantities):
        axes[2].text(index, value * 1.12, f"{value:,}", ha="center", fontsize=9)

    fig.suptitle("$56 one-round market-maker prompt hierarchy probe (three repeats)", y=1.03)
    fig.tight_layout()
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    figure_path = FIGURE_DIR / "prompt_hierarchy_probe.png"
    fig.savefig(figure_path, dpi=220, bbox_inches="tight")
    plt.close(fig)

    total_probe_cost = sum(float(row["cost_usd"]) for row in run_rows)
    print(f"Wrote {len(run_rows)} run rows and {len(aggregate_rows)} aggregate rows")
    print(f"Prompt-probe cost: ${total_probe_cost:.6f}")
    print(f"Figure: {figure_path}")


if __name__ == "__main__":
    main()

"""Build an auditable Figure 6--7 mechanism analysis from existing logs.

This script does not call an LLM or rerun the market. It separates model
proposals, accepted orders, executed trades, synchronized quote measures, and
the simulator's recorded price for the four runs used in the progress report.
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "runs"
FIGURE_DIR = ROOT / "docs" / "figures"
TABLE_DIR = ROOT / "docs" / "tables"

RUNS = {
    "56 baseline": DATA_ROOT / "fig6_above_baseline",
    "56 prompt adjusted": DATA_ROOT / "fig6_above_prompt_adjusted",
    "14 baseline": DATA_ROOT / "fig6_below_baseline",
    "14 prompt adjusted": DATA_ROOT / "fig6_below_prompt_adjusted",
}

COLORS = {
    "56 baseline": "#264653",
    "56 prompt adjusted": "#2a9d8f",
    "14 baseline": "#e76f51",
    "14 prompt adjusted": "#f4a261",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size <= 2:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def as_int(value: str | None) -> int:
    if value is None or value == "":
        return 0
    return int(float(value))


def fmt_number(value: float | int | None, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "NA"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def count_order_validation_failures(path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not path.exists():
        return counts
    pattern = re.compile(r"failed validation: (.+)$", re.IGNORECASE)
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.search(line)
        if not match:
            continue
        reason = match.group(1)
        if reason.startswith("Insufficient lendable shares"):
            counts["insufficient shares / no borrowing"] += 1
        elif reason.startswith("Insufficient cash"):
            counts["insufficient cash"] += 1
        else:
            counts[reason] += 1
    return counts


def load_seen_prices(path: Path) -> dict[tuple[int, str], float]:
    """Read the last price shown to each agent from the exact rendered prompt."""
    seen: dict[tuple[int, str], float] = {}
    if not path.exists():
        return seen
    pattern = re.compile(r"- Last Price: \$([0-9]+(?:\.[0-9]+)?)")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        match = pattern.search(record.get("user_prompt", ""))
        if match:
            # Prompt/decision rounds are 0--14; market rounds are 1--15.
            seen[(as_int(str(record.get("round"))) + 1, str(record.get("agent_id")))] = float(
                match.group(1)
            )
    return seen


def load_run(name: str, run_dir: Path) -> dict:
    parameters = json.loads((run_dir / "parameters.json").read_text(encoding="utf-8"))
    initial_price = float(parameters["INITIAL_PRICE"])
    fundamental = float(parameters["FUNDAMENTAL_PRICE"])

    market_rows = read_csv(run_dir / "data" / "market_data.csv")
    order_rows = read_csv(run_dir / "data" / "order_data.csv")
    trade_rows = read_csv(run_dir / "data" / "trade_data.csv")
    decision_rows = read_csv(run_dir / "structured_decisions.csv")
    validation_csv_rows = read_csv(run_dir / "validation_errors.csv")
    seen_prices = load_seen_prices(run_dir / "data" / "rendered_prompts.jsonl")

    # Structured decisions are logged as rounds 0--14, while market, orders,
    # and trades use rounds 1--15. Normalize decisions to market round numbers.
    for row in decision_rows:
        row["market_round"] = str(as_int(row["round"]) + 1)

    decision_by_agent_round: dict[tuple[int, str], dict[str, str]] = {}
    for row in decision_rows:
        key = (as_int(row["market_round"]), row["agent_id"])
        decision_by_agent_round.setdefault(key, row)

    proposed = [
        row for row in decision_rows if row["decision"].strip().lower() in {"buy", "sell"}
    ]
    holds = {
        (as_int(row["market_round"]), row["agent_id"])
        for row in decision_rows
        if row["decision"].strip().lower() == "hold"
    }

    directions_by_agent_round: dict[tuple[int, str], set[str]] = defaultdict(set)
    type_by_agent_round: dict[tuple[int, str], str] = {}
    for row in decision_rows:
        key = (as_int(row["market_round"]), row["agent_id"])
        direction = row["decision"].strip().lower()
        if direction in {"buy", "sell"}:
            directions_by_agent_round[key].add(direction)
        type_by_agent_round[key] = row["agent_type"]

    agent_round_categories: Counter[str] = Counter()
    agent_type_categories: dict[str, Counter[str]] = defaultdict(Counter)
    for key in decision_by_agent_round:
        directions = directions_by_agent_round.get(key, set())
        if directions == {"buy"}:
            category = "buy only"
        elif directions == {"sell"}:
            category = "sell only"
        elif directions == {"buy", "sell"}:
            category = "both sides"
        else:
            category = "hold / no order"
        agent_round_categories[category] += 1
        agent_type_categories[type_by_agent_round[key]][category] += 1

    trades_by_round: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in trade_rows:
        trades_by_round[as_int(row["round"])].append(row)

    proposed_by_round_side: dict[tuple[int, str], int] = Counter()
    accepted_by_round_side: dict[tuple[int, str], int] = Counter()
    accepted_qty_by_round_side: dict[tuple[int, str], int] = Counter()
    for row in proposed:
        proposed_by_round_side[(as_int(row["market_round"]), row["decision"].lower())] += 1
    for row in order_rows:
        side = row["decision"].strip().lower()
        accepted_by_round_side[(as_int(row["round"]), side)] += 1
        accepted_qty_by_round_side[(as_int(row["round"]), side)] += as_int(row["quantity"])

    round_rows: list[dict[str, object]] = []
    previous_recorded = initial_price
    latest_trade: float | None = None
    for market in market_rows:
        round_number = as_int(market["round"])
        recorded = float(market["price"])
        round_trades = trades_by_round.get(round_number, [])
        trade_count = len(round_trades)
        trade_volume = sum(as_int(row["quantity"]) for row in round_trades)
        last_trade_this_round = (
            float(round_trades[-1]["price"]) if round_trades else None
        )
        if last_trade_this_round is not None:
            latest_trade = last_trade_this_round
        delta = recorded - previous_recorded
        if trade_count:
            source = "transaction"
        elif abs(delta) > 1e-12:
            source = "quote fallback"
        else:
            source = "no recorded change"

        post_midpoint = as_float(market.get("post_match_midpoint"))
        round_rows.append(
            {
                "run": name,
                "round": round_number,
                "recorded_price": recorded,
                "recorded_price_change": delta,
                "recorded_price_source": source,
                "last_trade_this_round": last_trade_this_round,
                "last_executed_trade_to_date": latest_trade,
                "post_match_midpoint": post_midpoint,
                "trade_count": trade_count,
                "trade_volume": trade_volume,
                "proposed_buy_orders": proposed_by_round_side[(round_number, "buy")],
                "proposed_sell_orders": proposed_by_round_side[(round_number, "sell")],
                "accepted_buy_orders": accepted_by_round_side[(round_number, "buy")],
                "accepted_sell_orders": accepted_by_round_side[(round_number, "sell")],
                "accepted_buy_quantity": accepted_qty_by_round_side[(round_number, "buy")],
                "accepted_sell_quantity": accepted_qty_by_round_side[(round_number, "sell")],
                "recorded_PE": abs(recorded - fundamental) / fundamental,
                "transaction_PE_this_round": (
                    abs(last_trade_this_round - fundamental) / fundamental
                    if last_trade_this_round is not None
                    else None
                ),
            }
        )
        previous_recorded = recorded

    valuations_by_round: dict[int, list[float]] = defaultdict(list)
    for (round_number, _agent_id), row in decision_by_agent_round.items():
        value = as_float(row.get("valuation"))
        if value is not None:
            valuations_by_round[round_number].append(value)

    accepted_limit_quotes: dict[tuple[int, str], list[float]] = defaultdict(list)
    accepted_limit_quote_to_valuation: dict[str, list[float]] = defaultdict(list)
    accepted_limit_quote_to_seen_price: dict[str, list[float]] = defaultdict(list)
    accepted_limit_abs_gap_from_seen_price: dict[str, list[float]] = defaultdict(list)
    for row in order_rows:
        if row["order_type"].strip().lower() != "limit":
            continue
        round_number = as_int(row["round"])
        side = row["decision"].strip().lower()
        price = as_float(row.get("price_limit"))
        if price is None:
            continue
        accepted_limit_quotes[(round_number, side)].append(price)
        decision = decision_by_agent_round.get((round_number, row["agent_id"]))
        valuation = as_float(decision.get("valuation")) if decision else None
        if valuation and valuation != 0:
            accepted_limit_quote_to_valuation[side].append(price / valuation)
        seen_price = seen_prices.get((round_number, row["agent_id"]))
        if seen_price and seen_price != 0:
            accepted_limit_quote_to_seen_price[side].append(price / seen_price)
            accepted_limit_abs_gap_from_seen_price[side].append(
                abs(price - seen_price) / seen_price
            )

    for row in round_rows:
        round_number = int(row["round"])
        values = valuations_by_round.get(round_number, [])
        buys = accepted_limit_quotes.get((round_number, "buy"), [])
        sells = accepted_limit_quotes.get((round_number, "sell"), [])
        row["median_reported_valuation"] = median(values) if values else None
        row["median_accepted_limit_buy"] = median(buys) if buys else None
        row["median_accepted_limit_sell"] = median(sells) if sells else None

    failures = count_order_validation_failures(run_dir / "order_state.txt")
    final_recorded = float(round_rows[-1]["recorded_price"])
    last_executed = None
    if trade_rows:
        last_executed = float(trade_rows[-1]["price"])

    abs_movement = sum(abs(float(row["recorded_price_change"])) for row in round_rows)
    quote_abs_movement = sum(
        abs(float(row["recorded_price_change"]))
        for row in round_rows
        if row["recorded_price_source"] == "quote fallback"
    )
    initial_gap = abs(initial_price - fundamental)
    trade_seller_volume: Counter[str] = Counter()
    trade_buyer_volume: Counter[str] = Counter()
    for row in trade_rows:
        trade_seller_volume[row["seller_id"]] += as_int(row["quantity"])
        trade_buyer_volume[row["buyer_id"]] += as_int(row["quantity"])
    total_trade_volume = sum(trade_seller_volume.values())
    top_seller_id = trade_seller_volume.most_common(1)[0][0] if trade_seller_volume else None
    agent_type_by_id = {
        agent_id: row["agent_type"]
        for (_round, agent_id), row in decision_by_agent_round.items()
    }
    market_maker_counts = agent_type_categories.get("Market Maker", Counter())
    summary = {
        "run": name,
        "initial_price": initial_price,
        "final_recorded_price": final_recorded,
        "last_executed_trade_price": last_executed,
        "agent_decisions": len(decision_by_agent_round),
        "proposed_buy_orders": sum(
            1 for row in proposed if row["decision"].strip().lower() == "buy"
        ),
        "proposed_sell_orders": sum(
            1 for row in proposed if row["decision"].strip().lower() == "sell"
        ),
        "hold_decisions": len(holds),
        "agent_round_buy_only": agent_round_categories["buy only"],
        "agent_round_sell_only": agent_round_categories["sell only"],
        "agent_round_both_sides": agent_round_categories["both sides"],
        "agent_round_hold_or_no_order": agent_round_categories["hold / no order"],
        "accepted_buy_orders": sum(
            1 for row in order_rows if row["decision"].strip().lower() == "buy"
        ),
        "accepted_sell_orders": sum(
            1 for row in order_rows if row["decision"].strip().lower() == "sell"
        ),
        "order_validation_failures": sum(failures.values()),
        "failure_reasons": "; ".join(f"{key}: {value}" for key, value in failures.items()) or "none",
        "validation_errors_csv_rows": len(validation_csv_rows),
        "trades": len(trade_rows),
        "trade_volume": sum(as_int(row["quantity"]) for row in trade_rows),
        "zero_trade_rounds": sum(1 for row in round_rows if row["trade_count"] == 0),
        "quote_change_rounds": sum(
            1 for row in round_rows if row["recorded_price_source"] == "quote fallback"
        ),
        "quote_share_abs_recorded_movement": (
            quote_abs_movement / abs_movement if abs_movement else 0.0
        ),
        "initial_recorded_PE": abs(initial_price - fundamental) / fundamental,
        "final_recorded_PE": abs(final_recorded - fundamental) / fundamental,
        "recorded_gap_closed": (
            (initial_gap - abs(final_recorded - fundamental)) / initial_gap
            if initial_gap
            else None
        ),
        "final_transaction_PE": (
            abs(last_executed - fundamental) / fundamental
            if last_executed is not None
            else None
        ),
        "median_limit_buy_price_to_valuation": (
            median(accepted_limit_quote_to_valuation["buy"])
            if accepted_limit_quote_to_valuation["buy"]
            else None
        ),
        "median_limit_sell_price_to_valuation": (
            median(accepted_limit_quote_to_valuation["sell"])
            if accepted_limit_quote_to_valuation["sell"]
            else None
        ),
        "median_limit_buy_price_to_seen_price": (
            median(accepted_limit_quote_to_seen_price["buy"])
            if accepted_limit_quote_to_seen_price["buy"]
            else None
        ),
        "median_limit_sell_price_to_seen_price": (
            median(accepted_limit_quote_to_seen_price["sell"])
            if accepted_limit_quote_to_seen_price["sell"]
            else None
        ),
        "median_limit_buy_abs_pct_from_seen_price": (
            median(accepted_limit_abs_gap_from_seen_price["buy"])
            if accepted_limit_abs_gap_from_seen_price["buy"]
            else None
        ),
        "median_limit_sell_abs_pct_from_seen_price": (
            median(accepted_limit_abs_gap_from_seen_price["sell"])
            if accepted_limit_abs_gap_from_seen_price["sell"]
            else None
        ),
        "market_maker_both_sides_agent_rounds": market_maker_counts["both sides"],
        "market_maker_total_agent_rounds": sum(market_maker_counts.values()),
        "unique_trade_sellers": len(trade_seller_volume),
        "top_trade_seller_id": top_seller_id,
        "top_trade_seller_type": agent_type_by_id.get(top_seller_id, "NA") if top_seller_id else "NA",
        "top_trade_seller_volume_share": (
            trade_seller_volume[top_seller_id] / total_trade_volume
            if top_seller_id and total_trade_volume
            else None
        ),
    }
    return {
        "name": name,
        "initial_price": initial_price,
        "fundamental": fundamental,
        "rounds": round_rows,
        "summary": summary,
        "agent_type_categories": agent_type_categories,
        "trade_seller_volume": trade_seller_volume,
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def style_axis(ax: plt.Axes) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#dddddd", linewidth=0.7, alpha=0.8)
    ax.set_axisbelow(True)


def plot_price_audit(analyses: list[dict]) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5), sharex=True)
    for ax, analysis in zip(axes.flat, analyses):
        rows = analysis["rounds"]
        rounds = [int(row["round"]) for row in rows]
        recorded = [float(row["recorded_price"]) for row in rows]
        color = COLORS[analysis["name"]]
        ax.plot([0] + rounds, [analysis["initial_price"]] + recorded, color=color,
                linewidth=2.1, marker="o", markersize=3.5, label="Recorded price")
        trade_x = [int(row["round"]) for row in rows if row["last_trade_this_round"] is not None]
        trade_y = [float(row["last_trade_this_round"]) for row in rows if row["last_trade_this_round"] is not None]
        if trade_x:
            ax.scatter(trade_x, trade_y, color="#111111", marker="x", s=38,
                       linewidth=1.4, label="Last executed trade in round", zorder=4)
        quote_x = [int(row["round"]) for row in rows if row["recorded_price_source"] == "quote fallback"]
        quote_y = [float(row["recorded_price"]) for row in rows if row["recorded_price_source"] == "quote fallback"]
        if quote_x:
            ax.scatter(quote_x, quote_y, facecolors="none", edgecolors="#d62828",
                       s=80, linewidth=1.5, label="Changed with zero trades", zorder=5)
        ax.axhline(analysis["fundamental"], color="#588157", linestyle="--",
                   linewidth=1.5, label="Fundamental ($28)")
        if not trade_x:
            ax.text(0.98, 0.06, "No executed trades", transform=ax.transAxes,
                    ha="right", va="bottom", fontsize=9,
                    bbox={"boxstyle": "round,pad=0.3", "facecolor": "#fff3cd", "edgecolor": "#d6b656"})
        ax.set_title(analysis["name"], loc="left", fontweight="bold")
        ax.set_ylabel("Price ($)")
        style_axis(ax)
    for ax in axes[-1, :]:
        ax.set_xlabel("Trading round")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    # Include trade marker from a lower-price panel when the first panel has none.
    if "Last executed trade in round" not in labels:
        h2, l2 = axes[1, 0].get_legend_handles_labels()
        for handle, label in zip(h2, l2):
            if label not in labels:
                handles.append(handle)
                labels.append(label)
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False,
               bbox_to_anchor=(0.5, -0.01))
    fig.suptitle("Recorded prices versus executed trades", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0.055, 1, 0.95))
    fig.savefig(FIGURE_DIR / "canonical_price_audit.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_order_funnel(analyses: list[dict]) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.8), sharex=True)
    for ax, analysis in zip(axes.flat, analyses):
        rows = analysis["rounds"]
        rounds = [int(row["round"]) for row in rows]
        accepted_buy = [int(row["accepted_buy_orders"]) for row in rows]
        accepted_sell = [-int(row["accepted_sell_orders"]) for row in rows]
        proposed_buy = [int(row["proposed_buy_orders"]) for row in rows]
        proposed_sell = [-int(row["proposed_sell_orders"]) for row in rows]
        ax.bar(rounds, accepted_buy, color="#2a9d8f", alpha=0.8, label="Accepted buys")
        ax.bar(rounds, accepted_sell, color="#e76f51", alpha=0.8, label="Accepted sells")
        ax.plot(rounds, proposed_buy, color="#006d77", linewidth=1.4,
                marker="o", markersize=2.8, label="Proposed buys")
        ax.plot(rounds, proposed_sell, color="#9d0208", linewidth=1.4,
                marker="o", markersize=2.8, label="Proposed sells")
        ax.axhline(0, color="#333333", linewidth=0.8)
        ax.set_title(analysis["name"], loc="left", fontweight="bold")
        ax.set_ylabel("Orders (buy + / sell -)")
        style_axis(ax)
    for ax in axes[-1, :]:
        ax.set_xlabel("Trading round")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False,
               bbox_to_anchor=(0.5, -0.01))
    fig.suptitle("Proposed and accepted order flow", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0.055, 1, 0.95))
    fig.savefig(FIGURE_DIR / "canonical_order_flow.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_valuation_quote_gap(analyses: list[dict]) -> None:
    low_analyses = [analysis for analysis in analyses if analysis["initial_price"] == 14]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    for ax, analysis in zip(axes, low_analyses):
        rows = analysis["rounds"]
        rounds = [int(row["round"]) for row in rows]
        recorded = [float(row["recorded_price"]) for row in rows]
        valuations = [as_float(row["median_reported_valuation"]) for row in rows]
        bid = [as_float(row["median_accepted_limit_buy"]) for row in rows]
        ask = [as_float(row["median_accepted_limit_sell"]) for row in rows]
        ax.plot(rounds, valuations, color="#6a4c93", linewidth=2.2,
                label="Median reported valuation")
        ax.plot(rounds, recorded, color=COLORS[analysis["name"]], linewidth=2.1,
                marker="o", markersize=3.5, label="Recorded price")
        ax.plot(rounds, bid, color="#2a9d8f", linewidth=1.5, marker="^",
                markersize=4, label="Median accepted limit buy")
        ax.plot(rounds, ask, color="#e76f51", linewidth=1.5, marker="v",
                markersize=4, label="Median accepted limit sell")
        ax.axhline(analysis["fundamental"], color="#588157", linestyle="--",
                   linewidth=1.2, label="Fundamental ($28)")
        ax.set_title(analysis["name"], loc="left", fontweight="bold")
        ax.set_xlabel("Trading round")
        ax.set_ylabel("Price or valuation ($)")
        style_axis(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False,
               bbox_to_anchor=(0.5, -0.08))
    fig.suptitle("Reported valuations remain detached from executable quotes",
                 fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0.08, 1, 0.92))
    fig.savefig(FIGURE_DIR / "canonical_valuation_quote_gap.png", dpi=200,
                bbox_inches="tight")
    plt.close(fig)


def plot_execution_bottleneck(analyses: list[dict]) -> None:
    low_analyses = [analysis for analysis in analyses if analysis["initial_price"] == 14]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.7))

    labels = [analysis["name"].replace("14 ", "") for analysis in low_analyses]
    x = list(range(len(labels)))
    width = 0.34
    buy_ratio = [
        100 * analysis["summary"]["median_limit_buy_price_to_seen_price"]
        for analysis in low_analyses
    ]
    sell_ratio = [
        100 * analysis["summary"]["median_limit_sell_price_to_seen_price"]
        for analysis in low_analyses
    ]
    axes[0].bar([value - width / 2 for value in x], buy_ratio, width,
                color="#2a9d8f", label="Accepted limit buys")
    axes[0].bar([value + width / 2 for value in x], sell_ratio, width,
                color="#e76f51", label="Accepted limit sells")
    axes[0].axhline(100, color="#333333", linestyle="--", linewidth=1.2,
                    label="Price shown to agent")
    axes[0].set_xticks(x, labels)
    axes[0].set_ylabel("Median quote / seen price (%)")
    axes[0].set_title("Quotes anchor to the current price", loc="left", fontweight="bold")
    axes[0].legend(frameon=False, fontsize=8)
    style_axis(axes[0])

    seller_ids = sorted(
        {seller_id for analysis in low_analyses for seller_id in analysis["trade_seller_volume"]},
        key=int,
    )
    bottoms = [0] * len(low_analyses)
    seller_colors = ["#457b9d", "#f4a261", "#6a4c93", "#8ab17d"]
    for index, seller_id in enumerate(seller_ids):
        volumes = [analysis["trade_seller_volume"].get(seller_id, 0) for analysis in low_analyses]
        axes[1].bar(x, volumes, width=0.58, bottom=bottoms,
                    color=seller_colors[index % len(seller_colors)],
                    label=f"Seller agent {seller_id}")
        bottoms = [bottom + volume for bottom, volume in zip(bottoms, volumes)]
    axes[1].set_xticks(x, labels)
    axes[1].set_ylabel("Executed shares")
    axes[1].set_title("All supply comes from market makers", loc="left", fontweight="bold")
    axes[1].legend(frameon=False, fontsize=8)
    style_axis(axes[1])

    fig.suptitle("Why the $14 price path moves only gradually", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(FIGURE_DIR / "canonical_execution_bottleneck.png", dpi=200,
                bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    analyses = [load_run(name, path) for name, path in RUNS.items()]
    summaries = [analysis["summary"] for analysis in analyses]
    rounds = [row for analysis in analyses for row in analysis["rounds"]]
    agent_type_rows: list[dict[str, object]] = []
    for analysis in analyses:
        for agent_type, counts in sorted(analysis["agent_type_categories"].items()):
            agent_type_rows.append(
                {
                    "run": analysis["name"],
                    "agent_type": agent_type,
                    "buy_only_agent_rounds": counts["buy only"],
                    "sell_only_agent_rounds": counts["sell only"],
                    "both_sides_agent_rounds": counts["both sides"],
                    "hold_or_no_order_agent_rounds": counts["hold / no order"],
                    "total_agent_rounds": sum(counts.values()),
                }
            )
    write_csv(TABLE_DIR / "canonical_run_summary.csv", summaries)
    write_csv(TABLE_DIR / "canonical_round_audit.csv", rounds)
    write_csv(TABLE_DIR / "canonical_agent_decision_summary.csv", agent_type_rows)
    mechanism_fields = [
        "run",
        "median_limit_buy_price_to_seen_price",
        "median_limit_sell_price_to_seen_price",
        "median_limit_buy_abs_pct_from_seen_price",
        "median_limit_sell_abs_pct_from_seen_price",
        "market_maker_both_sides_agent_rounds",
        "market_maker_total_agent_rounds",
        "unique_trade_sellers",
        "top_trade_seller_id",
        "top_trade_seller_type",
        "top_trade_seller_volume_share",
    ]
    write_csv(
        TABLE_DIR / "canonical_mechanism_summary.csv",
        [{field: summary.get(field) for field in mechanism_fields} for summary in summaries],
    )
    plot_price_audit(analyses)
    plot_order_funnel(analyses)
    plot_valuation_quote_gap(analyses)
    plot_execution_bottleneck(analyses)

    for summary in summaries:
        print(
            f"{summary['run']}: final recorded={fmt_number(summary['final_recorded_price'])}, "
            f"last trade={fmt_number(summary['last_executed_trade_price'])}, "
            f"proposed B/S={summary['proposed_buy_orders']}/{summary['proposed_sell_orders']}, "
            f"accepted B/S={summary['accepted_buy_orders']}/{summary['accepted_sell_orders']}, "
            f"validation failures={summary['order_validation_failures']}, "
            f"trades={summary['trades']}, quote movement share="
            f"{100 * summary['quote_share_abs_recorded_movement']:.1f}%"
        )


if __name__ == "__main__":
    main()

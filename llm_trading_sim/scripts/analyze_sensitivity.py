"""Summarize sensitivity runs listed in logs/sensitivity/manifest.json (no API calls).

Primary price outcome is the last executed trade price carried forward
(market_data.last_execution_price_to_date); the simulator's recorded price is
kept only for comparison. Writes logs/sensitivity/summary.csv and summary.png.
"""
import csv
import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs" / "sensitivity"
V = 28.0
ROUND_RE = re.compile(r"Start of Round (\d+)")
LEVEL_RE = re.compile(r"Agent (\d+): ([\d.]+) @ \$([\d.]+)")


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def resting_share(path, type_of):
    """Market makers' share of resting quantity in each round's last book snapshot."""
    last, current, side = {}, None, None
    rnd = None
    for line in path.read_text(errors="replace").splitlines():
        if m := ROUND_RE.search(line):
            rnd = int(m.group(1))
        elif "=== Detailed Order Book Round" in line:
            current = []
            last[rnd] = current
            side = None
        elif " - Buy Orders:" in line or " - Sell Orders:" in line:
            side = "buy" if "Buy" in line else "sell"
        elif "Aggregated Order Book" in line:
            side = None
        elif current is not None and side and (m := LEVEL_RE.search(line)):
            current.append((type_of.get(int(m.group(1))), float(m.group(2))))
    rows = [r for snap in last.values() for r in snap]
    total = sum(q for _, q in rows)
    return sum(q for t, q in rows if t == "market_maker") / total if total else np.nan


def summarize(cell_id, rec):
    d = ROOT / rec["run_dir"]
    md = list(csv.DictReader(open(d / "data/market_data.csv")))
    od = pd.read_csv(d / "data/order_data.csv") if (d / "data/order_data.csv").stat().st_size > 2 else pd.DataFrame()
    agents = pd.read_csv(d / "data/agent_data.csv")[["agent_id", "agent_type"]].drop_duplicates()
    type_of = dict(zip(agents.agent_id, agents.agent_type))
    usage = list(csv.DictReader(open(d / "data/llm_usage.csv")))
    sd = pd.read_csv(d / "structured_decisions.csv")
    check = json.loads((d / "dividend_control_check.json").read_text())

    last_trade = num(md[-1].get("last_execution_price_to_date"))
    p0 = float(rec["price"])
    row = {
        "cell_id": cell_id, "block": rec["block"], "price": rec["price"], "path": rec["path"],
        "seed": rec["seed"], "temperature": rec["temperature"], "model": rec["model"],
        "family": rec.get("family") or "",
        "last_trade_15": last_trade,
        "recorded_15": num(md[-1]["price"]),
        "pe_15": abs(last_trade - V) / V if not np.isnan(last_trade) else np.nan,
        "gap_left": abs(np.log(last_trade / V)) / abs(np.log(p0 / V)) if not np.isnan(last_trade) else np.nan,
        "trades": sum(int(r["num_trades"]) for r in md),
        "volume": sum(num(r["total_volume"]) for r in md),
        "zero_volume_rounds": sum(int(r["num_trades"]) == 0 for r in md),
        "dividend_path_ok": bool(check.get("complete")) and bool(check.get("path_match")),
        "llm_calls_ok": f"{sum(r['success'] == 'True' for r in usage)}/{len(usage)}",
        "cost_usd": sum(num(r["cost_usd"]) for r in usage),
        "clipped_orders": (d / "decisions.log").read_text(errors="replace").count("clipped from"),
        "median_valuation_non_opt": sd[sd.agent_type_id != "optimistic"].valuation.median(),
    }
    row["converged"] = row["pe_15"] < 0.10
    if len(od):
        od["agent_type"] = od.agent_id.map(type_of)
        mm = od[od.agent_type == "market_maker"]
        sides = mm.groupby(["agent_id", "round"]).decision.nunique()
        row["mm_two_sided_share"] = (sides == 2).mean() if len(sides) else np.nan
        row["mm_buy_share"] = (mm.decision == "buy").mean() if len(mm) else np.nan
        row["buy_share_all"] = (od.decision == "buy").mean()
    log = d / "order_state.log"
    row["mm_depth_share"] = resting_share(log, type_of) if log.exists() else np.nan
    return row


def main():
    manifest = json.loads((OUT / "manifest.json").read_text())
    rows = [summarize(k, v) for k, v in manifest.items() if v["status"] == "done"]
    df = pd.DataFrame(rows).sort_values(["block", "price", "cell_id"])
    df.to_csv(OUT / "summary.csv", index=False, float_format="%.4f")
    cols = ["cell_id", "last_trade_15", "recorded_15", "pe_15", "converged", "trades",
            "zero_volume_rounds", "mm_two_sided_share", "mm_buy_share", "mm_depth_share",
            "median_valuation_non_opt", "clipped_orders", "dividend_path_ok", "llm_calls_ok", "cost_usd"]
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(df[[c for c in cols if c in df]].round(3).to_string(index=False))
    print(f"\nTotal recorded cost: ${df.cost_usd.sum():.2f}")

    main_runs = df[df.block != "test"]
    if len(main_runs):
        fig, ax = plt.subplots(figsize=(12, 5))
        colors = {"pilot": "#555", "A": "#2f6db4", "B": "#2a9d8f", "C": "#e76f51", "D": "#7b4fb3", "E": "#c98a1b", "R": "#264653"}
        for i, r in enumerate(main_runs.itertuples()):
            ax.scatter(i, r.last_trade_15, color=colors.get(r.block, "k"), s=50, zorder=3)
            ax.plot([i, i], [r.price, r.last_trade_15], color=colors.get(r.block, "k"), alpha=0.4)
            ax.scatter(i, r.price, marker="_", color="#999", s=80)
        ax.axhline(V, color="k", ls="--", lw=1, label="Fundamental $28")
        ax.set_xticks(range(len(main_runs)), main_runs.cell_id, rotation=75, fontsize=7)
        ax.set_ylabel("Last trade price at round 15 ($)")
        ax.set_title("Sensitivity runs: start price (grey dash) to last trade at round 15 (dot), by block (no dot = no trade in 15 rounds)")
        for b, c in colors.items():
            if b in set(main_runs.block):
                ax.scatter([], [], color=c, label=f"Block {b}" if b != "pilot" else "Pilot")
        ax.legend(fontsize=8, ncol=4)
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        fig.savefig(OUT / "summary.png", dpi=170)


if __name__ == "__main__":
    main()

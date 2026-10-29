"""Q2/Q3: do personas trade differently, and do market makers supply liquidity?

This script does not call an LLM. It reads the four Figure 6 runs in
data/runs/ and writes per-persona order-behaviour metrics, simple tests and
two figures under docs/.

Metrics per run and persona:
  limit_share          limit orders / accepted orders (holds excluded)
  two_sided_share      share of active agent-rounds with both a buy and a sell
  median_dist_ref_pct  median |limit price - price shown to agent| / that price
  median_dist_best_pct median distance behind the same-side best quote at the
                       start of the round (0 = joins the best quote)
  mean_abs_imbalance   mean over agent-rounds of |buy qty - sell qty| / (buy + sell)
  depth_share          share of resting book quantity, summed over end-of-round
                       order-book snapshots in order_state.txt
"""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "runs"
FIGURE_DIR = ROOT / "docs" / "figures"
TABLE_DIR = ROOT / "docs" / "tables"

RUNS = {
    "$56 baseline": DATA_ROOT / "fig6_above_baseline",
    "$56 prompt adjusted": DATA_ROOT / "fig6_above_prompt_adjusted",
    "$14 baseline": DATA_ROOT / "fig6_below_baseline",
    "$14 prompt adjusted": DATA_ROOT / "fig6_below_prompt_adjusted",
}
RUN_ORDER = list(RUNS)
COLORS = {
    "$56 baseline": "#264653",
    "$56 prompt adjusted": "#2a9d8f",
    "$14 baseline": "#e76f51",
    "$14 prompt adjusted": "#f4a261",
}
TYPE_ORDER = ["market_maker", "default", "speculator", "optimistic"]
TYPE_LABELS = {"market_maker": "Market maker", "default": "Default",
               "speculator": "Speculator", "optimistic": "Optimistic"}

ROUND_RE = re.compile(r"Start of Round (\d+)")
SNAPSHOT_RE = re.compile(r"=== Detailed Order Book Round")
SIDE_RE = re.compile(r" - (Buy|Sell) Orders:")
LEVEL_RE = re.compile(r"Agent (\d+): ([\d.]+) @ \$([\d.]+)")


def load_run(run: str, run_dir: Path):
    initial_price = pd.read_json(run_dir / "parameters.json", typ="series")["INITIAL_PRICE"]
    agents = pd.read_csv(run_dir / "data/agent_data.csv")[["agent_id", "agent_type"]].drop_duplicates()
    type_of = dict(zip(agents.agent_id, agents.agent_type))

    market = pd.read_csv(run_dir / "data/market_data.csv").sort_values("round")
    bid_col = "pre_match_best_bid" if "pre_match_best_bid" in market else "best_bid"
    ask_col = "pre_match_best_ask" if "pre_match_best_ask" in market else "best_ask"
    # The price agents see in round r is the recorded price at the end of round r-1.
    market["ref_price"] = market["price"].shift(1).fillna(initial_price)
    market = market.rename(columns={bid_col: "pre_bid", ask_col: "pre_ask"})[
        ["round", "ref_price", "pre_bid", "pre_ask"]]

    orders = pd.read_csv(run_dir / "data/order_data.csv")
    orders["agent_type"] = orders.agent_id.map(type_of)
    orders = orders.merge(market, on="round", how="left")
    orders["run"] = run
    return orders, resting_book(run, run_dir / "order_state.txt", type_of)


def resting_book(run: str, path: Path, type_of: dict) -> pd.DataFrame:
    """Resting orders in the last order-book snapshot of each round."""
    last_snapshot, current, side, rnd = {}, None, None, None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if m := ROUND_RE.search(line):
            rnd = int(m.group(1))
        elif SNAPSHOT_RE.search(line):
            current = []
            last_snapshot[rnd] = current
            side = None
        elif m := SIDE_RE.search(line):
            side = m.group(1).lower()
        elif current is not None and side and (m := LEVEL_RE.search(line)):
            aid, qty, price = m.groups()
            current.append({"run": run, "round": rnd, "side": side, "quantity": float(qty),
                            "price": float(price), "agent_type": type_of[int(aid)]})
        elif "Aggregated Order Book" in line:
            side = None
    return pd.DataFrame([row for rows in last_snapshot.values() for row in rows],
                        columns=["run", "round", "side", "quantity", "price", "agent_type"])


def per_type_metrics(orders: pd.DataFrame, book: pd.DataFrame):
    o = orders.copy()
    o["is_limit"] = o.order_type == "limit"
    o["signed_qty"] = np.where(o.decision == "buy", o.quantity, -o.quantity)

    lim = o[o.is_limit].copy()
    lim["dist_ref_pct"] = (lim.price_limit - lim.ref_price).abs() / lim.ref_price * 100
    lim["dist_best_pct"] = np.where(
        lim.decision == "buy",
        (lim.pre_bid - lim.price_limit) / lim.ref_price * 100,
        (lim.price_limit - lim.pre_ask) / lim.ref_price * 100,
    )

    ar = o.groupby(["run", "agent_type", "agent_id", "round"]).agg(
        buy_qty=("signed_qty", lambda s: s[s > 0].sum()),
        sell_qty=("signed_qty", lambda s: -s[s < 0].sum()),
        sides=("decision", "nunique"),
    ).reset_index()
    ar["abs_imbalance"] = (ar.buy_qty - ar.sell_qty).abs() / (ar.buy_qty + ar.sell_qty)
    ar["two_sided"] = ar.sides == 2

    g = ["run", "agent_type"]
    out = o.groupby(g).agg(n_orders=("decision", "size"), limit_share=("is_limit", "mean"),
                           buy_share=("decision", lambda s: (s == "buy").mean()))
    out = out.join(ar.groupby(g).agg(two_sided_share=("two_sided", "mean"),
                                     mean_abs_imbalance=("abs_imbalance", "mean")))
    out = out.join(lim.groupby(g).agg(median_dist_ref_pct=("dist_ref_pct", "median"),
                                      median_dist_best_pct=("dist_best_pct", "median")))
    # Personas that only send market orders leave nothing on the book.
    out["resting_qty"] = book.groupby(g).quantity.sum().reindex(out.index).fillna(0)
    out["depth_share"] = out.resting_qty / out.resting_qty.groupby(level=0).transform("sum")
    out = out.reset_index()
    for col in ("limit_share", "buy_share", "two_sided_share", "depth_share"):
        out[col] *= 100
    return out, o, ar, lim


def tests(o, ar, lim) -> pd.DataFrame:
    rows = []
    for name, prefix in (("$56 runs", "$56"), ("$14 runs", "$14")):
        sub = o[o.run.str.startswith(prefix)]
        runs = sub.run.unique()
        for col, label in (("order_type", "Order type (limit vs market) independent of persona"),
                           ("decision", "Buy/sell mix independent of persona")):
            ct = pd.crosstab(sub.agent_type, sub[col])
            if ct.shape[1] > 1:
                chi2, p, dof, _ = stats.chi2_contingency(ct)
                rows.append({"sample": name, "test": label, "method": f"Chi-square, dof={dof}",
                             "statistic": chi2, "p_value": p, "n": int(ct.values.sum())})
        a = ar[ar.run.isin(runs)]
        groups = [a[a.agent_type == t].abs_imbalance for t in TYPE_ORDER if (a.agent_type == t).any()]
        if len({v for grp in groups for v in grp}) > 1:
            h, p = stats.kruskal(*groups)
            rows.append({"sample": name, "test": "Directionality equal across personas",
                         "method": "Kruskal-Wallis", "statistic": h, "p_value": p, "n": len(a)})
            mm, other = a[a.agent_type == "market_maker"].abs_imbalance, a[a.agent_type != "market_maker"].abs_imbalance
            u, p = stats.mannwhitneyu(mm, other, alternative="less")
            rows.append({"sample": name, "test": "Market makers less directional than others",
                         "method": "Mann-Whitney U, one-sided", "statistic": u, "p_value": p, "n": len(a)})
        l = lim[lim.run.isin(runs)].dropna(subset=["dist_ref_pct"])
        mm, other = l[l.agent_type == "market_maker"].dist_ref_pct, l[l.agent_type != "market_maker"].dist_ref_pct
        if len(mm) and len(other):
            u, p = stats.mannwhitneyu(mm, other, alternative="less")
            rows.append({"sample": name, "test": "Market-maker limit prices closer to current price",
                         "method": "Mann-Whitney U, one-sided", "statistic": u, "p_value": p, "n": len(l)})
    return pd.DataFrame(rows)


def plot_metrics(metrics: pd.DataFrame) -> None:
    panels = [
        ("limit_share", "Limit orders (% of orders)", "Higher = more passive"),
        ("two_sided_share", "Two-sided rounds (% of active rounds)", "Buy and sell in the same round"),
        ("median_dist_ref_pct", "Median limit-price distance (% of price)", "Lower = quotes nearer the price"),
        ("mean_abs_imbalance", "Mean |buy - sell| / (buy + sell)", "1 = fully one-directional"),
        ("depth_share", "Share of resting book quantity (%)", "End-of-round order-book snapshots"),
        ("buy_share", "Buy orders (% of orders)", "50 = balanced"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    x = np.arange(len(TYPE_ORDER))
    width = 0.2
    for ax, (col, title, sub) in zip(axes.flat, panels):
        for i, run in enumerate(RUN_ORDER):
            m = metrics[metrics.run == run].set_index("agent_type").reindex(TYPE_ORDER)
            ax.bar(x + (i - 1.5) * width, m[col].values, width, label=run, color=COLORS[run])
        ax.set_xticks(x, [TYPE_LABELS[t] for t in TYPE_ORDER])
        ax.set_title(f"{title}\n", fontsize=11, loc="left")
        ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=9, color="#666")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.3)
        if col == "buy_share":
            ax.axhline(50, color="#444", lw=0.8, ls="--")
    axes.flat[0].legend(frameon=False, fontsize=9)
    fig.suptitle("Q2/Q3: order behaviour by persona (GPT-4o, T=0, seed 42, 8 agents x 15 rounds)", fontsize=13)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "q2_q3_by_persona.png", dpi=180)
    plt.close(fig)


def plot_depth(book: pd.DataFrame) -> None:
    colors = {"market_maker": "#2a7f62", "default": "#8a8a8a", "speculator": "#c98a1b", "optimistic": "#7b4fb3"}
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    for ax, run in zip(axes, RUN_ORDER):
        piv = (book[book.run == run]
               .pivot_table(index="agent_type", columns="side", values="quantity", aggfunc="sum", fill_value=0)
               .reindex(index=TYPE_ORDER, columns=["buy", "sell"]).fillna(0))
        labels = [TYPE_LABELS[t] for t in TYPE_ORDER]
        ax.barh(labels, -piv["buy"] / 1000, color=[colors[t] for t in TYPE_ORDER], alpha=0.55)
        ax.barh(labels, piv["sell"] / 1000, color=[colors[t] for t in TYPE_ORDER])
        ax.axvline(0, color="#333", lw=0.8)
        ax.set_title(run, fontsize=11)
        ax.set_xlabel("<- bid qty (k shares)   ask qty ->")
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Resting limit liquidity by side (end-of-round snapshots, summed)", fontsize=13)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "q3_book_depth_by_side.png", dpi=180)
    plt.close(fig)


def main() -> None:
    loaded = [load_run(run, path) for run, path in RUNS.items()]
    orders = pd.concat([o for o, _ in loaded])
    book = pd.concat([b for _, b in loaded])

    metrics, o, ar, lim = per_type_metrics(orders, book)
    metrics["run"] = pd.Categorical(metrics.run, RUN_ORDER)
    metrics["agent_type"] = pd.Categorical(metrics.agent_type, TYPE_ORDER)
    metrics = metrics.sort_values(["run", "agent_type"])
    metrics.to_csv(TABLE_DIR / "q2_q3_metrics_by_persona.csv", index=False, float_format="%.2f")

    test_df = tests(o, ar, lim)
    test_df.to_csv(TABLE_DIR / "q2_q3_tests.csv", index=False, float_format="%.4g")

    plot_metrics(metrics)
    plot_depth(book)

    cols = ["run", "agent_type", "n_orders", "limit_share", "two_sided_share", "median_dist_ref_pct",
            "median_dist_best_pct", "mean_abs_imbalance", "buy_share", "depth_share"]
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(metrics[cols].round(2).to_string(index=False))
        print()
        print(test_df.round(4).to_string(index=False))


if __name__ == "__main__":
    main()

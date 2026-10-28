"""Regenerate the two local price panels used in the progress report.

This offline script reads the versioned data package under ``data/runs``.
The two runs compared in each panel are not matched on the realized dividend
path, so the plot is descriptive rather than a causal prompt comparison.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures"
RUNS = {
    "above": {
        "start": 56.0,
        "baseline": ROOT / "data/runs/fig6_above_baseline/data/market_data.csv",
        "prompt": ROOT / "data/runs/fig6_above_prompt_adjusted/data/market_data.csv",
        "ylim": (25, 59),
    },
    "below": {
        "start": 14.0,
        "baseline": ROOT / "data/runs/fig6_below_baseline/data/market_data.csv",
        "prompt": ROOT / "data/runs/fig6_below_prompt_adjusted/data/market_data.csv",
        "ylim": (12, 32),
    },
}


def load_prices(path: Path, start: float) -> tuple[list[int], list[float], int]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    rounds = [0] + [int(row["round"]) for row in rows]
    prices = [start] + [float(row["price"]) for row in rows]
    trades = sum(int(row["num_trades"]) for row in rows)
    return rounds, prices, trades


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for side, config in RUNS.items():
        x_base, y_base, n_base = load_prices(config["baseline"], config["start"])
        x_prompt, y_prompt, n_prompt = load_prices(config["prompt"], config["start"])

        fig, ax = plt.subplots(figsize=(10.5, 5.25), layout="constrained")
        ax.axhline(
            28.0,
            color="#17803d",
            linewidth=2,
            linestyle=(0, (5, 3)),
            label="Fundamental value: $28",
        )
        ax.plot(
            x_base,
            y_base,
            color="#2456a6",
            linewidth=2.5,
            marker="o",
            markersize=3.5,
            label=f"Our baseline recorded price ({n_base} trades)",
        )
        ax.plot(
            x_prompt,
            y_prompt,
            color="#ba5638",
            linewidth=2.2,
            linestyle="--",
            marker="s",
            markersize=3.3,
            label=f"Prompt-adjusted recorded price ({n_prompt} trades)",
        )
        ax.set(
            xlim=(0, 15),
            ylim=config["ylim"],
            xticks=range(0, 16, 3),
            xlabel="Trading round",
            ylabel="Recorded price ($)",
            title=f"Our current-code runs: ${config['start']:.0f} initial price",
        )
        ax.grid(alpha=0.2)
        ax.legend(
            loc="lower left" if side == "above" else "upper left",
            fontsize=9,
            frameon=True,
        )
        fig.savefig(OUT / f"ours_fig6_{side}.png", dpi=200, facecolor="white")
        plt.close(fig)


if __name__ == "__main__":
    main()

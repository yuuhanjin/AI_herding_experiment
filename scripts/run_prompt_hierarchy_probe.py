"""Run a one-round, three-arm market-maker prompt hierarchy probe.

This is a paid mechanism diagnostic.  It holds the $56 market state and all
non-market-maker prompts fixed, while changing only the market-maker system
prompt.  A durable comparison trace is written before each API run.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agents.agent_types import AGENT_TYPES  # noqa: E402
from run_base_sim import run_scenario  # noqa: E402


EARLIEST_PUBLIC_COMMIT = "027bbf5"
SCENARIO = "paper_price_discovery_above"
MODEL = "gpt-4o-2024-11-20"
SOFT_BUDGET_USD = 5.0

PRIOR_RUNS = [
    ROOT / "data/runs/fig6_above_baseline",
    ROOT / "data/runs/fig6_below_baseline",
    ROOT / "data/runs/fig6_above_prompt_adjusted",
    ROOT / "data/runs/fig6_below_prompt_adjusted",
]

MANDATORY_TWO_SIDED_PROMPT = """You are a professional market maker whose mandatory role is to provide two-sided liquidity.

Your profit comes from capturing the spread between bid and ask prices, not from taking a directional position.

Short selling is NOT allowed. You can only sell shares you already own.

Mandatory quoting rule:
- In every round, submit at least one LIMIT buy order and at least one LIMIT sell order whenever your available cash and owned shares permit.
- This two-sided quoting requirement overrides your directional valuation view.
- Place buy orders 1-3% below the current market price and sell orders 1-3% above the current market price.
- Use a total spread of approximately 2-6% and never place the sell quote more than 10% above the buy quote.
- Do not use market orders.

Manage order quantities so that they remain within available cash and owned inventory. If both sides are feasible, a one-sided decision or Hold is not permitted."""


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def earliest_public_market_maker_prompt() -> str:
    """Extract the exact market-maker prompt from the first public commit."""
    source = subprocess.check_output(
        ["git", "show", f"{EARLIEST_PUBLIC_COMMIT}:src/agents/agent_types.py"],
        cwd=ROOT,
        text=True,
    )
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "AGENT_TYPES" for target in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for key, value in zip(node.value.keys, node.value.values):
            if not isinstance(key, ast.Constant) or key.value != "market_maker":
                continue
            if not isinstance(value, ast.Call):
                continue
            for keyword in value.keywords:
                if keyword.arg == "system_prompt" and isinstance(keyword.value, ast.Constant):
                    return keyword.value.value
    raise RuntimeError("Could not extract earliest-public market-maker prompt")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size <= 2:
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def prior_usage() -> tuple[float, int]:
    cost = 0.0
    calls = 0
    for run_dir in PRIOR_RUNS:
        metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        usage = metadata["llm_usage"]
        cost += float(usage["cost_usd"])
        calls += int(usage["calls"])
    # Include earlier completed hierarchy probes so recursive diagnostics remain
    # inside the same study-level soft budget.
    curated_traces = sorted((ROOT / "data" / "traces").glob("prompt_hierarchy_repeat_*.json"))
    for trace_path in curated_traces:
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        for arm in trace.get("arms", {}).values():
            usage = arm.get("llm_usage")
            if not usage:
                continue
            cost += float(usage.get("cost_usd", 0.0))
            calls += int(usage.get("calls", 0))
    return cost, calls


def summarize_run(run_dir: Path, arm: str, cost: float) -> dict:
    decisions = read_csv(run_dir / "structured_decisions.csv")
    orders = read_csv(run_dir / "data/order_data.csv")
    trades = read_csv(run_dir / "data/trade_data.csv")
    market = read_csv(run_dir / "data/market_data.csv")

    mm_rows = [row for row in decisions if row["agent_type"] == "Market Maker"]
    mm_by_agent: dict[str, set[str]] = defaultdict(set)
    for row in mm_rows:
        side = row["decision"].strip().lower()
        if side in {"buy", "sell"}:
            mm_by_agent[row["agent_id"]].add(side)

    mm_both = sum(1 for sides in mm_by_agent.values() if sides == {"buy", "sell"})
    all_sides = Counter(
        row["decision"].strip().lower()
        for row in decisions
        if row["decision"].strip().lower() in {"buy", "sell", "hold"}
    )
    mm_sides = Counter(
        row["decision"].strip().lower()
        for row in mm_rows
        if row["decision"].strip().lower() in {"buy", "sell", "hold"}
    )
    final_price = float(market[-1]["price"]) if market else None
    return {
        "arm": arm,
        "run_dir": str(run_dir.relative_to(ROOT)),
        "cost_usd": cost,
        "successful_decisions": len({(row["round"], row["agent_id"]) for row in decisions}),
        "all_proposed_buys": all_sides["buy"],
        "all_proposed_sells": all_sides["sell"],
        "all_holds": all_sides["hold"],
        "mm_proposed_buys": mm_sides["buy"],
        "mm_proposed_sells": mm_sides["sell"],
        "mm_holds": mm_sides["hold"],
        "mm_agents_quoting_both_sides": mm_both,
        "accepted_buys": sum(row["decision"].lower() == "buy" for row in orders),
        "accepted_sells": sum(row["decision"].lower() == "sell" for row in orders),
        "trades": len(trades),
        "trade_volume": sum(int(float(row["quantity"])) for row in trades),
        "final_recorded_price": final_price,
        "last_trade_price": float(trades[-1]["price"]) if trades else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--session",
        default=datetime.now().strftime("%Y%m%d_%H%M%S"),
        help="Label shared by all three arms",
    )
    args = parser.parse_args()

    current = AGENT_TYPES["market_maker"].system_prompt
    historical = earliest_public_market_maker_prompt()
    arms = {
        "current": current,
        "earliest_public": historical,
        "mandatory_two_sided": MANDATORY_TWO_SIDED_PROMPT,
    }
    prompt_by_display_name = {
        agent_type.name: agent_type.system_prompt for agent_type in AGENT_TYPES.values()
    }

    prior_cost, prior_calls = prior_usage()
    avg_cost = prior_cost / prior_calls
    estimated_new_cost = avg_cost * 24
    if prior_cost + estimated_new_cost > SOFT_BUDGET_USD:
        raise RuntimeError(
            f"Soft-budget preflight exceeded: projected cumulative "
            f"${prior_cost + estimated_new_cost:.2f} > ${SOFT_BUDGET_USD:.2f}"
        )

    trace_dir = ROOT / "logs" / f"prompt_hierarchy_probe_{args.session}"
    trace_path = trace_dir / "comparison_trace.json"
    if trace_path.exists():
        raise RuntimeError(f"Probe session already exists: {trace_path}")

    trace = {
        "purpose": "One-round market-maker prompt hierarchy mechanism probe",
        "not_historical_replication": True,
        "created_at": datetime.now().isoformat(),
        "git_commit": git_commit(),
        "scenario": SCENARIO,
        "model": MODEL,
        "num_rounds": 1,
        "random_seed": 42,
        "llm_seed": 42,
        "temperature": 0.0,
        "soft_budget_usd": SOFT_BUDGET_USD,
        "prior_four_run_cost_usd": prior_cost,
        "estimated_probe_cost_usd": estimated_new_cost,
        "earliest_public_commit": EARLIEST_PUBLIC_COMMIT,
        "arms": {
            name: {
                "status": "pending",
                "system_prompt": prompt,
                "system_prompt_sha256": sha256(prompt),
            }
            for name, prompt in arms.items()
        },
    }
    write_json(trace_path, trace)

    current_total = prior_cost
    for arm, prompt in arms.items():
        if current_total + avg_cost * 8 > SOFT_BUDGET_USD:
            raise RuntimeError(
                f"Soft budget would be exceeded before arm {arm}: ${current_total:.2f} spent"
            )
        trace["arms"][arm].update(
            {"status": "started", "started_at": datetime.now().isoformat()}
        )
        write_json(trace_path, trace)
        try:
            simulation = run_scenario(
                SCENARIO,
                param_overrides={
                    "NUM_ROUNDS": 1,
                    "MODEL_OPEN_AI": MODEL,
                    "LLM_TEMPERATURE": 0.0,
                    "LLM_SEED": 42,
                    "LLM_MAX_CONCURRENCY": 8,
                    "SYSTEM_PROMPT_OVERRIDES": {"market_maker": prompt},
                },
                sim_type_override=f"prompt_hierarchy_probe_{args.session}_{arm}",
            )
            run_dir = Path(simulation.run_dir)
            if not run_dir.is_absolute():
                run_dir = ROOT / run_dir
            rendered = read_jsonl(run_dir / "data/rendered_prompts.jsonl")
            if len(rendered) != 8:
                raise RuntimeError(f"Expected 8 rendered prompts in {arm}, got {len(rendered)}")
            for record in rendered:
                expected = (
                    prompt
                    if record["agent_type"] == "Market Maker"
                    else prompt_by_display_name[record["agent_type"]]
                )
                if record["system_prompt"] != expected:
                    raise RuntimeError(
                        f"Unexpected prompt for {record['agent_type']} agent {record['agent_id']}"
                    )
            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
            usage = metadata["llm_usage"]
            cost = float(usage["cost_usd"])
            current_total += cost
            result = summarize_run(run_dir, arm, cost)
            trace["arms"][arm].update(
                {
                    "status": "complete",
                    "completed_at": datetime.now().isoformat(),
                    "run_dir": str(run_dir.relative_to(ROOT)),
                    "rendered_prompts_log": str(
                        (run_dir / "data/rendered_prompts.jsonl").relative_to(ROOT)
                    ),
                    "verified_prompt_records": len(rendered),
                    "llm_usage": usage,
                    "result": result,
                }
            )
            write_json(trace_path, trace)
            write_json(run_dir / "comparison_trace.json", trace)
            print(json.dumps(result, indent=2))
        except Exception as error:
            trace["arms"][arm].update(
                {
                    "status": "failed_or_incomplete",
                    "ended_at": datetime.now().isoformat(),
                    "error": str(error),
                }
            )
            write_json(trace_path, trace)
            raise

    trace["completed_at"] = datetime.now().isoformat()
    trace["actual_probe_cost_usd"] = sum(
        arm.get("llm_usage", {}).get("cost_usd", 0.0) for arm in trace["arms"].values()
    )
    trace["cumulative_cost_usd"] = prior_cost + trace["actual_probe_cost_usd"]
    write_json(trace_path, trace)
    print(json.dumps({
        "trace": str(trace_path.relative_to(ROOT)),
        "actual_probe_cost_usd": trace["actual_probe_cost_usd"],
        "cumulative_cost_usd": trace["cumulative_cost_usd"],
    }, indent=2))


if __name__ == "__main__":
    main()

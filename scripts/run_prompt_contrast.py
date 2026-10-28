"""Run a one-factor market-maker prompt contrast with an auditable trace.

Only the market-maker *system prompt* changes. The original scenario and
other agent prompts are left untouched. This is a mechanism test, not an
exact rerun of the paper's historical code.
"""

import argparse
import difflib
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agents.agent_types import AGENT_TYPES  # noqa: E402
from run_base_sim import run_scenario  # noqa: E402


BASELINE_RUNS = {
    "above": ROOT / "data/runs/fig6_above_baseline",
    "below": ROOT / "data/runs/fig6_below_baseline",
}
SCENARIOS = {
    "above": "paper_price_discovery_above",
    "below": "paper_price_discovery_below",
}
PROMPT_REPLACEMENTS = {
    "Short selling is permitted when shares can be borrowed. Manage both long and short inventory carefully.":
        "IMPORTANT: Short selling is NOT allowed. You can only sell shares you already own.",
    "Monitor your current inventory including borrowed shares":
        "Monitor your current inventory of owned shares",
    "You may sell shares you do not own by borrowing them when available":
        "Only place sell orders for quantities of shares you currently own",
}


def sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def prompt_variant(baseline):
    treatment = baseline
    for old, new in PROMPT_REPLACEMENTS.items():
        if treatment.count(old) != 1:
            raise ValueError(f"Expected exactly one occurrence of prompt clause: {old}")
        treatment = treatment.replace(old, new)
    return treatment


def read_prompts(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def git_commit():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=("above", "below"))
    parser.add_argument("--session", required=True, help="Shared label for both contrast runs")
    args = parser.parse_args()

    baseline = AGENT_TYPES["market_maker"].system_prompt
    treatment = prompt_variant(baseline)
    baseline_run = BASELINE_RUNS[args.scenario]
    baseline_prompts = read_prompts(baseline_run / "data/rendered_prompts.jsonl")
    expected_by_type = {row["agent_type"]: row["system_prompt"] for row in baseline_prompts}
    if expected_by_type["Market Maker"] != baseline:
        raise ValueError("Current market-maker prompt differs from the saved baseline; stop contrast")

    trace_path = ROOT / "logs" / f"prompt_contrast_{args.session}" / "comparison_trace.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else {
        "purpose": "One-factor no-short-selling wording contrast for market makers",
        "not_historical_replication": True,
        "created_at": datetime.now().isoformat(),
        "git_commit": git_commit(),
        "prompt_source": "src/agents/prompts/market_maker.md",
        "baseline_system_prompt": baseline,
        "treatment_system_prompt": treatment,
        "baseline_prompt_sha256": sha256(baseline),
        "treatment_prompt_sha256": sha256(treatment),
        "unified_diff": "".join(difflib.unified_diff(
            baseline.splitlines(keepends=True), treatment.splitlines(keepends=True),
            fromfile="baseline", tofile="no_short_wording")),
        "runs": {},
    }
    if trace["baseline_prompt_sha256"] != sha256(baseline) or trace["treatment_prompt_sha256"] != sha256(treatment):
        raise ValueError("Prompt text changed since this contrast session began")
    if args.scenario in trace["runs"]:
        raise ValueError(f"Scenario {args.scenario} already recorded in this session")

    baseline_metadata = json.loads((baseline_run / "metadata.json").read_text(encoding="utf-8"))
    prior_cost = sum(
        json.loads((path / "metadata.json").read_text(encoding="utf-8"))["llm_usage"]["cost_usd"]
        for path in BASELINE_RUNS.values()
    )
    contrast_cost = sum(run.get("cost_usd", 0) for run in trace["runs"].values())
    predicted_total = prior_cost + contrast_cost + baseline_metadata["llm_usage"]["cost_usd"]
    if predicted_total > 5.0:
        raise RuntimeError(f"Soft-budget preflight exceeded: projected cumulative ${predicted_total:.2f} > $5")

    trace["runs"][args.scenario] = {
        "status": "started",
        "started_at": datetime.now().isoformat(),
        "baseline_run": str(baseline_run.relative_to(ROOT)),
        "baseline_cost_usd": baseline_metadata["llm_usage"]["cost_usd"],
        "soft_budget_usd": 5.0,
        "predicted_cumulative_cost_usd": predicted_total,
        "model": baseline_metadata["parameters"]["MODEL_OPEN_AI"],
    }
    write_json(trace_path, trace)  # Durable trace before any paid call.

    try:
        simulation = run_scenario(
            SCENARIOS[args.scenario],
            param_overrides={"SYSTEM_PROMPT_OVERRIDES": {"market_maker": treatment}},
            sim_type_override=f"prompt_contrast_{args.scenario}_{args.session}",
        )
        run_dir = Path(simulation.run_dir)
        if not run_dir.is_absolute():
            run_dir = ROOT / run_dir
        actual_prompts = read_prompts(run_dir / "data/rendered_prompts.jsonl")
        if len(actual_prompts) != 120:
            raise RuntimeError(f"Expected 120 rendered prompts, got {len(actual_prompts)}")
        for row in actual_prompts:
            expected = treatment if row["agent_type"] == "Market Maker" else expected_by_type[row["agent_type"]]
            if row["system_prompt"] != expected:
                raise RuntimeError(f"Unexpected system prompt for agent {row['agent_id']} round {row['round']}")
        metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        trace["runs"][args.scenario].update({
            "status": "complete",
            "completed_at": datetime.now().isoformat(),
            "run_dir": str(run_dir.relative_to(ROOT)),
            "rendered_prompts_log": str((run_dir / "data/rendered_prompts.jsonl").relative_to(ROOT)),
            "verified_prompt_records": len(actual_prompts),
            "cost_usd": metadata["llm_usage"]["cost_usd"],
        })
        write_json(trace_path, trace)
        write_json(run_dir / "comparison_trace.json", trace)
        print(json.dumps(trace["runs"][args.scenario], indent=2))
    except Exception as error:
        trace["runs"][args.scenario].update({
            "status": "failed_or_incomplete",
            "ended_at": datetime.now().isoformat(),
            "error": str(error),
        })
        write_json(trace_path, trace)
        raise


if __name__ == "__main__":
    main()

"""Sensitivity-test runner (Teammate 3 protocol, Table 7 of the Oct 28 report).

Every cell replays one of three fixed dividend paths (D1-D3) with a fixed order
seed, so cells inside a block differ only in the treatment.

Usage (from llm_trading_sim/):
  .venv/bin/python scripts/run_sensitivity.py --design reduced --dry-run
  .venv/bin/python scripts/run_sensitivity.py --design reduced --blocks pilot A --yes
  .venv/bin/python scripts/run_sensitivity.py --pipeline-test --yes   # 2 cheap gpt-4o-mini runs

Output: logs/sensitivity/<cell_id>/<timestamp>/ and logs/sensitivity/manifest.json.
Finished cells are skipped on rerun, so an interrupted batch can be resumed.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))
os.environ.setdefault("LLM_MAX_RETRIES", "2")
os.environ.setdefault("LLM_REQUEST_TIMEOUT", "60")
sys.path.insert(0, str(ROOT / "src"))

BASE_MODEL = "gpt-4o-2024-11-20"
CHEAP_MODEL = "gpt-4o-mini"
COST_PER_RUN = {BASE_MODEL: 0.72, CHEAP_MODEL: 0.04}  # observed / estimated, 15 rounds
ORDER_SEED = 42
OUT = ROOT / "logs" / "sensitivity"
PATH_DIR = OUT / "dividend_paths"

# Scenario per starting price; $35/$21 reuse the $56/$14 scenarios with a new price.
PRICES = {56: "paper_price_discovery_above", 14: "paper_price_discovery_below",
          35: "paper_price_discovery_above", 21: "paper_price_discovery_below"}


def cell(block, price, path, seed=1, temp=0.0, model=BASE_MODEL, family=None, rep=None):
    parts = [block, f"p{price}", path, f"s{seed}", f"t{temp:g}", model.replace("-", "")]
    if family:
        parts.append(family.replace("family_", ""))
    if rep:
        parts.append(f"r{rep}")
    return {"cell_id": "_".join(parts), "block": block, "price": price, "path": path,
            "seed": seed, "temperature": temp, "model": model, "family": family}


def grid(design):
    full = design == "full"
    paths = ["D1", "D2", "D3"]
    cells = [cell("pilot", 56, "D1", rep=r) for r in (1, 2)]
    for price in (56, 14):
        for p in paths:
            for s in ((1, 2) if full else (1,)):
                cells.append(cell("A", price, p, seed=s))
    for price in (35, 21):
        for p in (paths if full else ["D1"]):
            cells.append(cell("B", price, p))
    for price in (56, 14):
        for t in ((0.5, 1.0) if full else (1.0,)):
            for s in ((1, 2) if full else (1,)):
                cells.append(cell("C", price, "D1", seed=s, temp=t))
    for price in (56, 14):
        for fam in (["family_p1", "family_p2", "family_p3", "family_p4"] if full
                    else ["family_p1", "family_p2"]):
            cells.append(cell("D", price, "D1", family=fam))
    for price in (56, 14):
        for p in paths:
            cells.append(cell("E", price, p, model=CHEAP_MODEL))
    # R: extra baseline replications (LLM seeds 2-5, same D1 path) to measure the noise floor,
    # added after the pilot showed large run-to-run variation at T = 0.
    for price in (56, 14):
        for s in (2, 3, 4, 5):
            cells.append(cell("R", price, "D1", seed=s))
    return cells


def ensure_paths():
    from scenarios import get_scenario
    from dividend_controls import generate_path
    PATH_DIR.mkdir(parents=True, exist_ok=True)
    params = get_scenario("paper_price_discovery_above").parameters
    for k in (1, 2, 3):
        f = PATH_DIR / f"D{k}.json"
        if not f.exists():
            f.write_text(json.dumps(generate_path(params, seed=k), indent=2))
    return {f"D{k}": PATH_DIR / f"D{k}.json" for k in (1, 2, 3)}


def overrides(c, path_file):
    o = {"MODEL_OPEN_AI": c["model"], "LLM_SEED": c["seed"], "LLM_TEMPERATURE": c["temperature"],
         "INITIAL_PRICE": float(c["price"]), "LLM_MAX_CONCURRENCY": 4,
         "DIVIDEND_CONTROL": {"mode": "replay", "order_seed": ORDER_SEED, "path_file": str(path_file)}}
    if c["family"]:
        families = json.loads((ROOT / "sweeps/variants/persona_families.json").read_text())
        o.update(families[c["family"]])
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", choices=["full", "reduced"], default="reduced")
    ap.add_argument("--blocks", nargs="+", default=None, help="e.g. pilot A B C D E")
    ap.add_argument("--pipeline-test", action="store_true",
                    help="Run two 15-round gpt-4o-mini cells ($56, $14) to check the pipeline")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    if args.pipeline_test:
        cells = [cell("test", p, "D1", model=CHEAP_MODEL) for p in (56, 14)]
    else:
        cells = [c for c in grid(args.design) if not args.blocks or c["block"] in args.blocks]

    OUT.mkdir(parents=True, exist_ok=True)
    manifest_file = OUT / "manifest.json"
    manifest = json.loads(manifest_file.read_text()) if manifest_file.exists() else {}
    todo = [c for c in cells if manifest.get(c["cell_id"], {}).get("status") != "done"]
    cost = sum(COST_PER_RUN[c["model"]] for c in todo)
    print(f"{len(cells)} cells selected, {len(todo)} to run, estimated cost ${cost:.2f}")
    for c in todo:
        print("  ", c["cell_id"])
    if args.dry_run or not todo:
        return
    if not args.yes and input("Run these paid cells? [y/N] ").strip().lower() != "y":
        return

    from dotenv import dotenv_values
    key = dotenv_values(ROOT / ".env").get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY missing: run `.venv/bin/python replicate.py key` first.")
    os.environ["OPENAI_API_KEY"] = key
    from run_base_sim import run_scenario

    paths = ensure_paths()
    for i, c in enumerate(todo, 1):
        print(f"\n[{i}/{len(todo)}] {c['cell_id']}", flush=True)
        record = {**c, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
        try:
            sim = run_scenario(PRICES[c["price"]], param_overrides=overrides(c, paths[c["path"]]),
                               sim_type_override=f"sensitivity/{c['cell_id']}")
            record.update(status="done", run_dir=str(sim.run_dir))
        except Exception as e:  # keep going; failed cells are retried on the next run
            record.update(status="failed", error=f"{type(e).__name__}: {e}")
            print("  FAILED:", record["error"], flush=True)
        manifest[c["cell_id"]] = record
        manifest_file.write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

"""Local replication entry point; --check makes no API requests."""
import argparse
import getpass
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))
os.environ.setdefault("LLM_MAX_RETRIES", "2")
os.environ.setdefault("LLM_REQUEST_TIMEOUT", "60")
sys.path.insert(0, str(ROOT / "src"))
parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=["check", "key", "pilot", "above", "below"])
parser.add_argument('--dividend-mode', choices=['legacy','independent','replay'], default='legacy')
parser.add_argument('--dividend-seed', type=int, default=42)
parser.add_argument('--order-seed', type=int, default=42)
parser.add_argument('--dividend-path', help='JSON file with zero-based payment rounds')
args = parser.parse_args()
if args.mode == "key":
    from dotenv import set_key
    key = getpass.getpass("Paste your API key (hidden), then press Enter: ").strip()
    if not key or any(c.isspace() for c in key):
        raise SystemExit("Key not saved: empty or contains whitespace.")
    env_path = ROOT / ".env"
    env_path.touch(mode=0o600, exist_ok=True)
    env_path.chmod(0o600)
    set_key(str(env_path), "OPENAI_API_KEY", key)
    print("Key saved locally. No API request was made.")
    raise SystemExit(0)

from scenarios import get_scenario
from scenarios.base import DEFAULT_LLM_BASE_URL, DEFAULT_LLM_MODEL
from dotenv import dotenv_values
key = dotenv_values(ROOT / ".env").get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
if args.mode == "check":
    assert DEFAULT_LLM_BASE_URL == "https://openrouter.ai/api/v1"
    assert DEFAULT_LLM_MODEL == "openai/gpt-4o-2024-11-20"
    for side in ("above", "below"):
        p = get_scenario("paper_price_discovery_" + side).parameters
        assert p["NUM_ROUNDS"] == 15
        assert sum(p["AGENT_PARAMS"]["agent_composition"].values()) == 8
        assert abs(p["FUNDAMENTAL_PRICE"] - 28) < 1e-8
        print(side, "price:", p["INITIAL_PRICE"], "rounds:", p["NUM_ROUNDS"], "fundamental:", p["FUNDAMENTAL_PRICE"])
    print("Endpoint:", DEFAULT_LLM_BASE_URL)
    print("Model:", DEFAULT_LLM_MODEL)
    print("API key:", "configured (not validated)" if key else "not configured")
    print("Offline configuration check passed. No API calls made.")
    raise SystemExit(0)
if not key:
    raise SystemExit("API key missing. Run the key setup first.")
os.environ["OPENAI_API_KEY"] = key
from run_base_sim import run_scenario
side = "above" if args.mode == "pilot" else args.mode
rounds = 2 if args.mode == "pilot" else 15
print(f"Starting {rounds} rounds with 8 agents. This makes paid API requests.")
run_scenario("paper_price_discovery_" + side,
    param_overrides={"NUM_ROUNDS": rounds, "MODEL_OPEN_AI": DEFAULT_LLM_MODEL,
                     "LLM_MAX_CONCURRENCY": 2,
                     "DIVIDEND_CONTROL": {"mode": args.dividend_mode,
                         "seed": args.dividend_seed, "order_seed": args.order_seed,
                         **({"path_file": str(Path(args.dividend_path).resolve())} if args.dividend_path else {})}},
    sim_type_override="replication_" + args.mode + ("_" + args.dividend_mode if args.dividend_mode != "legacy" else ""))

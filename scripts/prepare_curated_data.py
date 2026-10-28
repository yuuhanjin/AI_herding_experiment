"""Build the small, shareable evidence package used by the research reports.

The simulator writes large timestamped directories under ``logs/``.  Those
directories are intentionally ignored by Git.  This script copies only the
files required to audit and reproduce the offline analyses into stable paths
under ``data/`` and writes SHA-256 checksums for every copied file.

It never calls an LLM and never copies ``.env`` or API credentials.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"

RUNS = {
    "fig6_above_baseline": {
        "source": "logs/replication_fig6_above_seed42/20261014_234547",
        "study": "figure_6_7",
        "scenario": "above",
        "variant": "baseline",
    },
    "fig6_below_baseline": {
        "source": "logs/replication_fig6_below_seed42/20261014_234649",
        "study": "figure_6_7",
        "scenario": "below",
        "variant": "baseline",
    },
    "fig6_above_prompt_adjusted": {
        "source": "logs/prompt_contrast_above_20261015_no_short_wording/20261015_000510",
        "study": "figure_6_7",
        "scenario": "above",
        "variant": "market_maker_no_short_wording",
    },
    "fig6_below_prompt_adjusted": {
        "source": "logs/prompt_contrast_below_20261015_no_short_wording/20261015_000618",
        "study": "figure_6_7",
        "scenario": "below",
        "variant": "market_maker_no_short_wording",
    },
    "prompt_probe_r1_current": {
        "source": "logs/prompt_hierarchy_probe_20261021_mechanism_current/20261021_212843",
        "study": "prompt_hierarchy_probe",
        "repeat": 1,
        "arm": "current",
    },
    "prompt_probe_r1_earliest_public": {
        "source": "logs/prompt_hierarchy_probe_20261021_mechanism_earliest_public/20261021_212922",
        "study": "prompt_hierarchy_probe",
        "repeat": 1,
        "arm": "earliest_public",
    },
    "prompt_probe_r1_mandatory_two_sided": {
        "source": "logs/prompt_hierarchy_probe_20261021_mechanism_mandatory_two_sided/20261021_212955",
        "study": "prompt_hierarchy_probe",
        "repeat": 1,
        "arm": "mandatory_two_sided",
    },
    "prompt_probe_r2_current": {
        "source": "logs/prompt_hierarchy_probe_20261021_mechanism_r2_current/20261021_213106",
        "study": "prompt_hierarchy_probe",
        "repeat": 2,
        "arm": "current",
    },
    "prompt_probe_r2_earliest_public": {
        "source": "logs/prompt_hierarchy_probe_20261021_mechanism_r2_earliest_public/20261021_213132",
        "study": "prompt_hierarchy_probe",
        "repeat": 2,
        "arm": "earliest_public",
    },
    "prompt_probe_r2_mandatory_two_sided": {
        "source": "logs/prompt_hierarchy_probe_20261021_mechanism_r2_mandatory_two_sided/20261021_213157",
        "study": "prompt_hierarchy_probe",
        "repeat": 2,
        "arm": "mandatory_two_sided",
    },
    "prompt_probe_r3_current": {
        "source": "logs/prompt_hierarchy_probe_20261021_mechanism_r3_current/20261021_213237",
        "study": "prompt_hierarchy_probe",
        "repeat": 3,
        "arm": "current",
    },
    "prompt_probe_r3_earliest_public": {
        "source": "logs/prompt_hierarchy_probe_20261021_mechanism_r3_earliest_public/20261021_213313",
        "study": "prompt_hierarchy_probe",
        "repeat": 3,
        "arm": "earliest_public",
    },
    "prompt_probe_r3_mandatory_two_sided": {
        "source": "logs/prompt_hierarchy_probe_20261021_mechanism_r3_mandatory_two_sided/20261021_213346",
        "study": "prompt_hierarchy_probe",
        "repeat": 3,
        "arm": "mandatory_two_sided",
    },
}

TRACE_FILES = {
    "prompt_hierarchy_repeat_1.json": (
        "logs/prompt_hierarchy_probe_20261021_mechanism/comparison_trace.json"
    ),
    "prompt_hierarchy_repeat_2.json": (
        "logs/prompt_hierarchy_probe_20261021_mechanism_r2/comparison_trace.json"
    ),
    "prompt_hierarchy_repeat_3.json": (
        "logs/prompt_hierarchy_probe_20261021_mechanism_r3/comparison_trace.json"
    ),
}

RUN_FILES = (
    ("metadata.json", "metadata.json"),
    ("parameters.json", "parameters.json"),
    ("structured_decisions.csv", "structured_decisions.csv"),
    ("validation_errors.csv", "validation_errors.csv"),
    # The source is a log, but the curated evidence uses .txt so it is not
    # hidden by the repository-wide *.log ignore rule.
    ("order_state.log", "order_state.txt"),
    ("comparison_trace.json", "comparison_trace.json"),
    ("data/agent_data.csv", "data/agent_data.csv"),
    ("data/dividend_data.csv", "data/dividend_data.csv"),
    ("data/llm_usage.csv", "data/llm_usage.csv"),
    ("data/market_data.csv", "data/market_data.csv"),
    ("data/order_data.csv", "data/order_data.csv"),
    ("data/rendered_prompts.jsonl", "data/rendered_prompts.jsonl"),
    ("data/trade_data.csv", "data/trade_data.csv"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_and_describe(source: Path, destination: Path) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Normalize line endings before hashing. Git is configured to retain LF for
    # curated evidence, so the checksum is identical on Windows, macOS, Linux,
    # and in the repository blob itself.
    destination.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))
    return {
        "path": destination.relative_to(ROOT).as_posix(),
        "bytes": destination.stat().st_size,
        "sha256": sha256(destination),
    }


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def main() -> None:
    manifest: dict[str, object] = {
        "schema_version": 1,
        "generated_on": date.today().isoformat(),
        "source_repository_commit": git_commit(),
        "description": (
            "Curated evidence for the Figure 6-7 replication and the "
            "market-maker prompt hierarchy probe."
        ),
        "runs": {},
        "traces": [],
    }

    for run_id, details in RUNS.items():
        source_dir = ROOT / str(details["source"])
        if not source_dir.is_dir():
            raise FileNotFoundError(f"Missing source run: {source_dir}")
        destination_dir = DATA_ROOT / "runs" / run_id
        copied = []
        for source_name, destination_name in RUN_FILES:
            source = source_dir / source_name
            if not source.exists():
                if source_name == "comparison_trace.json":
                    continue
                raise FileNotFoundError(f"Missing required evidence file: {source}")
            copied.append(copy_and_describe(source, destination_dir / destination_name))
        manifest["runs"][run_id] = {
            key: value for key, value in details.items() if key != "source"
        } | {
            "original_local_source": str(details["source"]),
            "files": copied,
        }

    for destination_name, source_name in TRACE_FILES.items():
        source = ROOT / source_name
        if not source.exists():
            raise FileNotFoundError(f"Missing source trace: {source}")
        manifest["traces"].append(
            copy_and_describe(source, DATA_ROOT / "traces" / destination_name)
        )

    manifest_path = DATA_ROOT / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    total_bytes = sum(
        int(file_record["bytes"])
        for run_record in manifest["runs"].values()
        for file_record in run_record["files"]
    ) + sum(int(file_record["bytes"]) for file_record in manifest["traces"])
    print(f"Wrote {len(RUNS)} curated runs to {DATA_ROOT}")
    print(f"Curated package size: {total_bytes / 1024 / 1024:.2f} MiB")


if __name__ == "__main__":
    main()

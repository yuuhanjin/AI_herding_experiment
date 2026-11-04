"""Read-only measurements and provenance; no API calls or random draws."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import importlib.metadata
import subprocess
import sys
import zipfile
from urllib.parse import urlsplit


def price_snapshot(trades, bid, ask, recorded_price, previous_execution=None):
    last = float(trades[-1].price) if trades else None
    return {'recorded_price': recorded_price,
            'last_execution_price_this_round': last,
            'last_execution_price_to_date': last if last is not None else previous_execution,
            'best_bid_post_match': bid, 'best_ask_post_match': ask,
            'midpoint_post_match': (bid + ask) / 2 if bid is not None and ask is not None else None,
            'execution_price_is_stale': not bool(trades) and previous_execution is not None,
            'quote_snapshot_phase': 'post_matching', 'price_audit_schema': 1}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_params(value):
    if isinstance(value, dict):
        return {k: ('[redacted]' if any(s in k.lower() for s in
                ('api_key', 'password', 'secret', 'token', 'authorization')) else safe_params(v))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_params(v) for v in value]
    return value


def write_manifest(run_dir, params, status):
    root = Path(__file__).resolve().parents[1]
    run_dir = Path(run_dir)
    target = run_dir / 'run_manifest.json'
    manifest = json.loads(target.read_text()) if target.exists() else {}
    if not manifest:
        baseline_path = root / 'audit/upstream_baseline.json'
        baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
        candidates = [p for p in (root / 'src').rglob('*') if p.is_file()
                      and p.suffix in ('.py', '.md', '.json') and '__pycache__' not in p.parts]
        candidates += [root / p for p in ('replicate.py', 'requirements.txt', 'pyproject.toml')
                       if (root / p).exists()]
        # llm_config can contain private configuration; record its hash, not its contents.
        hashes = {str(p.relative_to(root)): digest(p) for p in sorted(candidates)}
        with zipfile.ZipFile(run_dir / 'source_snapshot.zip', 'w', zipfile.ZIP_DEFLATED) as z:
            for p in candidates:
                if p.name != 'llm_config.py':
                    z.write(p, str(p.relative_to(root)))
        from scenarios.base import DEFAULT_LLM_BASE_URL
        parsed = urlsplit(DEFAULT_LLM_BASE_URL or 'https://api.openai.com/v1')
        endpoint = parsed.scheme + '://' + (parsed.hostname or '') + parsed.path
        manifest = {'schema': 1, 'captured_at_run_start': datetime.now(timezone.utc).isoformat(),
                    'provenance_kind': 'run_time_capture', 'upstream_reference': baseline.get('commit'),
                    'source_sha256': hashes,
                    'changed_from_reference': [p for p, h in hashes.items()
                        if p in baseline.get('files', {}) and h != baseline['files'][p]],
                    'added_to_reference': [p for p in hashes if p not in baseline.get('files', {})],
                    'parameters': safe_params(params), 'endpoint': endpoint,
                    'python': sys.version, 'source_snapshot': 'source_snapshot.zip',
                    'snapshot_exclusions': ['.env', 'llm_config.py (hash and endpoint only)', 'logs', '.venv'],
                    'dependencies': sorted({d.metadata['Name']: d.version for d in
                                           importlib.metadata.distributions() if d.metadata['Name']}.items())}
        (run_dir / 'parameters_audit.json').write_text(json.dumps(safe_params(params), indent=2, default=str))
    manifest['status'] = status
    manifest['updated_at'] = datetime.now(timezone.utc).isoformat()
    manifest['output_sha256'] = {str(p.relative_to(run_dir)): digest(p)
        for p in sorted((run_dir / 'data').glob('*')) if p.is_file()}
    target.write_text(json.dumps(manifest, indent=2, default=str))

"""Run AFTER 100-candidate experiment completes.
Fixes metrics extraction, re-fetches real BRAIN results, re-scores, generates final report.

Usage:
    python experiments/post_experiment_analysis.py [--results PATH] [--inspect FIRST_SIM_ID]
"""
import os, sys, json, time, base64
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

import requests
from brain_alpha_ops.config import load_run_config
from experiments.validate_scoring import ScoringValidator


# ═══════════════════════════════════════════════════════════════
# Step 0: Auth helper
# ═══════════════════════════════════════════════════════════════

def _create_session() -> requests.Session:
    username = os.environ.get("BRAIN_USERNAME", "")
    password = os.environ.get("BRAIN_PASSWORD", "")
    auth_b64 = base64.b64encode(f"{username}:{password}".encode()).decode()
    session = requests.Session()
    resp = session.post(
        "https://api.worldquantbrain.com/authentication",
        headers={"Authorization": f"Basic {auth_b64}"},
        timeout=60
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Auth failed: {resp.status_code} {resp.text[:200]}")
    print(f"[Auth] {resp.status_code}")
    return session


# ═══════════════════════════════════════════════════════════════
# Step 1: Inspect — dump full structure of one sim result
# ═══════════════════════════════════════════════════════════════

def inspect_result_structure(session: requests.Session, sim_id: str) -> dict:
    """Fetch one simulation result and dump the FULL JSON structure."""
    url = f"https://api.worldquantbrain.com/simulations/{sim_id}"
    print(f"\n{'='*60}")
    print(f"  Inspecting: {sim_id}")
    print(f"  URL: {url}")
    print(f"{'='*60}")

    resp = session.get(url, timeout=60)
    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code}: {resp.text[:300]}")
        return {}

    data = resp.json()
    # Print full structure (truncated for readability)
    raw = json.dumps(data, indent=2, default=str)
    print(raw[:3000])
    if len(raw) > 3000:
        print(f"\n  ... truncated ({len(raw)} total chars)")

    # Save raw dump for offline inspection
    dump_path = Path("experiments/_inspect_result.json")
    with open(dump_path, "w") as f:
        f.write(raw)
    print(f"\n  Full JSON saved to: {dump_path}")

    return data


# ═══════════════════════════════════════════════════════════════
# Step 2: extract_metrics — FIXED version with deep traversal
# ═══════════════════════════════════════════════════════════════

def extract_metrics_deep(result_data: dict) -> dict:
    """Drill into correct nesting level to extract BRAIN metrics."""
    source = result_data
    candidates = []

    # Collect candidates from known nesting patterns
    if "sharpe" in source or "Sharpe" in source:
        candidates.append(("top_level", source))
    if "is" in source and isinstance(source["is"], dict):
        candidates.append(("result['is']", source["is"]))
    if "result" in source and isinstance(source["result"], dict):
        r = source["result"]
        if "is" in r and isinstance(r["is"], dict):
            candidates.append(("result['result']['is']", r["is"]))
        candidates.append(("result['result']", r))
    if "stats" in source and isinstance(source["stats"], dict):
        candidates.append(("result['stats']", source["stats"]))
    # metrics alongside pnl
    if "pnl" in source:
        metrics_keys = {"sharpe", "fitness", "turnover", "Sharpe", "Fitness", "Turnover"}
        if metrics_keys & set(source.keys()):
            candidates.append(("top_level_with_pnl", source))

    for label, c in candidates:
        sharpe = c.get("sharpe") or c.get("Sharpe")
        if sharpe is not None:
            return _build_metrics_dict(c, label)

    # Nothing found — return diagnostic info
    return {
        "sharpe": 0, "fitness": 0, "turnover": 0, "returns": 0,
        "drawdown": 0, "margin": 0, "sub_universe_sharpe": 0,
        "correlation": 0, "weight_concentration": 0,
        "pass_fail": "EXTRACTION_FAILED",
        "failure_reason": "Could not locate metrics in result JSON",
        "extraction_source": "none_found",
        "_raw_keys": sorted(result_data.keys()),
    }


def _build_metrics_dict(c: dict, source_label: str) -> dict:
    def sf(*keys):
        for k in keys:
            v = c.get(k)
            if v is not None:
                try:
                    return round(float(v), 4)
                except (TypeError, ValueError):
                    pass
        return 0.0

    return {
        "sharpe": sf("sharpe", "Sharpe"),
        "fitness": sf("fitness", "Fitness"),
        "turnover": sf("turnover", "Turnover"),
        "returns": sf("returns", "Returns", "pnl_ann", "PnL"),
        "drawdown": sf("drawdown", "maxDrawdown", "Drawdown", "max_drawdown"),
        "margin": sf("margin", "Margin"),
        "sub_universe_sharpe": sf("sub_universe_sharpe", "subSharpe", "subUniversSharpe"),
        "correlation": sf("correlation", "selfCorrelation", "Correlation"),
        "weight_concentration": sf("weight_concentration", "weightConcentration"),
        "pass_fail": str(c.get("pass_fail") or c.get("pass") or c.get("status", "UNKNOWN")).upper(),
        "failure_reason": c.get("failure_reason") or c.get("failure") or c.get("message"),
        "extraction_source": source_label,
    }


# ═══════════════════════════════════════════════════════════════
# Step 3-5: Refetch + rescore + analyze
# ═══════════════════════════════════════════════════════════════

def reprocess_experiment(results_path: str = None, inspect_first: bool = True):
    """Main entry: refetch all results, extract correct metrics, rescore, generate report."""
    if results_path is None:
        # Auto-find
        candidates = sorted(
            Path("experiments").glob("_intermediate_results*.json"),
            key=lambda p: p.stat().st_mtime, reverse=True
        )
        if not candidates:
            print("No _intermediate_results*.json found.")
            return
        results_path = str(candidates[0])

    print(f"Loading: {results_path}")
    with open(results_path) as f:
        stored = json.load(f)

    print(f"  Rows: {stored.get('total', len(stored.get('results', [])))}")
    print(f"  Stored completed: {stored.get('completed', 0)}, failed: {stored.get('failed', 0)}")

    stored_results = stored.get("results", [])
    completed = [r for r in stored_results if r.get("status") == "completed"]

    if not completed:
        print("No completed results found — nothing to reprocess.")
        return

    # ── Extract sim_ids from log and match to results ──
    log_path = _find_latest_log()
    sim_ids = _extract_sim_ids_from_log(log_path) if log_path else []
    print(f"  Extracted {len(sim_ids)} sim_ids from log")
    for r in completed:
        r_idx = r.get("index", -1)
        if 1 <= r_idx <= len(sim_ids):
            r["_sim_id"] = sim_ids[r_idx - 1]

    # ── Auth ──
    session = _create_session()

    # ── Inspect first result structure ──
    if inspect_first:
        first_with_id = next((r for r in completed if r.get("_sim_id")), None)
        if first_with_id and first_with_id.get("_sim_id"):
            inspect_result_structure(session, first_with_id["_sim_id"])

    # ── Refetch all completed results ──
    print(f"\n{'='*60}")
    print(f"  Refetching {len(completed)} completed results from BRAIN...")
    print(f"{'='*60}")

    fixed_results = []
    extraction_sources = {}

    # Load config for scoring
    config = load_run_config()

    for i, r in enumerate(completed):
        sim_id = r.get("_sim_id")
        if not sim_id:
            r["metrics"] = {"sharpe": 0, "fitness": 0, "turnover": 0,
                            "failure_reason": "No sim_id available for refetch",
                            "extraction_source": "no_sim_id"}
            fixed_results.append(r)
            continue

        try:
            resp = session.get(
                f"https://api.worldquantbrain.com/simulations/{sim_id}",
                timeout=60
            )
            if resp.status_code == 429:
                print(f"  [{i+1}/{len(completed)}] 429 — waiting 60s...")
                time.sleep(60)
                resp = session.get(
                    f"https://api.worldquantbrain.com/simulations/{sim_id}",
                    timeout=60
                )

            if resp.status_code != 200:
                r["metrics"] = {"sharpe": 0, "fitness": 0, "turnover": 0,
                                "failure_reason": f"Refetch HTTP {resp.status_code}",
                                "extraction_source": "refetch_failed"}
                fixed_results.append(r)
                print(f"  [{i+1}/{len(completed)}] {sim_id[:20]}... HTTP {resp.status_code}")
                continue

            data = resp.json()
            r["_raw_simulation"] = data  # store sim response for debugging

            # Get alpha_id, then fetch REAL metrics from /alphas/{alpha_id}
            alpha_id = data.get("alpha", "") or data.get("alphaId", "")
            r["alpha_id"] = str(alpha_id) if alpha_id else ""

            if alpha_id and data.get("status", "").upper() in ("COMPLETE", "COMPLETED"):
                time.sleep(2)  # rate limit safety
                alpha_resp = session.get(
                    f"https://api.worldquantbrain.com/alphas/{alpha_id}",
                    timeout=60
                )
                if alpha_resp.status_code == 200:
                    alpha_data = alpha_resp.json()
                    r["_raw_result"] = alpha_data
                    metrics = extract_metrics_deep(alpha_data)
                else:
                    metrics = {"sharpe": 0, "fitness": 0, "turnover": 0,
                               "failure_reason": f"Alpha endpoint HTTP {alpha_resp.status_code}",
                               "extraction_source": "alpha_fetch_failed"}
            else:
                # No alpha_id — use simulation data directly (will likely have no metrics)
                metrics = extract_metrics_deep(data)
            src = metrics.get("extraction_source", "unknown")
            extraction_sources[src] = extraction_sources.get(src, 0) + 1

            # Merge metrics into result
            r["metrics"] = metrics
            r["metrics_fixed"] = True
            fixed_results.append(r)

            sharpe_str = f"{metrics['sharpe']:.3f}" if metrics['sharpe'] != 0 else "0.000"
            print(f"  [{i+1}/{len(completed)}] {sim_id[:20]}... "
                  f"sharpe={sharpe_str} fitness={metrics['fitness']:.3f} "
                  f"source={src}")

            time.sleep(3)  # rate limit safety

        except Exception as exc:
            r["metrics"] = {"sharpe": 0, "fitness": 0, "turnover": 0,
                            "failure_reason": f"Refetch exception: {type(exc).__name__}",
                            "extraction_source": "exception"}
            fixed_results.append(r)
            print(f"  [{i+1}/{len(completed)}] {sim_id[:20] if sim_id else '?'}... ERROR: {type(exc).__name__}")

    # ── Add failed results as-is ──
    failed_stored = [r for r in stored_results if r.get("status") != "completed"]
    for r in failed_stored:
        r["metrics"] = r.get("metrics", {"sharpe": 0, "fitness": 0, "turnover": 0})
        r["metrics_fixed"] = False
        fixed_results.append(r)

    # ── Analysis ──
    print(f"\n{'='*60}")
    print(f"  ANALYSIS")
    print(f"{'='*60}")

    completed_fixed = [r for r in fixed_results if r.get("metrics_fixed")]
    sharpes = [r["metrics"]["sharpe"] for r in completed_fixed]
    non_zero_sharpes = [s for s in sharpes if s != 0]
    fitnesses = [r["metrics"]["fitness"] for r in completed_fixed]
    turnover_raw = [r["metrics"]["turnover"] for r in completed_fixed]

    print(f"\n  Completed (refetched): {len(completed_fixed)}")
    print(f"  Failed: {len(failed_stored)}")
    print(f"\n  Extraction sources:")
    for src, cnt in sorted(extraction_sources.items(), key=lambda x: -x[1]):
        print(f"    {src}: {cnt}")

    if non_zero_sharpes:
        s = sorted(non_zero_sharpes)
        n = len(s)
        print(f"\n  Sharpe distribution (n={n}):")
        print(f"    Min={min(s):.3f}  P25={s[n//4]:.3f}  Median={s[n//2]:.3f}  P75={s[3*n//4]:.3f}  Max={max(s):.3f}")
        print(f"    Mean={sum(s)/n:.3f}")
        for thresh in [1.25, 1.0, 0.8, 0.5, 0.0]:
            cnt = sum(1 for x in s if x >= thresh)
            print(f"    >= {thresh}: {cnt} ({cnt/n*100:.1f}%)")
    else:
        print(f"\n  [WARN] ALL Sharpes are 0.0 — extraction likely still broken!")
        if completed_fixed:
            raw = completed_fixed[0].get("_raw_result", {})
            print(f"  Dump first raw result keys: {sorted(raw.keys())}")
            if "is" in raw:
                print(f"  'is' keys: {sorted(raw['is'].keys()) if isinstance(raw['is'], dict) else type(raw['is'])}")

    if fitnesses:
        f_sorted = sorted(fitnesses)
        fn = len(f_sorted)
        print(f"\n  Fitness distribution (n={fn}):")
        print(f"    Min={min(f_sorted):.3f}  Median={f_sorted[fn//2]:.3f}  Max={max(f_sorted):.3f}")
        for thresh in [1.0, 0.5]:
            cnt = sum(1 for f in f_sorted if f >= thresh)
            print(f"    >= {thresh}: {cnt} ({cnt/fn*100:.1f}%)")

    # Failure analysis
    if failed_stored:
        print(f"\n  Failure reasons:")
        reasons = {}
        for r in failed_stored:
            err = r.get("error") or r.get("failure_reason") or "unknown"
            if "unknown variable" in str(err).lower() or "unknown operator" in str(err).lower():
                key = "unknown_field_or_operator"
            elif "invalid number of inputs" in str(err).lower():
                key = "syntax_error"
            elif "phantom" in str(err).lower():
                key = "phantom_field"
            elif "timeout" in str(err).lower():
                key = "timeout"
            elif "400" in str(err):
                key = "http_400"
            else:
                key = err[:60] if isinstance(err, str) else str(type(err).__name__)
            reasons[key] = reasons.get(key, 0) + 1
        for reason, cnt in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"    {reason}: {cnt}")

    # ── Save fixed results ──
    fixed_path = Path(results_path).with_suffix("").with_name(
        Path(results_path).stem + "_fixed.json"
    )
    with open(fixed_path, "w") as f:
        json.dump({
            "completed": len(completed_fixed),
            "failed": len(failed_stored),
            "total": len(fixed_results),
            "results": fixed_results,
            "sharpes": sharpes,
            "non_zero_sharpes": non_zero_sharpes,
            "fitnesses": fitnesses,
        }, f, indent=2, default=str)
    print(f"\n  Fixed results: {fixed_path}")

    # ── Generate markdown report ──
    report_path = Path(results_path).with_suffix("").with_name(
        Path(results_path).stem + "_report.md"
    )
    _generate_markdown_report(
        report_path, completed_fixed, failed_stored,
        non_zero_sharpes, fitnesses, extraction_sources
    )
    print(f"  Report: {report_path}")

    return fixed_results


# ═══════════════════════════════════════════════════════════════
# Markdown report generator
# ═══════════════════════════════════════════════════════════════

def _generate_markdown_report(path, completed, failed, sharpes, fitnesses, sources):
    lines = [
        "# BRAIN Alpha 100-Candidate Experiment Report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total candidates | {len(completed) + len(failed)} |",
        f"| COMPLETED (BRAIN simulation) | {len(completed)} |",
        f"| FAILED | {len(failed)} |",
        f"| Success rate | {len(completed)/max(len(completed)+len(failed),1)*100:.1f}% |",
    ]

    if sharpes:
        s = sorted(sharpes)
        n = len(s)
        lines.extend([
            "",
            "## Sharpe Distribution",
            "",
            f"| Percentile | Value |",
            f"|------------|-------|",
            f"| Min | {min(s):.3f} |",
            f"| P25 | {s[n//4]:.3f} |",
            f"| Median | {s[n//2]:.3f} |",
            f"| P75 | {s[3*n//4]:.3f} |",
            f"| Max | {max(s):.3f} |",
            f"| Mean | {sum(s)/n:.3f} |",
            "",
            f"| Threshold | Count | Rate |",
            f"|-----------|-------|------|",
            f"| >= 1.25 | {sum(1 for x in s if x >= 1.25)} | {sum(1 for x in s if x >= 1.25)/n*100:.1f}% |",
            f"| >= 1.00 | {sum(1 for x in s if x >= 1.0)} | {sum(1 for x in s if x >= 1.0)/n*100:.1f}% |",
            f"| >= 0.80 | {sum(1 for x in s if x >= 0.8)} | {sum(1 for x in s if x >= 0.8)/n*100:.1f}% |",
            f"| >= 0.50 | {sum(1 for x in s if x >= 0.5)} | {sum(1 for x in s if x >= 0.5)/n*100:.1f}% |",
        ])
    else:
        lines.extend(["", "[WARN] All Sharpes are 0.0 — extraction likely broken."])

    if fitnesses:
        f = sorted(fitnesses)
        fn = len(f)
        lines.extend([
            "",
            "## Fitness Distribution",
            "",
            f"| Threshold | Count | Rate |",
            f"|-----------|-------|------|",
            f"| >= 1.0 | {sum(1 for x in f if x >= 1.0)} | {sum(1 for x in f if x >= 1.0)/fn*100:.1f}% |",
            f"| >= 0.5 | {sum(1 for x in f if x >= 0.5)} | {sum(1 for x in f if x >= 0.5)/fn*100:.1f}% |",
            f"| Median | {f[fn//2]:.3f} | — |",
        ])

    # Extraction sources
    if sources:
        lines.extend([
            "",
            "## Metrics Extraction",
            "",
            "| Source path | Count |",
            "|-------------|-------|",
        ])
        for src, cnt in sorted(sources.items(), key=lambda x: -x[1]):
            lines.append(f"| {src} | {cnt} |")

    # Top 20
    sorted_comp = sorted(completed, key=lambda r: r.get("metrics", {}).get("sharpe", 0), reverse=True)
    lines.extend([
        "",
        "## Top 20 Candidates by Sharpe",
        "",
        "| # | Alpha ID | Sharpe | Fitness | Turnover | Corr | Expression |",
        "|---|----------|--------|---------|----------|------|------------|",
    ])
    for i, r in enumerate(sorted_comp[:20]):
        m = r.get("metrics", {})
        expr = (r.get("expression") or "")[:45]
        lines.append(
            f"| {i+1} | {r.get('alpha_id', '?')[:12]} | {m.get('sharpe', 0):.3f} | "
            f"{m.get('fitness', 0):.3f} | {m.get('turnover', 0):.3f} | "
            f"{m.get('correlation', 0):.3f} | `{expr}` |"
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _find_latest_log() -> Path | None:
    logs = sorted(Path("experiments").glob("experiment_100c_*.log"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for log in logs:
        if log.stat().st_size > 100:
            return log
    return None


def _extract_sim_ids_from_log(log_path: Path) -> list[str]:
    """Extract simulation IDs from experiment log."""
    sim_ids = []
    with open(log_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            # Pattern: "Submitted: 1BXFRn4Jt4QW9yd1dQF5FVmx... OK"
            if "Submitted:" in line:
                parts = line.split()
                for p in parts:
                    if len(p) >= 20 and p[0].isalnum() and "/" not in p and "." not in p:
                        sim_ids.append(p.strip("."))
                        break
    return sim_ids


# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Post-experiment analysis")
    parser.add_argument("--results", help="Path to _intermediate_results.json")
    parser.add_argument("--inspect", help="Simulation ID to inspect (skip full reprocess)")
    parser.add_argument("--no-inspect", action="store_true", help="Skip structure inspection")
    args = parser.parse_args()

    if args.inspect:
        session = _create_session()
        inspect_result_structure(session, args.inspect)
    else:
        reprocess_experiment(args.results, inspect_first=not args.no_inspect)

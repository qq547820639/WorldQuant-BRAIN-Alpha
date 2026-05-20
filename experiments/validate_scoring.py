"""End-to-end scoring validation experiment.

Generates N Alpha candidates, submits each for official BRAIN simulation,
collects real metrics, then compares the internal scoring system's predictions
against BRAIN's actual results.

Purpose:
    Answer the question: "Does this system produce BRAIN-accepted Alpha?"

Output:
    experiments/validation_report.json   — raw data
    experiments/validation_report.md     — human-readable report

Usage:
    $env:BRAIN_USERNAME = "your@email.com"
    $env:BRAIN_PASSWORD = "your_password"
    python experiments/validate_scoring.py --candidates 50
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Project root ‐──────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from brain_alpha_ops.config import RunConfig, OpsConfig, BrainSettings, load_run_config
from brain_alpha_ops.runner import api_from_run_config
from brain_alpha_ops.research.generator import CandidateGenerator, local_quality, extract_fields, extract_operators
from brain_alpha_ops.research.scoring import build_scorecard, evaluate_quality_gate
from brain_alpha_ops.models import Candidate


# ═══════════════════════════════════════════════════════════════════════════
# Experiment State
# ═══════════════════════════════════════════════════════════════════════════

@dataclasses.dataclass
class ExperimentResult:
    """One candidate's full experiment record."""
    index: int
    expression: str
    fields: list[str]
    operators: list[str]
    family: str
    dataset_id: str

    # Internal scoring (before BRAIN simulation)
    prior_score: float = 0.0
    local_quality: float = 0.0
    local_rank: float = 0.0

    # BRAIN official simulation status
    simulation_status: str = ""           # "submitted" | "completed" | "failed" | "error"
    official_alpha_id: str = ""
    simulation_error: str = ""
    brain_failure_detail: str = ""        # Diagnostic: BRAIN's rejection reason

    # BRAIN official metrics (raw)
    sharpe: float | None = None
    fitness: float | None = None
    turnover: float | None = None
    turnover_raw: float | None = None   # undivided — for correct fitness crosscheck
    returns: float | None = None
    drawdown: float | None = None
    margin: float | None = None
    self_correlation: float | None = None
    weight_concentration: float | None = None
    sub_universe_sharpe: float | None = None
    is_booksize_ratio: float | None = None
    ic_mean: float | None = None
    ic_ir: float | None = None

    # Internal scoring (after BRAIN simulation)
    empirical_score: float = 0.0
    checklist_score: float = 0.0
    total_score: float = 0.0
    decision_band: str = ""
    gate_status: str = ""
    gate_failed_reasons: list[str] = dataclasses.field(default_factory=list)

    # BRAIN official pass/fail
    brain_pass_fail: str = ""            # "PASS" | "FAIL" | "unknown"
    brain_check_passed: bool = False
    brain_is_submittable: bool = False
    brain_errors: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ExperimentReport:
    """Aggregate experiment analysis."""
    total_generated: int = 0
    total_simulated: int = 0
    total_completed: int = 0
    total_failed: int = 0
    total_passed_brain: int = 0      # BRAIN pass_fail == "PASS"
    total_submittable: int = 0       # BRAIN check returned submittable

    # Score distributions
    sharpe_distribution: list[float] = dataclasses.field(default_factory=list)
    fitness_distribution: list[float] = dataclasses.field(default_factory=list)
    turnover_distribution: list[float] = dataclasses.field(default_factory=list)

    # Scoring calibration metrics
    prior_score_vs_sharpe_corr: float | None = None
    total_score_vs_pass_rate: dict[str, float] = dataclasses.field(default_factory=dict)

    # Correlation rejection rate
    expression_correlation_blocked: int = 0
    expression_correlation_block_rate: float = 0.0

    # Field / operator usage
    top_fields: list[tuple[str, int]] = dataclasses.field(default_factory=list)
    top_operators: list[tuple[str, int]] = dataclasses.field(default_factory=list)
    skeleton_distribution: dict[str, int] = dataclasses.field(default_factory=dict)

    results: list[ExperimentResult] = dataclasses.field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# Experiment Runner
# ═══════════════════════════════════════════════════════════════════════════

class ScoringValidator:
    """Runs the end-to-end scoring validation experiment."""

    def __init__(self, run_config: RunConfig, candidate_count: int = 50):
        self.run_config = run_config
        self.candidate_count = candidate_count
        self.api = api_from_run_config(run_config)
        self.generator = CandidateGenerator()
        self.results: list[ExperimentResult] = []
        self.report = ExperimentReport()

    # ── Step 1: Generate ─────────────────────────────────────────────────

    def generate_candidates(self) -> list[ExperimentResult]:
        """Generate N Alpha candidates using the existing pipeline generator."""
        print(f"\n{'='*60}")
        print(f"  Step 1: Generating {self.candidate_count} candidates")
        print(f"{'='*60}")

        ops = self.run_config.ops
        budget_max = ops.budget.max_candidates_per_cycle

        # Wire up generator — use HypothesisDrivenGenerator with fixed template resolution
        from brain_alpha_ops.data import OfficialDataLoader, FieldDatasetMapper
        from brain_alpha_ops.research.theme_engine import DynamicThemeEngine
        from brain_alpha_ops.research.dataset_selector import DatasetSelector
        from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary

        try:
            loader = OfficialDataLoader.instance()

            fields_list = [
                {"name": f.id, "category": f.category, "delay": f.delay, "coverage": f.coverage}
                for f in loader.get_fields()
            ]
            operators_list = [
                {"name": op.name, "category": op.category, "definition": op.definition, "description": op.description}
                for op in loader.get_operators()
            ]

            mapper = FieldDatasetMapper()
            mapper.build(loader)
            theme = DynamicThemeEngine(loader)
            theme.build_categories()
            selector = DatasetSelector()
            selector.initialize(loader)

            # Select dataset
            ds_ids = selector.select(ops.budget.dataset_strategy)
            if ds_ids:
                ops.settings.dataset = ds_ids[0]

            # Use BOTH generators for comparison
            # Primary: HypothesisDrivenGenerator (with fixed template resolution)
            from brain_alpha_ops.research.hypothesis_driven_generator import HypothesisDrivenGenerator
            hypothesis_dir = getattr(ops.budget, 'hypothesis_library_dir',
                                     'brain_alpha_ops/research/hypotheses')
            library = HypothesisLibrary(hypothesis_dir).load_all()
            ratio = getattr(ops.budget, 'generation_mode_ratio', '70/20/10')
            self.generator = HypothesisDrivenGenerator(
                loader=loader, mapper=mapper, theme_engine=theme,
                selector=selector, library=library, ratio_str=ratio,
            )
            self.generator.update_context(fields_list, operators_list)
            if ds_ids:
                self.generator.set_dataset(ds_ids[0])

            print(f"  Generator: HypothesisDrivenGenerator (70/20/10)")
            print(f"  Loaded: {len(fields_list)} fields, {len(operators_list)} operators, "
                  f"{len(selector.available_datasets)} datasets")
        except Exception as exc:
            print(f"  ERROR: Could not load generator components: {exc}")
            return []

        rounds = (self.candidate_count + budget_max - 1) // budget_max

        candidates: list[ExperimentResult] = []
        for r in range(rounds):
            batch_size = min(budget_max, self.candidate_count - len(candidates))
            generated = self.generator.generate(batch_size, dataset_id=ops.settings.dataset or "")
            for i, c in enumerate(generated):
                result = ExperimentResult(
                    index=len(candidates) + 1,
                    expression=c.expression or "",
                    fields=extract_fields(c.expression),
                    operators=extract_operators(c.expression),
                    family=c.family or "",
                    dataset_id=c.dataset_id or ops.settings.dataset or "",
                    prior_score=0.0,
                    local_quality=float(local_quality(c, 0.0).get("score", 0.0)),
                    local_rank=0.0,
                )
                # Calculate prior score (without official metrics)
                scorecard = build_scorecard(c, ops.thresholds)
                result.prior_score = scorecard.get("prior_score", 0.0)
                result.local_rank = 0.65 * result.prior_score + 0.35 * result.local_quality
                candidates.append(result)

            print(f"  Round {r+1}/{rounds}: generated {len(generated)} candidates "
                  f"(total: {len(candidates)}/{self.candidate_count})")
            if r == 0 and generated:
                # Show sample expressions for debugging
                for j, gc in enumerate(generated[:3]):
                    expr_preview = (gc.expression or "")[:100]
                    print(f"    Sample {j+1}: {expr_preview}...")

        self.results = candidates
        self.report.total_generated = len(candidates)
        print(f"\n  [OK] Generated {len(candidates)} candidates")
        return candidates

    # ── Step 2: Official BRAIN Simulation ────────────────────────────────

    def simulate_all(self) -> None:
        """Submit each candidate for official BRAIN simulation and collect results."""
        print(f"\n{'='*60}")
        print(f"  Step 2: BRAIN Official Simulation ({len(self.results)} candidates)")
        print(f"{'='*60}")

        self.api.authenticate()

        # Build settings for simulation — use raw BrainSettings dict (has pasteurization)
        # build_simulation_payload will convert to API format
        from dataclasses import asdict
        brain_settings = asdict(self.run_config.ops.settings)

        # Skip local validation — submit all expressions directly to BRAIN
        valid_indices = list(range(len(self.results)))
        for result in self.results:
            result.simulation_status = "pre_submit"

        valid_count = len(valid_indices)
        print(f"\n  Submitting {valid_count} simulations (1 at a time to avoid 429)...")
        simulation_map: dict[int, str] = {}  # index -> simulation_id

        batch_size = 1  # avoid CONCURRENT_SIMULATION_LIMIT_EXCEEDED
        for batch_start in range(0, valid_count, batch_size):
            batch_end = min(batch_start + batch_size, valid_count)
            batch_indices = valid_indices[batch_start:batch_end]

            # Submit batch (with retry on 429)
            for idx in batch_indices:
                result = self.results[idx]
                for retry in range(3):
                    try:
                        sim_id = self.api.submit_simulation(result.expression, brain_settings)
                        simulation_map[idx] = sim_id
                        result.simulation_status = "submitted"
                        print(f"    Submitted #{result.index}: {sim_id[:60]}...")
                        break
                    except Exception as exc:
                        if '429' in str(exc) and retry < 2:
                            import time
                            wait = (retry + 1) * 15
                            print(f"    ⏳ #{result.index} 429 - waiting {wait}s (retry {retry+1}/3)...")
                            time.sleep(wait)
                        else:
                            result.simulation_status = "error"
                            result.simulation_error = f"submit_simulation: {type(exc).__name__}: {exc}"
                            print(f"    FAIL #{result.index}: {result.simulation_error[:100]}")
                            break

            # Poll batch — use built-in poll_until_complete for reliability
            pending = set(batch_indices)
            for idx in list(pending):
                sim_id = simulation_map.get(idx)
                if not sim_id:
                    pending.discard(idx)
                    continue
                try:
                    final_status = self.api.poll_until_complete(sim_id)
                    if final_status == "COMPLETED":
                        metrics_data = self.api.fetch_result(sim_id)
                        self._record_simulation_result(idx, metrics_data)
                        print(f"    [OK] #{self.results[idx].index} COMPLETED")
                    else:
                        # FAILED or TIMEOUT — try to fetch error details from BRAIN
                        self.results[idx].simulation_status = "failed"
                        self.results[idx].simulation_error = f"BRAIN returned {final_status}"
                        try:
                            # Even on FAILED, fetch_result may return error info
                            result = self.api.fetch_result(sim_id)
                            raw = result.get("raw", result)
                            self.results[idx].brain_failure_detail = str(raw)[:400]
                        except Exception:
                            self.results[idx].brain_failure_detail = f"(could not fetch details: {final_status})"
                        detail_preview = self.results[idx].brain_failure_detail[:120]
                        print(f"    [X] #{self.results[idx].index} {final_status}: {detail_preview}")
                    pending.discard(idx)
                except Exception as exc:
                    self.results[idx].simulation_status = "error"
                    self.results[idx].simulation_error = f"poll: {type(exc).__name__}: {exc}"
                    pending.discard(idx)
                    print(f"    [X] #{self.results[idx].index} poll error: {type(exc).__name__}: {exc}")

            done_count = sum(1 for r in self.results if r.simulation_status in ("completed", "failed", "error"))
            print(f"  Batch {batch_start//batch_size+1}: {sum(1 for r in self.results if r.simulation_status == 'completed')} completed, "
                  f"{done_count}/{valid_count} total done")

        self.report.total_simulated = valid_count
        self.report.total_completed = sum(1 for r in self.results if r.simulation_status == "completed")
        self.report.total_failed = sum(1 for r in self.results if r.simulation_status in ("failed", "error"))
        print(f"\n  [OK] Simulation complete: {self.report.total_completed} completed, "
              f"{self.report.total_failed} failed/error")

    def _record_simulation_result(self, idx: int, metrics_data: dict) -> None:
        """Extract BRAIN metrics from simulation result and update experiment record."""
        result = self.results[idx]
        result.simulation_status = "completed"

        # Extract metrics from normalized fetch_result response
        metrics = metrics_data.get("metrics") or {}
        result.official_alpha_id = str(metrics.get("official_alpha_id") or "")

        # Extract key BRAIN metrics
        result.sharpe = _safe_float(metrics.get("sharpe"))
        result.fitness = _safe_float(metrics.get("fitness"))
        result.turnover = _safe_float(metrics.get("turnover"))
        result.turnover_raw = _safe_float(metrics.get("turnover_raw", metrics.get("turnover", 0)))
        result.returns = _safe_float(metrics.get("returns"))
        result.drawdown = _safe_float(metrics.get("drawdown"))
        result.margin = _safe_float(metrics.get("margin"))
        result.self_correlation = _safe_float(metrics.get("self_correlation"))
        result.weight_concentration = _safe_float(metrics.get("weight_concentration"))
        result.sub_universe_sharpe = _safe_float(metrics.get("sub_universe_sharpe"))
        result.is_booksize_ratio = _safe_float(metrics.get("is_booksize_ratio"))

        # Extract pass_fail
        result.brain_pass_fail = str(metrics.get("pass_fail") or "unknown").upper()

        # Extract IC metrics
        result.ic_mean = _safe_float(metrics.get("ic_mean"))
        result.ic_ir = _safe_float(metrics.get("ic_ir"))

    # ── Step 3: Evaluate Scoring System ──────────────────────────────────

    def evaluate_scoring(self) -> None:
        """Re-score all candidates using the internal scoring system with real metrics."""
        print(f"\n{'='*60}")
        print(f"  Step 3: Evaluating Internal Scoring System")
        print(f"{'='*60}")

        ops = self.run_config.ops
        for result in self.results:
            if result.simulation_status != "completed":
                continue

            # Build a Candidate object for the scoring system
            candidate = Candidate(
                alpha_id=result.official_alpha_id or f"exp_{result.index}",
                expression=result.expression,
                hypothesis=f"Experiment #{result.index}",
                family=result.family,
                dataset_id=result.dataset_id,
                official_alpha_id=result.official_alpha_id,
                official_metrics=_metrics_to_dict(result),
            )

            # Full scorecard
            scorecard = build_scorecard(candidate, ops.thresholds)
            result.empirical_score = scorecard.get("empirical_score", 0.0)
            result.checklist_score = scorecard.get("checklist_score", 0.0)
            result.total_score = scorecard.get("total_score", 0.0)
            result.decision_band = scorecard.get("decision_band", "")

            # Quality gate
            gate = evaluate_quality_gate(candidate, ops.thresholds)
            result.gate_status = gate.get("status", "")
            result.gate_failed_reasons = gate.get("failed_reasons", [])

            # BRAIN check (if official_alpha_id available)
            if result.official_alpha_id:
                try:
                    check = self.api.check_alpha(result.official_alpha_id)
                    result.brain_check_passed = check.get("status") == "PASSED"
                    result.brain_is_submittable = check.get("status") == "PASSED"
                    result.brain_errors = check.get("failures") or check.get("errors") or []
                except Exception as exc:
                    result.brain_errors.append(str(exc))

        self.report.total_passed_brain = sum(1 for r in self.results if r.brain_pass_fail == "PASS")
        self.report.total_submittable = sum(1 for r in self.results if r.brain_is_submittable)
        print(f"  BRAIN PASS: {self.report.total_passed_brain}/{self.report.total_completed}")
        print(f"  BRAIN Submittable: {self.report.total_submittable}/{self.report.total_completed}")

    # ── Step 4: Analyze ──────────────────────────────────────────────────

    def analyze(self) -> ExperimentReport:
        """Run statistical analysis on experiment results."""
        print(f"\n{'='*60}")
        print(f"  Step 4: Analysis")
        print(f"{'='*60}")

        completed = [r for r in self.results if r.simulation_status == "completed"]
        if not completed:
            print("  [WARN] No completed simulations to analyze")
            return self.report

        # Sharpe distribution
        sharpes = [r.sharpe for r in completed if r.sharpe is not None]
        self.report.sharpe_distribution = sorted(sharpes)
        print(f"  Sharpe: min={min(sharpes):.3f}, max={max(sharpes):.3f}, "
              f"mean={sum(sharpes)/len(sharpes):.3f}, "
              f"≥1.25: {sum(1 for s in sharpes if s >= 1.25)}/{len(sharpes)}")

        # Fitness distribution
        fitnesses = [r.fitness for r in completed if r.fitness is not None]
        self.report.fitness_distribution = sorted(fitnesses)
        if fitnesses:
            print(f"  Fitness: min={min(fitnesses):.3f}, max={max(fitnesses):.3f}, "
                  f"mean={sum(fitnesses)/len(fitnesses):.3f}, "
                  f"≥1.0: {sum(1 for f in fitnesses if f >= 1.0)}/{len(fitnesses)}")

        # Turnover distribution
        turnovers = [r.turnover for r in completed if r.turnover is not None]
        self.report.turnover_distribution = sorted(turnovers)
        if turnovers:
            print(f"  Turnover: min={min(turnovers):.3f}, max={max(turnovers):.3f}, "
                  f"mean={sum(turnovers)/len(turnovers):.3f}, "
                  f"≤0.30: {sum(1 for t in turnovers if t <= 0.30)}/{len(turnovers)}, "
                  f"≤0.70: {sum(1 for t in turnovers if t <= 0.70)}/{len(turnovers)}")

        # Prior score vs actual Sharpe correlation
        prior_sharpe_pairs = [(r.prior_score, r.sharpe) for r in completed if r.sharpe is not None]
        if len(prior_sharpe_pairs) >= 10:
            self.report.prior_score_vs_sharpe_corr = _pearson_r(
                [p[0] for p in prior_sharpe_pairs],
                [p[1] for p in prior_sharpe_pairs],
            )
            print(f"  Prior Score vs Sharpe correlation: {self.report.prior_score_vs_sharpe_corr:.4f}")

        # Total score vs BRAIN pass rate by score band
        bands: dict[str, list[bool]] = {"≥85": [], "70-84": [], "50-69": [], "<50": []}
        for r in completed:
            if r.total_score >= 85:
                bands["≥85"].append(r.brain_pass_fail == "PASS")
            elif r.total_score >= 70:
                bands["70-84"].append(r.brain_pass_fail == "PASS")
            elif r.total_score >= 50:
                bands["50-69"].append(r.brain_pass_fail == "PASS")
            else:
                bands["<50"].append(r.brain_pass_fail == "PASS")
        self.report.total_score_vs_pass_rate = {
            band: sum(passes) / max(len(passes), 1)
            for band, passes in bands.items() if passes
        }
        for band, rate in self.report.total_score_vs_pass_rate.items():
            count = len(bands[band])
            print(f"  Score band {band}: {rate:.1%} BRAIN pass rate ({count} candidates)")

        # Field / operator usage
        field_counts: dict[str, int] = {}
        operator_counts: dict[str, int] = {}
        skeleton_counts: dict[str, int] = {}
        for r in self.results:
            for f in r.fields:
                field_counts[f] = field_counts.get(f, 0) + 1
            for o in r.operators:
                operator_counts[o] = operator_counts.get(o, 0) + 1
            skeleton_counts[r.family] = skeleton_counts.get(r.family, 0) + 1

        self.report.top_fields = sorted(field_counts.items(), key=lambda x: -x[1])[:20]
        self.report.top_operators = sorted(operator_counts.items(), key=lambda x: -x[1])[:20]
        self.report.skeleton_distribution = skeleton_counts

        print(f"  Top fields: {self.report.top_fields[:5]}")
        print(f"  Top operators: {self.report.top_operators[:5]}")
        print(f"  Skeleton distribution: {skeleton_counts}")

        # Correlation rejection estimate (expression similarity)
        expressions = [r.expression for r in self.results if r.expression]
        from brain_alpha_ops.research.safety import similarity
        high_sim = 0
        for i in range(len(expressions)):
            for j in range(i + 1, len(expressions)):
                sim = similarity(expressions[i], expressions[j])
                if sim >= 0.90:
                    high_sim += 1
                    break
        self.report.expression_correlation_blocked = high_sim
        self.report.expression_correlation_block_rate = high_sim / max(len(self.results), 1)
        print(f"  Expression similarity ≥0.90: {high_sim}/{len(self.results)} "
              f"({self.report.expression_correlation_block_rate:.1%})")

        self.report.results = [dataclasses.asdict(r) for r in self.results]
        return self.report

    # ── Orchestrator ─────────────────────────────────────────────────────

    def run(self) -> ExperimentReport:
        """Run the full experiment pipeline."""
        print(f"\n{'#'*60}")
        print(f"  BRAIN Alpha Scoring Validation Experiment")
        print(f"  Candidates: {self.candidate_count}")
        print(f"  Started: {datetime.now(timezone.utc).isoformat()}")
        print(f"{'#'*60}")

        t0 = time.time()

        self.generate_candidates()
        t1 = time.time()
        print(f"\n  [Generate] {t1-t0:.1f}s")

        self.simulate_all()
        t2 = time.time()
        print(f"\n  [Simulate] {t2-t1:.1f}s")

        self.evaluate_scoring()
        t3 = time.time()
        print(f"\n  [Evaluate] {t3-t2:.1f}s")

        report = self.analyze()
        t4 = time.time()
        print(f"\n  [Analyze] {t4-t3:.1f}s")
        print(f"\n  Total: {t4-t0:.1f}s")

        return report


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metrics_to_dict(result: ExperimentResult) -> dict:
    """Convert experiment result metrics to BRAIN metrics dict for scoring."""
    return {
        "sharpe": result.sharpe,
        "fitness": result.fitness,
        "turnover": result.turnover,
        "turnover_raw": result.turnover_raw,
        "returns": result.returns,
        "drawdown": result.drawdown,
        "margin": result.margin,
        "self_correlation": result.self_correlation,
        "weight_concentration": result.weight_concentration,
        "sub_universe_sharpe": result.sub_universe_sharpe,
        "is_booksize_ratio": result.is_booksize_ratio,
    }


def _pearson_r(xs: list[float], ys: list[float]) -> float:
    """Compute Pearson correlation coefficient."""
    n = len(xs)
    if n < 3:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    std_x = (sum((x - mean_x) ** 2 for x in xs)) ** 0.5
    std_y = (sum((y - mean_y) ** 2 for y in ys)) ** 0.5
    if std_x == 0 or std_y == 0:
        return 0.0
    return cov / (std_x * std_y)


# ═══════════════════════════════════════════════════════════════════════════
# Report Generation
# ═══════════════════════════════════════════════════════════════════════════

def generate_report(report: ExperimentReport, output_dir: Path) -> None:
    """Generate JSON and Markdown reports from experiment data."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON report (raw data) — use asdict for proper serialization
    import dataclasses
    json_path = output_dir / "validation_report.json"
    json_path.write_text(
        json.dumps(dataclasses.asdict(report), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n  JSON report: {json_path}")

    # Markdown report
    md_path = output_dir / "validation_report.md"
    lines = _build_markdown_report(report)
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Markdown report: {md_path}")


def _build_markdown_report(report: ExperimentReport) -> list[str]:
    """Build a human-readable Markdown report."""
    lines = []
    lines.append("# BRAIN Alpha 评分系统验证报告")
    lines.append("")
    lines.append(f"> 生成时间: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"> 候选数量: {report.total_generated}")
    lines.append(f"> 模拟完成: {report.total_completed}")
    lines.append(f"> 模拟失败: {report.total_failed}")
    lines.append("")

    # ── Executive Summary ──
    lines.append("## 执行摘要")
    lines.append("")
    if report.total_completed == 0:
        lines.append("**[WARN] 无有效模拟结果。无法评估系统产出质量。**")
        lines.append("")
        lines.append("可能原因：")
        lines.append("- BRAIN API 认证失败")
        lines.append("- 表达式验证失败（字段/算子无效）")
        lines.append("- 模拟配额耗尽")
        lines.append("- 网络/超时问题")
        return lines

    pass_rate = report.total_passed_brain / max(report.total_completed, 1)
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| BRAIN PASS 通过率 | {report.total_passed_brain}/{report.total_completed} ({pass_rate:.1%}) |")
    lines.append(f"| BRAIN Submittable | {report.total_submittable}/{report.total_completed} |")

    if report.sharpe_distribution:
        lines.append(f"| Sharpe 均值 | {sum(report.sharpe_distribution)/len(report.sharpe_distribution):.3f} |")
        lines.append(f"| Sharpe ≥ 1.25 | {sum(1 for s in report.sharpe_distribution if s >= 1.25)}/{len(report.sharpe_distribution)} |")

    if report.fitness_distribution:
        lines.append(f"| Fitness 均值 | {sum(report.fitness_distribution)/len(report.fitness_distribution):.3f} |")
        lines.append(f"| Fitness ≥ 1.0 | {sum(1 for f in report.fitness_distribution if f >= 1.0)}/{len(report.fitness_distribution)} |")

    if report.turnover_distribution:
        lines.append(f"| Turnover ≤ 0.30 | {sum(1 for t in report.turnover_distribution if t <= 0.30)}/{len(report.turnover_distribution)} |")
        lines.append(f"| Turnover ≤ 0.70 | {sum(1 for t in report.turnover_distribution if t <= 0.70)}/{len(report.turnover_distribution)} |")

    lines.append("")
    core = f"**核心判断**: "
    if pass_rate >= 0.3:
        core += f"系统能够产出 BRAIN 接受的 Alpha（{pass_rate:.0%} 通过率），值得继续投入。"
    elif pass_rate >= 0.1:
        core += f"系统产出 Alpha 有一定通过率（{pass_rate:.0%}），但效率偏低，需要优化生成策略。"
    else:
        core += f"系统产出 Alpha 通过率极低（{pass_rate:.0%}），**生成架构或评分体系可能需要根本性重新思考。**"
    lines.append(core)
    lines.append("")

    # ── Scoring Calibration ──
    lines.append("## 评分系统校准")
    lines.append("")
    if report.prior_score_vs_sharpe_corr is not None:
        lines.append(f"- **prior_score 与 实际 Sharpe 的 Pearson 相关系数**: {report.prior_score_vs_sharpe_corr:.4f}")
        if abs(report.prior_score_vs_sharpe_corr) < 0.2:
            lines.append("  - [WARN] **极弱相关** — prior_score 几乎无法预测实际 Sharpe，需要重新设计先验维度。")
        elif abs(report.prior_score_vs_sharpe_corr) < 0.5:
            lines.append("  - [WARN] **弱到中等相关** — prior_score 有一定预测力但有限。")
        else:
            lines.append("  - [PASS] **中等以上相关** — prior_score 具有有意义的预测能力。")
        lines.append("")

    if report.total_score_vs_pass_rate:
        lines.append("### 评分分带 vs BRAIN 通过率")
        lines.append("")
        lines.append("| 评分带 | 候选数 | BRAIN 通过率 | 判定 |")
        lines.append("|--------|--------|-------------|------|")
        for band in ["≥85", "70-84", "50-69", "<50"]:
            rate = report.total_score_vs_pass_rate.get(band)
            if rate is not None:
                actual_rate = report.total_score_vs_pass_rate[band]
                verdict = "[PASS] 准确" if (band == "≥85" and actual_rate >= 0.5) or (band == "<50" and actual_rate < 0.2) else "[WARN] 需校准"
                lines.append(f"| {band} | — | {actual_rate:.1%} | {verdict} |")
        lines.append("")

    # ── Correlation Blocking ──
    lines.append("## 表达式相关性分析")
    lines.append("")
    lines.append(f"- 表达式相似度 ≥ 0.90: {report.expression_correlation_blocked}/{report.total_generated} ({report.expression_correlation_block_rate:.1%})")
    if report.expression_correlation_block_rate > 0.5:
        lines.append("  - [WARN] **75%+ 可能被云端 correlation 阻断** — 生成策略产生了大量趋同表达式。")
        lines.append("  - 建议: 增加骨架多样性、放宽字段选择范围、引入字段组合去重。")
    lines.append("")

    # ── Field / Operator Diversity ──
    lines.append("## 字段与算子使用分布")
    lines.append("")
    lines.append(f"- 唯一字段数: {len(report.top_fields)}")
    lines.append(f"- 唯一算子数: {len(report.top_operators)}")
    lines.append(f"- 骨架分布: {report.skeleton_distribution}")
    lines.append("")

    # ── Recommendations ──
    lines.append("## 建议")
    lines.append("")
    lines.append("基于实验结果：")
    lines.append("")
    lines.append("1. ")
    if pass_rate < 0.1:
        lines.append("**根本性架构重新思考** — 当前生成策略产出质量不足以证明系统价值。考虑：")
        lines.append("   - 限制生成范围到特定已知有效的因子类型")
        lines.append("   - 引入人工筛选步骤")
        lines.append("   - 使用 BRAIN 平台上已有的成功 Alpha 作为模板")
    elif pass_rate < 0.3:
        lines.append("**优化生成策略** — 系统有一定产出能力但效率需提升：")
        lines.append("   - 增加字段池到 200+")
        lines.append("   - 启用 PROD_CORRELATION API 预检")
        lines.append("   - 优化骨架多样性策略")
    else:
        lines.append("**继续投入工程优化** — 系统产出质量可接受：")
        lines.append("   - 修复安全漏洞和前端闭环")
        lines.append("   - 持续校准评分参数")
        lines.append("   - 扩大生产规模")

    lines.append(f"2. prior_score 预测效度: {'可接受' if report.prior_score_vs_sharpe_corr and abs(report.prior_score_vs_sharpe_corr) >= 0.3 else '需重新设计'}")
    lines.append(f"3. 表达式多样性: {'可接受' if report.expression_correlation_block_rate < 0.5 else '需改善'}")

    lines.append("")
    lines.append("---")
    lines.append(f"*报告结束。原始数据见 `validation_report.json`*")
    return lines


# ═══════════════════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════════════════

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="BRAIN Alpha Scoring Validation Experiment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python experiments/validate_scoring.py --candidates 50
  python experiments/validate_scoring.py --candidates 20 --config config/run_config.json
  python experiments/validate_scoring.py --candidates 100 --dataset model77

Environment:
  BRAIN_USERNAME    WorldQuant BRAIN account email
  BRAIN_PASSWORD    WorldQuant BRAIN account password
        """,
    )
    parser.add_argument("--candidates", type=int, default=50, help="Number of Alpha candidates to generate (default: 50)")
    parser.add_argument("--config", type=str, default="", help="Path to run_config.json (default: config/run_config.json)")
    parser.add_argument("--dataset", type=str, default="", help="Specific dataset ID (default: auto-rotate from config)")
    parser.add_argument("--output", type=str, default="experiments", help="Output directory for reports (default: experiments/)")
    args = parser.parse_args(argv)

    # Load config
    config_path = args.config or None
    run_config = load_run_config(config_path)

    # Override dataset if specified
    if args.dataset:
        run_config.ops.settings.dataset = args.dataset
        run_config.ops.budget.dataset_strategy = "specific"

    # Safety: force auto_submit=False
    run_config.auto_submit = False
    # Safety: limit cycles
    run_config.ops.budget.run_forever = False
    run_config.ops.budget.max_cycles = 1

    # Run experiment
    validator = ScoringValidator(run_config, candidate_count=args.candidates)
    try:
        report = validator.run()
    except Exception as exc:
        print(f"\n[FAIL] Experiment failed: {exc}")
        import traceback
        traceback.print_exc()
        return 1

    # Generate reports
    output_dir = Path(args.output)
    generate_report(report, output_dir)

    print(f"\n{'#'*60}")
    print(f"  Experiment Complete")
    print(f"  Reports: {output_dir.absolute()}")
    print(f"{'#'*60}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

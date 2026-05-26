from brain_alpha_ops.research.parallel_backtest import ParallelBacktestExecutor, ParallelBacktestPlanner


def test_parallel_backtest_planner_caps_jobs_by_account_budget():
    plan = ParallelBacktestPlanner().plan(
        ["rank(close)", "rank(volume)", "rank(close)"],
        markets=["USA", "EUR"],
        max_workers=8,
        max_batches=1,
        per_account_limit=3,
    )

    assert plan["ok"] is True
    assert plan["requested_jobs"] == 4
    assert plan["selected_jobs"] == 3
    assert plan["skipped_jobs"] == 1
    assert plan["rate_limit"]["max_workers"] == 3
    assert plan["account_safety"]["capacity_limited"] is True
    assert plan["batches"][0]["job_count"] == 3


def test_parallel_backtest_executor_accounts_for_job_failures():
    def runner(job):
        if job["market"] == "EUR":
            return {"ok": False, "error_code": "SIM_FAILED", "status": "FAILED"}
        return {"ok": True, "simulation_id": f"sim_{job['job_index']}", "status": "COMPLETED"}

    result = ParallelBacktestExecutor().execute(
        ["rank(close)"],
        markets=["USA", "EUR"],
        max_workers=2,
        max_batches=1,
        per_account_limit=5,
        runner=runner,
    )

    assert result["ok"] is False
    assert result["selected_jobs"] == 2
    assert result["submitted_count"] == 1
    assert result["completed_count"] == 1
    assert result["failed_count"] == 1
    assert result["results"][1]["error_code"] == "SIM_FAILED"

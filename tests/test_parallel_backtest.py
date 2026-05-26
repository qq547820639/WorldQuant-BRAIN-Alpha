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
    assert plan["duplicate_expressions"] == ["rank(close)"]
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
    assert result["failure_counts"]["SIM_FAILED"] == 1
    assert result["results"][1]["error_code"] == "SIM_FAILED"
    assert result["progress_events"][0]["event"] == "planned"


def test_parallel_backtest_executor_emits_progress_callback_and_terminal_failed_status():
    events = []

    def runner(_job):
        return {"ok": True, "simulation_id": "sim_failed", "status": "FAILED"}

    result = ParallelBacktestExecutor().execute(
        ["rank(close)"],
        markets=["USA"],
        max_workers=1,
        max_batches=1,
        per_account_limit=5,
        runner=runner,
        progress_callback=events.append,
    )

    assert result["ok"] is False
    assert result["failed_count"] == 1
    assert result["failure_counts"]["SIMULATION_FAILED"] == 1
    assert [event["event"] for event in events] == ["planned", "job_started", "job_finished", "completed"]


def test_parallel_backtest_planner_reports_empty_plan_safely():
    plan = ParallelBacktestPlanner().plan([], markets=["USA"])

    assert plan["ok"] is False
    assert plan["error_code"] == "EMPTY_PARALLEL_BACKTEST_PLAN"
    assert plan["jobs"] == []

from __future__ import annotations

from brain_alpha_ops.stall_monitor import StallMonitor, StallMonitorConfig
from brain_alpha_ops.web_jobs import job_delete, job_list, job_update


def test_stall_monitor_detects_list_backed_web_jobs_store():
    interrupts: list[str] = []
    jobs = [
        {
            "job_id": "job_list_1",
            "status": "running",
            "progress": {
                "phase": "simulation",
                "percent_complete": 10,
                "status_message": "waiting",
            },
        }
    ]
    monitor = StallMonitor(
        job_store_getter=lambda: jobs,
        config=StallMonitorConfig(stall_timeout_seconds=0, auto_interrupt=True),
        on_interrupt=interrupts.append,
    )

    monitor._check_all_jobs()
    monitor._check_all_jobs()

    assert interrupts == ["job_list_1"]


def test_stall_monitor_preserves_dict_store_compatibility():
    interrupts: list[str] = []
    jobs = {
        "job_dict_1": {
            "status": "running",
            "progress": {
                "phase": "generation",
                "percent_complete": 20,
                "status_message": "waiting",
            },
        }
    }
    monitor = StallMonitor(
        job_store_getter=lambda: jobs,
        config=StallMonitorConfig(stall_timeout_seconds=0, auto_interrupt=True),
        on_interrupt=interrupts.append,
    )

    monitor._check_all_jobs()
    monitor._check_all_jobs()

    assert interrupts == ["job_dict_1"]


def test_stall_monitor_reads_actual_web_jobs_job_list_rows():
    interrupts: list[str] = []
    job_id = "stall_monitor_web_job"
    job_update(job_id, status="running", progress={
        "phase": "candidate_generation",
        "percent_complete": 15,
        "status_message": "waiting",
    })
    try:
        monitor = StallMonitor(
            job_store_getter=lambda: job_list(limit=100),
            config=StallMonitorConfig(stall_timeout_seconds=0, auto_interrupt=True),
            on_interrupt=interrupts.append,
        )

        monitor._check_all_jobs()
        monitor._check_all_jobs()

        assert interrupts == [job_id]
    finally:
        job_delete(job_id)

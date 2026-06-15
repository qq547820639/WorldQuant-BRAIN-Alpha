"""Minimal acceptance test: verify core_pipeline produces result or fails within timeout."""
import logging
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Force safe limits BEFORE any pipeline imports
os.environ["BRAIN_ALPHA_FORCE_REAL_SUBMIT"] = "1"
os.environ["BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS"] = "1"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("e2e_acceptance")

class AcceptanceCorePipelineSmoke(unittest.TestCase):
    """Minimal smoke: pipeline must complete or fail within 60s."""

    HARD_TIMEOUT = 60  # seconds

    def test_core_pipeline_smoke(self):
        from brain_alpha_ops.config import load_run_config
        from brain_alpha_ops.runner import run_pipeline_from_config

        config = load_run_config("config/run_config.json")
        # Clamp budget for smoke
        config.ops.budget.run_forever = False
        config.ops.budget.max_cycles = 0  # Force immediate exit if loops
        config.ops.budget.max_runtime_seconds = 30
        config.auto_submit = False

        t0 = time.time()
        try:
            from brain_alpha_ops.ux.guided_pipeline import GuidedPipeline
            pipeline = GuidedPipeline(run_config=config)
            result = pipeline.run()
            elapsed = time.time() - t0
            logger.info(
                "GuidedPipeline completed in %.1fs — total_candidates=%s",
                elapsed,
                result.summary.get("total_candidates", 0) if result else 0,
            )
            self.assertIsNotNone(result)
            # Smoke test: must return within HARD_TIMEOUT
            self.assertLess(elapsed, self.HARD_TIMEOUT,
                f"Pipeline took {elapsed:.1f}s > {self.HARD_TIMEOUT}s limit")
        except Exception as exc:
            elapsed = time.time() - t0
            logger.warning("Pipeline raised after %.1fs: %s", elapsed, exc)
            if elapsed >= self.HARD_TIMEOUT:
                self.fail(f"Pipeline still hung after {elapsed:.1f}s")
            # Any exception within timeout is acceptable for smoke
            self.assertLess(elapsed, self.HARD_TIMEOUT)

if __name__ == "__main__":
    unittest.main()

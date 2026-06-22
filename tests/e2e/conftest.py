import pytest
import os

@pytest.fixture(scope="session")
def evidence_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("evidence")
    return str(d)

@pytest.fixture(scope="session")
def brain_runner(evidence_dir):
    from brain_alpha_ops.browser.brain_ui_runner import BrainBrowserRunner
    with BrainBrowserRunner(headless=True, evidence_dir=evidence_dir) as runner:
        yield runner

@pytest.fixture(scope="session")
def brain_credentials():
    return {
        "username": os.environ.get("BRAIN_USERNAME", ""),
        "password": os.environ.get("BRAIN_PASSWORD", ""),
    }

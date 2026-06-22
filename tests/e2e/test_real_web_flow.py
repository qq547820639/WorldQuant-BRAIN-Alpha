import pytest
import os

pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.browser, pytest.mark.live]

requires_brain = pytest.mark.skipif(
    os.environ.get("BRAIN_BROWSER_E2E_LIVE") != "1"
    or not os.environ.get("BRAIN_USERNAME")
    or not os.environ.get("BRAIN_PASSWORD"),
    reason="Requires BRAIN_BROWSER_E2E_LIVE=1 plus BRAIN credentials",
)

@pytest.mark.usefixtures("brain_runner", "brain_credentials")
@requires_brain
class TestRealBrainWebFlow:
    """Tests that exercise real BRAIN web interactions via Playwright."""
    
    def test_login(self, brain_runner, brain_credentials):
        """Verify real login via browser."""
        result = brain_runner.login(
            brain_credentials["username"],
            brain_credentials["password"],
        )
        assert result["ok"], f"Login failed: {result}"
    
    def test_alpha_creation_flow(self, brain_runner, brain_credentials):
        """Readonly alpha creation page evidence flow; real simulation is never triggered by default."""
        # Login
        login_result = brain_runner.login(
            brain_credentials["username"],
            brain_credentials["password"],
        )
        assert login_result["ok"]
        
        # Navigate to alpha creation
        nav_result = brain_runner.navigate_to_alpha_creation()
        assert nav_result["ok"]
        
        # Fill expression
        fill_result = brain_runner.fill_expression("rank(close)")
        assert fill_result["ok"]

        # Verify evidence collected
        evidence = brain_runner.get_evidence()
        assert len(evidence["screenshots"]) > 0
        assert evidence["transport"] == "browser"

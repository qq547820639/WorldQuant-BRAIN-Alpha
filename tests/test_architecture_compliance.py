"""Architecture compliance tests (v4.0 M5)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_architecture_no_dependency_violations():
    from scripts.check_architecture import check
    result = check()
    assert result["ok"], f"Architecture violations found: {result['violations']}"

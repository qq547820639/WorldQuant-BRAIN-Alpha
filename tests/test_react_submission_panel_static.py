from __future__ import annotations

from pathlib import Path

from _react_source_utils import resolve_react_source


ROOT = Path(__file__).resolve().parents[1]
TYPES = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "types"


def test_react_candidate_contract_includes_simulation_id():
    assert "simulation_id?: string;" in resolve_react_source(TYPES)

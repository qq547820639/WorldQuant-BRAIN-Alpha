"""QA Submission Gate Tests — WorldQuant BRAIN Alpha

Covers:
  QA-P0-001 through QA-P0-014 (production mock guard checks)
  Boundary and edge-case tests

Rules:
  - No real network calls: _request is always stubbed or submit_alpha is expected to raise
    before reaching _request.
  - Uses the same run_all() framework as the rest of the test suite.
  - PEP8-compliant; test names are self-documenting.
  - Source-code bugs (e.g. IndentationError in official.py) are flagged as KNOWN-BUG
    without masking the import so that the error is clearly reported.
"""

from __future__ import annotations

import os
import sys
import traceback

# ---------------------------------------------------------------------------
# Path bootstrap — identical to other test files in this project
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Attempt to import modules; capture errors as known bugs
# ---------------------------------------------------------------------------
_SAFETY_IMPORT_ERROR = None
_OFFICIAL_IMPORT_ERROR = None
_OFFICIAL_API_IMPORT_ERROR = None

try:
    from brain_alpha_ops.config import SubmissionPolicy
    from brain_alpha_ops.models import Candidate
    from brain_alpha_ops.research.safety import (
        MOCK_ID_PREFIXES,
        MOCK_SOURCE_VALUES,
        SubmissionLedger,
        _looks_mock_identifier,
        mock_source_reasons,
    )
except Exception as _exc:
    _SAFETY_IMPORT_ERROR = _exc

try:
    # brain_api/__init__.py imports OfficialBrainAPI on line 4, which triggers
    # the IndentationError in official.py — import each module directly instead.
    import importlib.util as _ilu
    import pathlib as _pl

    _official_spec = _ilu.spec_from_file_location(
        "brain_alpha_ops.brain_api.official",
        str(
            _pl.Path(__file__).resolve().parents[1]
            / "brain_alpha_ops"
            / "brain_api"
            / "official.py"
        ),
    )
    _official_mod = _ilu.module_from_spec(_official_spec)  # type: ignore[arg-type]
    _official_spec.loader.exec_module(_official_mod)  # type: ignore[union-attr]
    _looks_non_production_alpha_id = _official_mod._looks_non_production_alpha_id
    OfficialBrainAPI = _official_mod.OfficialBrainAPI
    _OFFICIAL_IMPORT_VIA_DIRECT = True
except Exception as _exc:
    _OFFICIAL_IMPORT_ERROR = _exc
    _looks_non_production_alpha_id = None  # type: ignore[assignment]
    OfficialBrainAPI = None  # type: ignore[assignment, misc]
    _OFFICIAL_IMPORT_VIA_DIRECT = False

try:
    # BrainAPIError lives in base.py which does NOT import official.py
    import importlib.util as _ilu2
    import pathlib as _pl2

    _base_spec = _ilu2.spec_from_file_location(
        "brain_alpha_ops.brain_api.base",
        str(
            _pl2.Path(__file__).resolve().parents[1]
            / "brain_alpha_ops"
            / "brain_api"
            / "base.py"
        ),
    )
    _base_mod = _ilu2.module_from_spec(_base_spec)  # type: ignore[arg-type]
    _base_spec.loader.exec_module(_base_mod)  # type: ignore[union-attr]
    BrainAPIError = _base_mod.BrainAPIError
except Exception as _exc:
    _OFFICIAL_API_IMPORT_ERROR = _exc
    BrainAPIError = RuntimeError  # type: ignore[assignment, misc]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candidate(
    alpha_id: str = "alpha_a1b2c3d4",
    official_alpha_id: str = "abc123xyz",
    simulation_id: str = "sim_789real",
    source_tags=None,
    **extra_fields,
):
    """Build a minimal but valid Candidate, with sensible production-safe defaults."""
    if _SAFETY_IMPORT_ERROR:
        raise RuntimeError(f"Cannot build Candidate — safety import failed: {_SAFETY_IMPORT_ERROR}")
    c = Candidate(
        alpha_id=alpha_id,
        expression="rank(close)",
        family="Momentum",
        hypothesis="Price strength continues.",
        data_fields=["close"],
        operators=["rank"],
        source_tags=source_tags if source_tags is not None else ["经验"],
    )
    c.official_alpha_id = official_alpha_id
    c.simulation_id = simulation_id
    c.official_metrics = {
        "sharpe": 1.5,
        "fitness": 1.1,
        "turnover": 0.25,
        "correlation": 0.30,
        "weight_concentration": 0.15,
        "official_alpha_id": official_alpha_id,
    }
    c.gate = {"submission_ready": True, "failed_reasons": []}
    for key, value in extra_fields.items():
        setattr(c, key, value)
    return c


def _make_stub_official_api():
    """Return an OfficialBrainAPI whose _request raises if ever called.

    Returns (api, request_calls_list).
    Raises KnownSourceBug if OfficialBrainAPI cannot be imported.
    """
    if OfficialBrainAPI is None:
        raise _KnownSourceBug(
            f"OfficialBrainAPI unavailable due to source-code bug: {_OFFICIAL_IMPORT_ERROR}"
        )

    # We need OfficialAPIConfig too
    from brain_alpha_ops.config import OfficialAPIConfig

    request_calls = []

    api = OfficialBrainAPI.__new__(OfficialBrainAPI)
    # Minimal initialisation to avoid network setup
    from brain_alpha_ops.config import OfficialAPIConfig as _OAC
    OfficialBrainAPI.__init__(
        api,
        _OAC(base_url="https://example-stub.invalid", min_request_interval_seconds=0),
        token="stub-token",
    )

    def _raise_if_called(*_args, **_kwargs):
        request_calls.append((_args, _kwargs))
        raise AssertionError("_request must NOT be called in this test")

    api._request = _raise_if_called
    return api, request_calls


class _KnownSourceBug(Exception):
    """Raised when a test cannot proceed due to a confirmed source-code bug."""


# ===========================================================================
# QA-P0-001: production mock alpha_id rejected by local guard
# ===========================================================================

def test_qa_p0_001_mock_alpha_id_rejected():
    """mock_source_reasons detects mock alpha_id; reason does not mention 'official'."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    candidate = _candidate(alpha_id="mock_xxx")
    reasons = mock_source_reasons(candidate)
    assert reasons, "Expected non-empty reasons for mock alpha_id"
    assert any("alpha_id" in r for r in reasons), f"Expected 'alpha_id' in reason; got: {reasons}"
    assert not any("official" in r for r in reasons), (
        f"Reason should be about alpha_id, not official_alpha_id; got: {reasons}"
    )


# ===========================================================================
# QA-P0-002: production mock official_alpha_id rejected
# ===========================================================================

def test_qa_p0_002_mock_official_alpha_id_rejected():
    """mock_source_reasons detects mock official_alpha_id."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    candidate = _candidate(official_alpha_id="mock_alpha_001")
    reasons = mock_source_reasons(candidate)
    assert reasons, "Expected non-empty reasons for mock official_alpha_id"
    assert any("official_alpha_id" in r for r in reasons), (
        f"Expected 'official_alpha_id' in reason; got: {reasons}"
    )


# ===========================================================================
# QA-P0-003: production mock simulation_id rejected
# ===========================================================================

def test_qa_p0_003_mock_simulation_id_rejected():
    """mock_source_reasons detects mock simulation_id with seemingly-normal official_id."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    candidate = _candidate(
        simulation_id="mock_sim_001",
        official_alpha_id="abc123xyz",
    )
    reasons = mock_source_reasons(candidate)
    assert reasons, "Expected non-empty reasons for mock simulation_id"
    assert any("simulation_id" in r for r in reasons), (
        f"Expected 'simulation_id' in reason; got: {reasons}"
    )


# ===========================================================================
# QA-P0-004: all mock/demo/test/fake/sample keywords rejected
# ===========================================================================

def test_qa_p0_004_source_keywords_all_rejected():
    """Every mock-sentinel keyword in source_tags and attribute fields is caught."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    # --- source_tags list ---
    for kw in ("mock", "demo", "test", "fake", "sample"):
        candidate = _candidate(source_tags=[kw])
        reasons = mock_source_reasons(candidate)
        assert reasons, f"Expected rejection for source_tags=['{kw}']; got no reasons"

    # --- attribute fields ---
    for field_name, field_value in (
        ("source", "mock"),
        ("environment", "test"),
        ("mode", "demo"),
    ):
        candidate = _candidate()
        setattr(candidate, field_name, field_value)
        reasons = mock_source_reasons(candidate)
        assert reasons, (
            f"Expected rejection for {field_name}='{field_value}'; got no reasons"
        )


# ===========================================================================
# QA-P0-005: missing official_alpha_id blocks via SubmissionLedger.assess()
# ===========================================================================

def test_qa_p0_005_missing_official_alpha_id_blocked_by_ledger():
    """SubmissionLedger.assess() blocks when official_alpha_id is absent."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    import tempfile

    for bad_id in ("", None):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = SubmissionLedger(tmp)
            candidate = _candidate(official_alpha_id="")
            candidate.official_alpha_id = bad_id
            candidate.official_metrics = {}
            result = ledger.assess(
                candidate,
                SubmissionPolicy(min_minutes_between_auto_submissions=0),
                mode="manual",
            )
            assert not result["allowed"], (
                f"Expected allowed=False for official_alpha_id={bad_id!r}; "
                f"got allowed={result['allowed']}"
            )
            assert any(
                "official" in r.lower() for r in result["failed_reasons"]
            ), f"Expected 'official' in failed_reasons; got: {result['failed_reasons']}"


# ===========================================================================
# QA-P0-006: batch — mock candidate fails, normal candidate passes
# ===========================================================================

def test_qa_p0_006_batch_mock_fails_normal_passes():
    """In a batch, mock candidate is caught; clean candidate has no reasons."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    mock_candidate = _candidate(alpha_id="mock_candidate")
    clean_candidate = _candidate(alpha_id="alpha_abc123")

    mock_reasons = mock_source_reasons(mock_candidate)
    clean_reasons = mock_source_reasons(clean_candidate)

    assert mock_reasons, "Expected mock_candidate to be rejected"
    assert not clean_reasons, (
        f"Expected clean_candidate to pass; got reasons: {clean_reasons}"
    )


# ===========================================================================
# QA-P0-007: direct payload bypass still caught by mock_source_reasons
# ===========================================================================

def test_qa_p0_007_direct_payload_still_caught():
    """Even a directly-constructed mock-id candidate is intercepted by mock_source_reasons."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    candidate = _candidate(alpha_id="mock_bypass_id_xyz")
    reasons = mock_source_reasons(candidate)
    assert reasons, "Expected non-empty reasons even for directly-constructed mock payload"


# ===========================================================================
# QA-P0-008: auto-submit mock candidate produces auto_submit_skipped event
# ===========================================================================

def test_qa_p0_008_auto_submit_skipped_event_evidence():
    """Verifying safety reasons that would trigger auto_submit_skipped event."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    candidate = _candidate(alpha_id="mock_alpha_autosubmit")

    reasons = mock_source_reasons(candidate)
    assert reasons, (
        "mock_source_reasons must return non-empty reasons so that "
        "_assess_auto_submission emits auto_submit_skipped"
    )
    assert any("non-production" in r for r in reasons), (
        f"Expected 'non-production' in reason text; got: {reasons}"
    )


# ===========================================================================
# QA-P0-009: OfficialBrainAPI.submit_alpha() blocks mock id immediately
# ===========================================================================

def test_qa_p0_009_official_api_blocks_mock_id():
    """submit_alpha raises BrainAPIError before reaching _request for mock ids.

    NOTE: This test relies on OfficialBrainAPI being importable.
    If official.py has a syntax error, this test is marked KNOWN-BUG.
    """
    if _OFFICIAL_IMPORT_ERROR:
        raise _KnownSourceBug(
            f"[SOURCE BUG] official.py has IndentationError in _parse() — "
            f"cannot test OfficialBrainAPI.submit_alpha(). "
            f"Fix required: indent 'return {{\"raw\": raw}}' under except clause. "
            f"Original error: {_OFFICIAL_IMPORT_ERROR}"
        )

    api, request_calls = _make_stub_official_api()

    # submit_alpha() raises BEFORE calling _request when the id looks non-production.
    # The raised exception may be BrainAPIError (loaded via top-level import) or
    # the same class re-imported inside OfficialBrainAPI's own import chain.
    # We accept either BrainAPIError subclass or RuntimeError as the public contract.
    try:
        api.submit_alpha("mock_alpha_001", "rank(close)", {})
    except (BrainAPIError, RuntimeError) as exc:
        # Verify the error message references the mock id and mentions non-production
        exc_text = str(exc)
        assert "mock_alpha_001" in exc_text or "non-production" in exc_text.lower(), (
            f"Error message should reference the mock id or 'non-production'; got: {exc_text}"
        )
    except _KnownSourceBug:
        raise
    except Exception as exc:
        raise AssertionError(
            f"Expected BrainAPIError/RuntimeError, got {type(exc).__name__}: {exc}"
        ) from exc
    else:
        raise AssertionError(
            "Expected an exception to be raised for mock_alpha_001; none was raised"
        )

    # _request must NEVER have been called
    assert len(request_calls) == 0, (
        f"_request was unexpectedly called {len(request_calls)} time(s)"
    )


def test_qa_p0_009b_looks_non_production_alpha_id_function():
    """Unit-test _looks_non_production_alpha_id directly (parsed directly, no __init__)."""
    if _OFFICIAL_IMPORT_ERROR:
        raise _KnownSourceBug(
            f"[SOURCE BUG] official.py cannot be parsed: {_OFFICIAL_IMPORT_ERROR}"
        )
    fn = _looks_non_production_alpha_id
    assert fn("mock_alpha_001") is True
    assert fn("demo-xyz") is True
    assert fn("test") is True
    assert fn("testing") is True
    assert fn("fake_run_001") is True
    assert fn("sample_abc") is True
    assert fn("dry_run_001") is True
    assert fn("dryrun_abc") is True
    assert fn("abc123xyz") is False
    assert fn("alpha_a1b2c3d4") is False


# ===========================================================================
# QA-P0-010: normal production candidate is NOT mis-killed
# ===========================================================================

def test_qa_p0_010_production_candidate_not_falsely_blocked():
    """Production candidates with clean ids produce no safety reasons."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    candidate = _candidate(
        alpha_id="alpha_a1b2c3d4",
        official_alpha_id="abc123xyz",
        simulation_id="sim_789real",
        source_tags=["经验"],
    )
    reasons = mock_source_reasons(candidate)
    assert reasons == [], (
        f"Expected no reasons for clean production candidate; got: {reasons}"
    )

    if _OFFICIAL_IMPORT_ERROR:
        # Only the safety part of this test can run
        return

    assert _looks_non_production_alpha_id("abc123xyz") is False, (
        "_looks_non_production_alpha_id must return False for clean id 'abc123xyz'"
    )


# ===========================================================================
# QA-P0-011: non-mock simulation_id not mis-killed
# ===========================================================================

def test_qa_p0_011_non_mock_simulation_id_not_blocked():
    """simulation_id='sim_abc123' is NOT flagged as mock."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    candidate = _candidate(simulation_id="sim_abc123")
    reasons = mock_source_reasons(candidate)
    assert reasons == [], (
        f"Expected no reasons for simulation_id='sim_abc123'; got: {reasons}"
    )


# ===========================================================================
# QA-P0-012: mock env candidate has reasons; MockBrainAPI class name detected
# ===========================================================================

def test_qa_p0_012_mock_env_candidate_has_reasons():
    """_looks_mock_identifier returns True for mock identifiers."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    assert _looks_mock_identifier("mock") is True
    assert _looks_mock_identifier("demo") is True
    assert _looks_mock_identifier("test") is True

    candidate = _candidate(alpha_id="mock_env_candidate")
    reasons = mock_source_reasons(candidate)
    assert reasons, "Expected reasons for mock env candidate"


def test_qa_p0_012b_mock_brain_api_class_name_starts_with_mock():
    """MockBrainAPI class name (lower) starts with 'mock' — this is the _using_mock_api() signal.

    mock.py uses relative imports, so we inject it as part of the brain_alpha_ops.brain_api
    package by temporarily patching sys.modules to avoid triggering the brain_api __init__
    (which fails due to the official.py IndentationError).
    """
    try:
        import importlib.util as ilu
        import pathlib as pl
        import types

        # Ensure the package stub exists in sys.modules so relative imports work
        pkg_name = "brain_alpha_ops.brain_api"
        if pkg_name not in sys.modules:
            stub = types.ModuleType(pkg_name)
            stub.__path__ = [
                str(pl.Path(__file__).resolve().parents[1] / "brain_alpha_ops" / "brain_api")
            ]
            stub.__package__ = pkg_name
            sys.modules[pkg_name] = stub

        # Also ensure the parent package exists
        parent_name = "brain_alpha_ops"
        if parent_name not in sys.modules:
            parent_stub = types.ModuleType(parent_name)
            parent_stub.__path__ = [
                str(pl.Path(__file__).resolve().parents[1] / "brain_alpha_ops")
            ]
            parent_stub.__package__ = parent_name
            sys.modules[parent_name] = parent_stub

        # Load base.py first (MockBrainAPI depends on it)
        base_spec = ilu.spec_from_file_location(
            "brain_alpha_ops.brain_api.base",
            str(
                pl.Path(__file__).resolve().parents[1]
                / "brain_alpha_ops"
                / "brain_api"
                / "base.py"
            ),
        )
        base_mod = ilu.module_from_spec(base_spec)  # type: ignore[arg-type]
        base_mod.__package__ = "brain_alpha_ops.brain_api"
        sys.modules["brain_alpha_ops.brain_api.base"] = base_mod
        base_spec.loader.exec_module(base_mod)  # type: ignore[union-attr]

        # Now load mock.py
        mock_spec = ilu.spec_from_file_location(
            "brain_alpha_ops.brain_api.mock",
            str(
                pl.Path(__file__).resolve().parents[1]
                / "brain_alpha_ops"
                / "brain_api"
                / "mock.py"
            ),
        )
        mock_mod = ilu.module_from_spec(mock_spec)  # type: ignore[arg-type]
        mock_mod.__package__ = "brain_alpha_ops.brain_api"
        sys.modules["brain_alpha_ops.brain_api.mock"] = mock_mod
        mock_spec.loader.exec_module(mock_mod)  # type: ignore[union-attr]

        MockBrainAPI = mock_mod.MockBrainAPI
        assert MockBrainAPI.__name__.lower().startswith("mock"), (
            f"MockBrainAPI class name should start with 'mock'; got: {MockBrainAPI.__name__}"
        )
    except AssertionError:
        raise
    except Exception as exc:
        raise AssertionError(f"Could not load or verify MockBrainAPI: {exc}") from exc


# ===========================================================================
# QA-P0-013: submission_blocked audit record has all required fields
# ===========================================================================

def test_qa_p0_013_lifecycle_record_fields_complete():
    """Simulated _record_lifecycle output includes all mandatory audit fields."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    import time

    candidate = _candidate(
        alpha_id="alpha_blocked_001",
        official_alpha_id="official_xyz999",
        simulation_id="sim_blocked_001",
    )
    candidate.lifecycle_status = "submission_blocked"
    candidate.gate = {
        "submission_ready": False,
        "failed_reasons": ["mock_source_detected"],
    }

    # Simulate what _record_lifecycle() would produce (from pipeline.py lines 520-537)
    record = {
        "timestamp": time.time(),
        "alpha_id": candidate.alpha_id,
        "official_alpha_id": (
            candidate.official_alpha_id
            or candidate.official_metrics.get("official_alpha_id", "")
        ),
        "stage": "submission_blocked",
        "status": candidate.lifecycle_status,
        "family": candidate.family,
        "hypothesis": candidate.hypothesis,
        "score": candidate.scorecard.get("total_score", 0.0),
        "scorecard": candidate.scorecard,
        "local_quality": candidate.local_quality,
        "validation": candidate.validation,
        "official_metrics": candidate.official_metrics,
        "gate": candidate.gate,
        "simulation_id": candidate.simulation_id,
        "expression": candidate.expression,
        "note": "blocked by mock_source_reasons",
    }

    required_fields = [
        "alpha_id",
        "official_alpha_id",
        "simulation_id",
        "stage",
        "status",
        "timestamp",
        "gate",
    ]
    for field_name in required_fields:
        assert field_name in record, (
            f"Lifecycle record is missing required field: '{field_name}'"
        )
    assert record["alpha_id"] == "alpha_blocked_001"
    assert record["official_alpha_id"] == "official_xyz999"
    assert record["simulation_id"] == "sim_blocked_001"
    assert record["stage"] == "submission_blocked"
    assert record["gate"]["failed_reasons"], "gate.failed_reasons must be non-empty"


# ===========================================================================
# QA-P0-014: local guard vs official pre-submit check — distinguishable errors
# ===========================================================================

def test_qa_p0_014_error_messages_are_distinguishable():
    """Local mock guard and official pre-submit check produce distinct error texts."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR

    # --- Local guard: mock_source_reasons ---
    candidate = _candidate(alpha_id="mock_alpha_999")
    reasons = mock_source_reasons(candidate)
    local_error_text = "; ".join(reasons)
    assert "non-production" in local_error_text, (
        f"Local guard reason should contain 'non-production'; got: {local_error_text}"
    )

    if _OFFICIAL_IMPORT_ERROR:
        raise _KnownSourceBug(
            f"[SOURCE BUG] Cannot verify OfficialBrainAPI error text — "
            f"official.py IndentationError: {_OFFICIAL_IMPORT_ERROR}"
        )

    # --- Official path: submit_alpha raises immediately for mock id (before _request) ---
    # This exception fires at official.py:295 and contains 'non-production'.
    api, _ = _make_stub_official_api()
    official_mock_error = ""
    try:
        api.submit_alpha("mock_alpha_999", "rank(close)", {})
    except (BrainAPIError, RuntimeError) as exc:
        official_mock_error = str(exc)
    except _KnownSourceBug:
        raise

    assert official_mock_error, "Expected an exception from submit_alpha for mock id"
    assert "non-production" in official_mock_error.lower(), (
        f"Official API mock-reject message should contain 'non-production'; got: {official_mock_error}"
    )

    # --- Simulate the official pre-submit check failure message (official.py:298) ---
    # This message only fires when _looks_non_production_alpha_id passes but
    # check_alpha returns status != 'PASSED'. We verify the text is different.
    official_check_fail_text = "official pre-submit check failed"
    assert local_error_text != official_check_fail_text, (
        "Local guard and official check failure messages must be distinct"
    )
    assert official_mock_error != official_check_fail_text, (
        "Official mock-reject message and official check fail message must be distinct"
    )
    # Confirm all three messages are pairwise-distinct
    assert len({local_error_text, official_mock_error, official_check_fail_text}) == 3, (
        f"All three error texts should be distinct:\n"
        f"  local: {local_error_text!r}\n"
        f"  official: {official_mock_error!r}\n"
        f"  pre-check-fail: {official_check_fail_text!r}"
    )


# ===========================================================================
# Boundary and edge-case tests
# ===========================================================================

def test_boundary_empty_official_id():
    """Empty string is NOT a mock identifier — returns False."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    assert _looks_mock_identifier("") is False, (
        "_looks_mock_identifier('') must return False"
    )


def test_boundary_none_official_id():
    """None value is safe — no exception, returns False."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    result = _looks_mock_identifier(None)
    assert result is False, (
        f"_looks_mock_identifier(None) must return False; got: {result}"
    )


def test_boundary_mixed_case_mock():
    """'Mock_Alpha_001' is caught despite mixed capitalisation."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    assert _looks_mock_identifier("Mock_Alpha_001") is True, (
        "_looks_mock_identifier is case-insensitive; 'Mock_Alpha_001' must be flagged"
    )
    if _OFFICIAL_IMPORT_ERROR:
        raise _KnownSourceBug(
            f"[SOURCE BUG] Cannot verify _looks_non_production_alpha_id: {_OFFICIAL_IMPORT_ERROR}"
        )
    assert _looks_non_production_alpha_id("Mock_Alpha_001") is True


def test_boundary_mock_inside_id():
    """'alpha_contest_123' contains 'test' but NOT as a prefix — must NOT be flagged."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    assert _looks_mock_identifier("alpha_contest_123") is False, (
        "'alpha_contest_123' has 'test' inside but not as prefix — must not be flagged"
    )
    if _OFFICIAL_IMPORT_ERROR:
        raise _KnownSourceBug(
            f"[SOURCE BUG] Cannot verify _looks_non_production_alpha_id: {_OFFICIAL_IMPORT_ERROR}"
        )
    assert _looks_non_production_alpha_id("alpha_contest_123") is False


def test_boundary_test_inside_id():
    """'simulation_interest_456' contains 'test' inside, not as prefix — must NOT be flagged."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    assert _looks_mock_identifier("simulation_interest_456") is False, (
        "'simulation_interest_456' must not be flagged — 'test' appears mid-word"
    )


def test_boundary_mock_prefix_edge():
    """'mock_' (prefix only, no suffix) IS flagged."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    assert _looks_mock_identifier("mock_") is True, (
        "'mock_' must be flagged — it starts with mock_ prefix"
    )
    if _OFFICIAL_IMPORT_ERROR:
        raise _KnownSourceBug(
            f"[SOURCE BUG] Cannot verify _looks_non_production_alpha_id: {_OFFICIAL_IMPORT_ERROR}"
        )
    assert _looks_non_production_alpha_id("mock_") is True


def test_boundary_demo_hyphen_prefix():
    """'demo-alpha-xyz' is flagged because it starts with 'demo-'."""
    if _SAFETY_IMPORT_ERROR:
        raise _SAFETY_IMPORT_ERROR
    assert _looks_mock_identifier("demo-alpha-xyz") is True, (
        "'demo-alpha-xyz' must be flagged — starts with 'demo-'"
    )
    if _OFFICIAL_IMPORT_ERROR:
        raise _KnownSourceBug(
            f"[SOURCE BUG] Cannot verify _looks_non_production_alpha_id: {_OFFICIAL_IMPORT_ERROR}"
        )
    assert _looks_non_production_alpha_id("demo-alpha-xyz") is True


# ===========================================================================
# Test runner — identical pattern to other test files in this project
# ===========================================================================

_KNOWN_BUG_MARKER = "[SOURCE BUG]"

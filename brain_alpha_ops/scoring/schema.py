"""JSON Schema definitions for scoring output structures.

Provides JSON Schema validation for ScoringResult, GateResult, and ScorecardDict.
These schemas can be used for API responses, logging, and external integrations.
"""

from __future__ import annotations

from typing import Any

SCORING_RESULT_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "ScoringResult",
    "description": "Complete scoring result with full attribution from OfficialScoringSystem",
    "type": "object",
    "required": ["alpha_id", "expression", "total_score", "decision_band", "passed_gate", "evaluated_at"],
    "properties": {
        "alpha_id": {"type": "string", "description": "Unique alpha identifier"},
        "expression": {"type": "string", "description": "Alpha expression string"},
        "total_score": {"type": "number", "minimum": 0, "maximum": 100, "description": "Composite score (0-100)"},
        "decision_band": {
            "type": "string",
            "enum": ["SUBMIT", "OPTIMIZE", "RESEARCH", "REJECT"],
            "description": "Decision band based on score thresholds",
        },
        "passed_gate": {"type": "boolean", "description": "Whether alpha passed quality gate"},
        "evaluated_at": {"type": "string", "format": "date-time", "description": "ISO 8601 evaluation timestamp"},
        "prior": {"$ref": "#/definitions/ScoreLayer"},
        "empirical": {"$ref": "#/definitions/ScoreLayer"},
        "checklist": {"$ref": "#/definitions/ScoreLayer"},
        "layer_weights": {
            "type": "object",
            "properties": {
                "prior": {"type": "number"},
                "empirical": {"type": "number"},
                "checklist": {"type": "number"},
            },
        },
        "hard_gates": {"type": "array", "items": {"$ref": "#/definitions/GateResultDict"}},
        "soft_gates": {"type": "array", "items": {"$ref": "#/definitions/GateResultDict"}},
        "release_gate": {"$ref": "#/definitions/ReleaseGate"},
        "attribution_tree": {"$ref": "#/definitions/AttributionNode"},
        "top_failures": {
            "type": "array",
            "items": {"$ref": "#/definitions/FailureItem"},
        },
        "improvement_hints": {"type": "array", "items": {"type": "string"}},
        "simulated_api_output": {"type": "object"},
        "api_output_deviation": {"type": "number", "minimum": 0},
        "deviation_details": {"type": "array", "items": {"type": "string"}},
        "threshold_version": {"type": "string"},
        "scoring_schema": {"type": "string"},
        "scoring_version": {"type": "string"},
        "config_hash": {"type": "string"},
        "score_basis": {"type": "string"},
        "settings_trace": {"type": "object"},
        "threshold_trace": {"type": "object"},
        "calibration": {"type": "object"},
        "attribution_summary": {"type": "string"},
    },
    "definitions": {
        "ScoreLayer": {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "weight": {"type": "number"},
                "items": {"type": "array", "items": {"$ref": "#/definitions/ScoreItem"}},
            },
        },
        "ScoreItem": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "score": {"type": "number"},
                "passed": {"type": "boolean"},
                "is_hard_gate": {"type": "boolean"},
                "actual": {},
                "target": {},
                "direction": {"type": "string"},
                "source": {"type": "string"},
            },
        },
        "GateResultDict": {
            "type": "object",
            "required": ["gate_name", "passed", "check_items", "failed_items", "threshold_source"],
            "properties": {
                "gate_name": {"type": "string"},
                "passed": {"type": "boolean"},
                "check_items": {"type": "array", "items": {"type": "object"}},
                "failed_items": {"type": "array", "items": {"type": "string"}},
                "threshold_source": {"type": "string"},
                "notes": {"type": "array", "items": {"type": "string"}},
                "zero_deviation": {"type": "boolean"},
                "triggered_rules": {"type": "array", "items": {"type": "object"}},
            },
        },
        "ReleaseGate": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "score": {"type": "number"},
                "threshold": {"type": "number"},
                "details": {"type": "object"},
            },
        },
        "AttributionNode": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "score": {"type": "number"},
                "weight": {"type": "number"},
                "contribution": {"type": "number"},
                "explanation": {"type": "string"},
                "historical_trend": {"type": "string"},
                "children": {"type": "array", "items": {"$ref": "#/definitions/AttributionNode"}},
            },
        },
        "FailureItem": {
            "type": "object",
            "required": ["item", "severity", "reason"],
            "properties": {
                "item": {"type": "string"},
                "severity": {"type": "string", "enum": ["HARD", "SOFT"]},
                "reason": {"type": "string"},
                "source": {"type": "string"},
            },
        },
    },
}


GATE_RESULT_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "GateResult",
    "description": "Pass/Fail gate result with full traceability",
    "type": "object",
    "required": ["gate_name", "passed", "check_items", "failed_items", "threshold_source"],
    "properties": {
        "gate_name": {"type": "string", "description": "Name identifier for the gate"},
        "passed": {"type": "boolean", "description": "Whether all checks passed"},
        "check_items": {
            "type": "array",
            "description": "Individual check results",
            "items": {"$ref": "#/definitions/GateCheckItem"},
        },
        "failed_items": {
            "type": "array",
            "description": "Descriptions of failed checks",
            "items": {"type": "string"},
        },
        "threshold_source": {
            "type": "string",
            "description": "Source of threshold values (e.g., BRAIN_Official)",
        },
        "notes": {
            "type": "array",
            "description": "Additional notes about the gate evaluation",
            "items": {"type": "string"},
        },
        "zero_deviation": {
            "type": "boolean",
            "description": "Whether configured gate matches official BRAIN check",
        },
    },
    "definitions": {
        "GateCheckItem": {
            "type": "object",
            "required": ["name", "passed"],
            "properties": {
                "name": {"type": "string"},
                "passed": {"type": "boolean"},
                "type": {"type": "string", "enum": ["HARD", "SOFT"]},
                "source": {"type": "string"},
                "description": {"type": "string"},
                "configured_passed": {"type": "boolean"},
                "official_passed": {"type": "boolean"},
                "zero_deviation": {"type": "boolean"},
                "actual": {},
                "target": {},
                "direction": {"type": "string"},
                "error": {"type": "string"},
            },
        },
    },
}


SCORECARD_DICT_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "ScorecardDict",
    "description": "Scorecard output from build_scorecard() in research.scoring",
    "type": "object",
    "required": ["total_score", "decision_band", "prior", "empirical", "submission_checklist", "layer_weights"],
    "properties": {
        "total_score": {"type": "number", "minimum": 0, "maximum": 100},
        "decision_band": {
            "type": "string",
            "enum": ["SUBMIT", "OPTIMIZE", "RESEARCH", "REJECT"],
        },
        "score_basis": {"type": "string"},
        "prior": {"$ref": "#/definitions/LayerResult"},
        "empirical": {"$ref": "#/definitions/LayerResult"},
        "submission_checklist": {"$ref": "#/definitions/ChecklistResult"},
        "layer_weights": {
            "type": "object",
            "properties": {
                "prior": {"type": "number"},
                "empirical": {"type": "number"},
                "checklist": {"type": "number"},
            },
        },
        "settings_trace": {"type": "object"},
        "calibration": {"type": "object"},
    },
    "definitions": {
        "LayerResult": {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "weight": {"type": "number"},
                "items": {"type": "array", "items": {"$ref": "#/definitions/LayerItem"}},
            },
        },
        "LayerItem": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "score": {"type": "number"},
                "passed": {"type": "boolean"},
                "is_hard_gate": {"type": "boolean"},
                "actual": {},
                "target": {},
                "direction": {"type": "string"},
                "source": {"type": "string"},
            },
        },
        "ChecklistResult": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "passed": {"type": "boolean"},
                            "meaning": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}


def validate_scoring_result(data: dict[str, Any]) -> list[str]:
    """Validate a ScoringResult dict against the schema.

    Returns a list of validation error messages (empty if valid).
    """
    errors: list[str] = []

    required = SCORING_RESULT_SCHEMA["required"]
    for field_name in required:
        if field_name not in data:
            errors.append(f"Missing required field: {field_name}")

    if "total_score" in data:
        score = data["total_score"]
        if not isinstance(score, (int, float)):
            errors.append("total_score must be a number")
        elif score < 0 or score > 100:
            errors.append("total_score must be between 0 and 100")

    if "decision_band" in data:
        valid_bands = {"SUBMIT", "OPTIMIZE", "RESEARCH", "REJECT"}
        if data["decision_band"] not in valid_bands:
            errors.append(f"decision_band must be one of {valid_bands}")

    if "passed_gate" in data and not isinstance(data["passed_gate"], bool):
        errors.append("passed_gate must be a boolean")

    return errors


def validate_gate_result(data: dict[str, Any]) -> list[str]:
    """Validate a GateResult dict against the schema.

    Returns a list of validation error messages (empty if valid).
    """
    errors: list[str] = []

    required = GATE_RESULT_SCHEMA["required"]
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if "check_items" in data and not isinstance(data["check_items"], list):
        errors.append("check_items must be an array")

    if "failed_items" in data and not isinstance(data["failed_items"], list):
        errors.append("failed_items must be an array")

    return errors

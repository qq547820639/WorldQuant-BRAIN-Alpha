"""Tests for the minimal YAML parser used by packaged hypothesis files."""

import pytest

from brain_alpha_ops.research.hypothesis_library._minimal_yaml import _minimal_yaml_load


def test_loads_simple_mapping():
    assert _minimal_yaml_load("name: AlphaOne\nid: 42\n") == {"name": "AlphaOne", "id": 42}


def test_loads_scalar_types():
    data = _minimal_yaml_load(
        "a: true\nb: false\nc: null\nd: 3.5\ne: -2\nf: 'quoted'\n"
    )
    assert data == {"a": True, "b": False, "c": None, "d": 3.5, "e": -2, "f": "quoted"}


def test_loads_integer_like_float():
    data = _minimal_yaml_load("weight: 3.0\n")
    assert data == {"weight": 3}
    assert isinstance(data["weight"], int)


def test_handles_empty_and_null():
    assert _minimal_yaml_load("a: ~\nb: Null\nc: \n") == {"a": None, "b": None, "c": {}}


def test_loads_nested_mapping():
    data = _minimal_yaml_load("outer:\n  inner:\n    key: value\n  num: 1\n")
    assert data == {"outer": {"inner": {"key": "value"}, "num": 1}}


def test_loads_sequence_nested_in_mapping():
    data = _minimal_yaml_load("items:\n  - a\n  - b\n  - 3\n")
    assert data == {"items": ["a", "b", 3]}


def test_loads_sequence_of_mappings_nested():
    data = _minimal_yaml_load("list:\n  - name: a\n    size: 1\n  - name: b\n    size: 2\n")
    assert data == {"list": [{"name": "a", "size": 1}, {"name": "b", "size": 2}]}


def test_loads_inline_list():
    data = _minimal_yaml_load("tags: [x, y, z]\nemptylist: []\n")
    assert data == {"tags": ["x", "y", "z"], "emptylist": []}


def test_loads_folded_block():
    data = _minimal_yaml_load("text: >\n  line one\n  line two\n")
    assert data == {"text": "line one line two"}


def test_strips_comments():
    data = _minimal_yaml_load("name: Alpha # trailing\n")
    assert data == {"name": "Alpha"}


def test_quoted_value_with_colon_is_scalar():
    data = _minimal_yaml_load("note: 'a: b'\n")
    assert data == {"note": "a: b"}


def test_empty_input_returns_empty_dict():
    assert _minimal_yaml_load("") == {}
    assert _minimal_yaml_load("   \n\n") == {}


def test_returns_empty_dict_when_top_level_is_sequence():
    # Top-level must be a mapping; a bare sequence yields {}.
    assert _minimal_yaml_load("- a\n- b\n") == {}


def test_unknown_scalar_returns_string():
    data = _minimal_yaml_load("key: hello world\n")
    assert data == {"key": "hello world"}
from agent_kit.judges import _resolve_path, run_judge
from agent_kit.types import JudgeSpec

_MISSING_SENTINEL = object()


# --- path resolver ---


def test_resolve_dotted_dict_path():
    assert _resolve_path({"a": {"b": 1}}, "a.b") == 1


def test_resolve_list_index():
    assert _resolve_path({"xs": [10, 20, 30]}, "xs.1") == 20


def test_resolve_nested_list_dict():
    assert _resolve_path({"out": [{"k": "v"}]}, "out.0.k") == "v"


def test_resolve_missing_key_returns_sentinel():
    from agent_kit.judges import _MISSING

    assert _resolve_path({"a": 1}, "b") is _MISSING


def test_resolve_through_null():
    from agent_kit.judges import _MISSING

    assert _resolve_path({"a": None}, "a.b") is _MISSING


def test_resolve_invalid_index():
    from agent_kit.judges import _MISSING

    assert _resolve_path({"xs": [1]}, "xs.notanint") is _MISSING


# --- not_null ---


def test_not_null_passes_when_present():
    spec = JudgeSpec(type="not_null", params={"path": "output.x"})
    assert run_judge(spec, {"output": {"x": 1}}).passed


def test_not_null_fails_on_missing():
    spec = JudgeSpec(type="not_null", params={"path": "output.x"})
    res = run_judge(spec, {"output": {}})
    assert not res.passed and "not found" in res.detail


def test_not_null_fails_on_null():
    spec = JudgeSpec(type="not_null", params={"path": "output.x"})
    res = run_judge(spec, {"output": {"x": None}})
    assert not res.passed and "is null" in res.detail


def test_not_null_passes_on_falsy_zero():
    spec = JudgeSpec(type="not_null", params={"path": "output.x"})
    assert run_judge(spec, {"output": {"x": 0}}).passed


def test_not_null_passes_on_empty_string():
    spec = JudgeSpec(type="not_null", params={"path": "output.x"})
    assert run_judge(spec, {"output": {"x": ""}}).passed


# --- key_present ---


def test_key_present_passes_even_for_null():
    spec = JudgeSpec(type="key_present", params={"path": "output.x"})
    assert run_judge(spec, {"output": {"x": None}}).passed


def test_key_present_fails_when_absent():
    spec = JudgeSpec(type="key_present", params={"path": "output.x"})
    assert not run_judge(spec, {"output": {}}).passed


# --- key_equals ---


def test_key_equals_passes_on_match():
    spec = JudgeSpec(type="key_equals", params={"path": "a", "value": 42})
    assert run_judge(spec, {"a": 42}).passed


def test_key_equals_fails_on_mismatch():
    spec = JudgeSpec(type="key_equals", params={"path": "a", "value": 42})
    res = run_judge(spec, {"a": 7})
    assert not res.passed and "expected 42" in res.detail


def test_key_equals_fails_on_missing():
    spec = JudgeSpec(type="key_equals", params={"path": "a", "value": 42})
    assert not run_judge(spec, {}).passed


# --- key_in ---


def test_key_in_passes():
    spec = JudgeSpec(type="key_in", params={"path": "x", "values": ["a", "b"]})
    assert run_judge(spec, {"x": "a"}).passed


def test_key_in_fails():
    spec = JudgeSpec(type="key_in", params={"path": "x", "values": ["a", "b"]})
    assert not run_judge(spec, {"x": "c"}).passed


# --- regex_match ---


def test_regex_match_passes():
    spec = JudgeSpec(
        type="regex_match", params={"path": "out", "pattern": r"^\d{4}$"}
    )
    assert run_judge(spec, {"out": "2026"}).passed


def test_regex_match_fails_on_non_string():
    spec = JudgeSpec(type="regex_match", params={"path": "out", "pattern": "."})
    res = run_judge(spec, {"out": 42})
    assert not res.passed and "not a string" in res.detail


def test_regex_match_substring_search():
    spec = JudgeSpec(
        type="regex_match",
        params={"path": "out", "pattern": "case"},
    )
    assert run_judge(spec, {"out": "this is a case study"}).passed


# --- length_bounds ---


def test_length_bounds_string_within():
    spec = JudgeSpec(
        type="length_bounds", params={"path": "x", "min": 3, "max": 10}
    )
    assert run_judge(spec, {"x": "hello"}).passed


def test_length_bounds_below_min():
    spec = JudgeSpec(type="length_bounds", params={"path": "x", "min": 5})
    res = run_judge(spec, {"x": "hi"})
    assert not res.passed and "below min" in res.detail


def test_length_bounds_above_max():
    spec = JudgeSpec(type="length_bounds", params={"path": "x", "max": 3})
    res = run_judge(spec, {"x": [1, 2, 3, 4]})
    assert not res.passed and "above max" in res.detail


def test_length_bounds_no_length():
    spec = JudgeSpec(type="length_bounds", params={"path": "x", "min": 0})
    res = run_judge(spec, {"x": 42})
    assert not res.passed and "no length" in res.detail


# --- schema_valid ---


def test_schema_valid_passes():
    spec = JudgeSpec(
        type="schema_valid",
        params={
            "path": "output",
            "schema": {
                "type": "object",
                "required": ["answer"],
                "properties": {"answer": {"type": "string"}},
            },
        },
    )
    assert run_judge(spec, {"output": {"answer": "yes"}}).passed


def test_schema_valid_fails_with_location():
    spec = JudgeSpec(
        type="schema_valid",
        params={
            "path": "output",
            "schema": {
                "type": "object",
                "required": ["answer"],
                "properties": {"answer": {"type": "string"}},
            },
        },
    )
    res = run_judge(spec, {"output": {"answer": 42}})
    assert not res.passed and "schema invalid" in res.detail


# --- error paths ---


def test_unknown_judge_type_fails():
    spec = JudgeSpec(type="not_a_real_judge", params={})
    res = run_judge(spec, {})
    assert not res.passed and "unknown judge type" in res.detail


def test_missing_judge_param_reports_clearly():
    spec = JudgeSpec(type="key_equals", params={"path": "x"})  # no value
    res = run_judge(spec, {"x": 1})
    assert not res.passed and "missing judge param" in res.detail

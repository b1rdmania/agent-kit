from __future__ import annotations

import re
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from agent_kit.types import JudgeResult, JudgeSpec

_MISSING = object()


def _resolve_path(root: Any, path: str) -> Any:
    cursor: Any = root
    for part in path.split("."):
        if isinstance(cursor, list):
            try:
                cursor = cursor[int(part)]
            except (ValueError, IndexError):
                return _MISSING
        elif isinstance(cursor, dict):
            if part not in cursor:
                return _MISSING
            cursor = cursor[part]
        else:
            return _MISSING
    return cursor


def _ok(spec: JudgeSpec, detail: str | None = None) -> JudgeResult:
    return JudgeResult(spec=spec, passed=True, detail=detail)


def _fail(spec: JudgeSpec, detail: str) -> JudgeResult:
    return JudgeResult(spec=spec, passed=False, detail=detail)


def _key_present(spec: JudgeSpec, root: Any) -> JudgeResult:
    path = spec.params["path"]
    value = _resolve_path(root, path)
    if value is _MISSING:
        return _fail(spec, f"path not found: {path}")
    return _ok(spec)


def _not_null(spec: JudgeSpec, root: Any) -> JudgeResult:
    path = spec.params["path"]
    value = _resolve_path(root, path)
    if value is _MISSING:
        return _fail(spec, f"path not found: {path}")
    if value is None:
        return _fail(spec, f"path {path} is null")
    return _ok(spec)


def _key_equals(spec: JudgeSpec, root: Any) -> JudgeResult:
    path = spec.params["path"]
    expected = spec.params["value"]
    value = _resolve_path(root, path)
    if value is _MISSING:
        return _fail(spec, f"path not found: {path}")
    if value != expected:
        return _fail(spec, f"expected {expected!r}, got {value!r}")
    return _ok(spec)


def _key_in(spec: JudgeSpec, root: Any) -> JudgeResult:
    path = spec.params["path"]
    allowed = spec.params["values"]
    value = _resolve_path(root, path)
    if value is _MISSING:
        return _fail(spec, f"path not found: {path}")
    if value not in allowed:
        return _fail(spec, f"value {value!r} not in {allowed!r}")
    return _ok(spec)


def _regex_match(spec: JudgeSpec, root: Any) -> JudgeResult:
    path = spec.params["path"]
    pattern = spec.params["pattern"]
    value = _resolve_path(root, path)
    if value is _MISSING:
        return _fail(spec, f"path not found: {path}")
    if not isinstance(value, str):
        return _fail(spec, f"path {path} is not a string ({type(value).__name__})")
    if not re.search(pattern, value):
        return _fail(spec, f"value did not match /{pattern}/: {value!r}")
    return _ok(spec)


def _length_bounds(spec: JudgeSpec, root: Any) -> JudgeResult:
    path = spec.params["path"]
    lo = spec.params.get("min")
    hi = spec.params.get("max")
    value = _resolve_path(root, path)
    if value is _MISSING:
        return _fail(spec, f"path not found: {path}")
    try:
        length = len(value)
    except TypeError:
        return _fail(spec, f"path {path} has no length ({type(value).__name__})")
    if lo is not None and length < lo:
        return _fail(spec, f"length {length} below min {lo}")
    if hi is not None and length > hi:
        return _fail(spec, f"length {length} above max {hi}")
    return _ok(spec)


def _schema_valid(spec: JudgeSpec, root: Any) -> JudgeResult:
    schema = spec.params["schema"]
    target = _resolve_path(root, spec.params.get("path", "output"))
    if target is _MISSING:
        return _fail(spec, "target path not found")
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(target), key=lambda e: e.path)
    if errors:
        first: ValidationError = errors[0]
        loc = "/".join(str(p) for p in first.absolute_path) or "<root>"
        return _fail(spec, f"schema invalid at {loc}: {first.message}")
    return _ok(spec)


_REGISTRY = {
    "key_present": _key_present,
    "not_null": _not_null,
    "key_equals": _key_equals,
    "key_in": _key_in,
    "regex_match": _regex_match,
    "length_bounds": _length_bounds,
    "schema_valid": _schema_valid,
}


def run_judge(spec: JudgeSpec, root: Any) -> JudgeResult:
    impl = _REGISTRY.get(spec.type)
    if impl is None:
        return _fail(spec, f"unknown judge type: {spec.type}")
    try:
        return impl(spec, root)
    except KeyError as exc:
        return _fail(spec, f"missing judge param: {exc.args[0]}")
    except Exception as exc:
        return _fail(spec, f"judge crashed: {exc}")

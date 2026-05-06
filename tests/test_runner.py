"""Runner edge cases. The e2e test exercises the happy path."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from agent_kit.runner import load_dataset, run


def _write_jsonl(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "ds.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return p


def _record(id_: str, judges: list[dict]) -> dict:
    return {"id": id_, "input": {}, "judges": judges}


def _run_against(monkeypatch, dataset_path: Path, response_factory) -> list:
    """Patch httpx.Client to return scripted responses."""

    class _MockResponse:
        def __init__(self, status_code: int, body, raw_text: str | None = None):
            self.status_code = status_code
            self._body = body
            self._raw_text = raw_text

        @property
        def text(self) -> str:
            if self._raw_text is not None:
                return self._raw_text
            return json.dumps(self._body)

        def json(self):
            if self._raw_text is not None:
                raise ValueError("not json")
            return self._body

    class _MockClient:
        def __init__(self, *args, **kwargs):
            self._calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, json=None, headers=None):
            self._calls += 1
            return response_factory(self._calls, json)

    monkeypatch.setattr("agent_kit.runner.httpx.Client", _MockClient)
    return run(dataset_path, "http://stub").results


def test_load_dataset_skips_blank_and_comment_lines(tmp_path):
    p = tmp_path / "ds.jsonl"
    p.write_text(
        '\n# a comment\n{"id": "a", "input": {}, "judges": []}\n\n'
        '{"id": "b", "input": {}, "judges": []}\n'
    )
    records = load_dataset(p)
    assert [r.id for r in records] == ["a", "b"]


def test_load_dataset_reports_line_number_on_bad_json(tmp_path):
    p = tmp_path / "ds.jsonl"
    p.write_text('{"id": "ok", "input": {}, "judges": []}\nNOT JSON\n')
    with pytest.raises(ValueError, match=r":2:"):
        load_dataset(p)


def test_run_handles_transport_error(tmp_path, monkeypatch):
    ds = _write_jsonl(tmp_path, [_record("net-fail", [])])

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, *a, **k):
            raise httpx.ConnectError("refused")

    monkeypatch.setattr("agent_kit.runner.httpx.Client", _Client)
    summary = run(ds, "http://stub")
    assert not summary.results[0].passed
    assert "transport error" in summary.results[0].error


def test_run_marks_500_as_fail(tmp_path, monkeypatch):
    ds = _write_jsonl(tmp_path, [_record("server-err", [])])
    results = _run_against(
        monkeypatch,
        ds,
        lambda n, body: _MockBuilder.response(500, raw_text="boom"),
    )
    assert "HTTP 500" in results[0].error


def test_run_fails_on_non_json_body(tmp_path, monkeypatch):
    ds = _write_jsonl(tmp_path, [_record("non-json", [])])
    results = _run_against(
        monkeypatch,
        ds,
        lambda n, body: _MockBuilder.response(200, raw_text="<html>nope</html>"),
    )
    assert "non-JSON response" in results[0].error


def test_run_fails_on_array_response(tmp_path, monkeypatch):
    ds = _write_jsonl(tmp_path, [_record("array-resp", [])])
    results = _run_against(
        monkeypatch,
        ds,
        lambda n, body: _MockBuilder.response(200, body=[1, 2, 3]),
    )
    assert "not a JSON object" in results[0].error


def test_run_fails_when_output_key_missing_with_error_field(tmp_path, monkeypatch):
    ds = _write_jsonl(tmp_path, [_record("agent-error", [])])
    results = _run_against(
        monkeypatch,
        ds,
        lambda n, body: _MockBuilder.response(
            200,
            body={
                "error": "model rejected",
                "metadata": {"cost_usd": 0.0001},
            },
        ),
    )
    assert "model rejected" in results[0].error
    assert results[0].cost_usd == pytest.approx(0.0001)


def test_run_fails_when_output_key_missing_no_error(tmp_path, monkeypatch):
    ds = _write_jsonl(tmp_path, [_record("contract-violation", [])])
    results = _run_against(
        monkeypatch,
        ds,
        lambda n, body: _MockBuilder.response(200, body={"metadata": {}}),
    )
    assert "contract violation" in results[0].error


def test_run_ignores_bool_cost(tmp_path, monkeypatch):
    ds = _write_jsonl(tmp_path, [_record("bool-cost", [])])
    results = _run_against(
        monkeypatch,
        ds,
        lambda n, body: _MockBuilder.response(
            200,
            body={"output": {}, "metadata": {"cost_usd": True}},
        ),
    )
    # bool is technically int in Python — must be excluded
    assert results[0].cost_usd is None


def test_run_handles_null_metadata(tmp_path, monkeypatch):
    ds = _write_jsonl(tmp_path, [_record("null-meta", [])])
    results = _run_against(
        monkeypatch,
        ds,
        lambda n, body: _MockBuilder.response(
            200, body={"output": {"k": 1}, "metadata": None}
        ),
    )
    assert results[0].passed
    assert results[0].cost_usd is None


def test_run_passes_with_no_judges_and_valid_shape(tmp_path, monkeypatch):
    ds = _write_jsonl(tmp_path, [_record("zero-judges", [])])
    results = _run_against(
        monkeypatch,
        ds,
        lambda n, body: _MockBuilder.response(200, body={"output": {}}),
    )
    assert results[0].passed


def test_run_sends_secret_header_when_provided(tmp_path, monkeypatch):
    ds = _write_jsonl(tmp_path, [_record("with-secret", [])])
    captured: dict = {}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, json=None, headers=None):
            captured["headers"] = headers
            return _MockBuilder.response(200, body={"output": {}})

    monkeypatch.setattr("agent_kit.runner.httpx.Client", _Client)
    run(ds, "http://stub", secret="s3cret")
    assert captured["headers"]["X-Agent-Kit-Secret"] == "s3cret"


# --- shared mock helpers ---


class _MockBuilder:
    @staticmethod
    def response(status_code: int, body=None, raw_text: str | None = None):
        class _Resp:
            def __init__(self):
                self.status_code = status_code
                self._body = body
                self._raw = raw_text

            @property
            def text(self):
                if self._raw is not None:
                    return self._raw
                return json.dumps(self._body)

            def json(self):
                if self._raw is not None:
                    raise ValueError("not json")
                return self._body

        return _Resp()

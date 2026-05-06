"""End-to-end: boot the stub server, run the sample dataset against it."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from agent_kit.runner import run

ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def stub_server():
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "examples.stub_server:app",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.perf_counter() + 10
    while time.perf_counter() < deadline:
        try:
            httpx.post(f"{base}/agent", json={"input": {}}, timeout=0.5)
            break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        proc.terminate()
        pytest.fail("stub server did not start within 10s")
    yield base
    proc.terminate()
    proc.wait(timeout=5)


def test_e2e_sample_dataset_passes(stub_server):
    summary = run(
        dataset_path=ROOT / "examples" / "sample.jsonl",
        endpoint=f"{stub_server}/agent",
    )
    assert summary.all_passed, [
        (r.record.id, [(j.spec.type, j.detail) for j in r.judge_results if not j.passed])
        for r in summary.results
        if not r.passed
    ]
    assert summary.total == 2
    assert summary.total_cost_usd == pytest.approx(0.0002)


def test_e2e_broken_no_output_endpoint(stub_server, tmp_path):
    ds = tmp_path / "ds.jsonl"
    ds.write_text('{"id": "broken", "input": {}, "judges": []}\n')
    summary = run(
        dataset_path=ds, endpoint=f"{stub_server}/agent/broken-no-output"
    )
    assert not summary.all_passed
    assert "contract violation" in summary.results[0].error


def test_e2e_broken_error_endpoint(stub_server, tmp_path):
    ds = tmp_path / "ds.jsonl"
    ds.write_text('{"id": "errored", "input": {}, "judges": []}\n')
    summary = run(
        dataset_path=ds, endpoint=f"{stub_server}/agent/broken-error"
    )
    assert not summary.all_passed
    assert "model rejected" in summary.results[0].error

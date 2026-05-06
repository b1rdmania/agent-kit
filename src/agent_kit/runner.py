from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from agent_kit.judges import run_judge
from agent_kit.types import EvalRecord, EvalResult, RunSummary


def load_dataset(path: Path) -> list[EvalRecord]:
    records: list[EvalRecord] = []
    with path.open() as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{i}: invalid JSON: {exc}") from exc
            records.append(EvalRecord.from_dict(raw))
    return records


def _request_payload(record: EvalRecord) -> dict[str, Any]:
    return {
        "input": record.input,
        "trace_id": f"agent-kit-{uuid.uuid4()}",
        "metadata": {
            "record_id": record.id,
            "source": "agent-kit-runner",
            "tags": record.tags,
        },
    }


def _evaluate(record: EvalRecord, response_json: dict[str, Any]) -> tuple[bool, list]:
    judge_results = [run_judge(spec, response_json) for spec in record.judges]
    passed = all(jr.passed for jr in judge_results)
    return passed, judge_results


def run(
    dataset_path: Path,
    endpoint: str,
    secret: str | None = None,
    timeout_seconds: float = 60.0,
) -> RunSummary:
    records = load_dataset(dataset_path)
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Agent-Kit-Secret"] = secret

    results: list[EvalResult] = []
    total_cost = 0.0
    started = time.perf_counter()

    with httpx.Client(timeout=timeout_seconds) as client:
        for record in records:
            req_started = time.perf_counter()
            try:
                resp = client.post(
                    endpoint, json=_request_payload(record), headers=headers
                )
            except httpx.HTTPError as exc:
                duration_ms = int((time.perf_counter() - req_started) * 1000)
                results.append(
                    EvalResult(
                        record=record,
                        passed=False,
                        duration_ms=duration_ms,
                        cost_usd=None,
                        judge_results=[],
                        error=f"transport error: {exc}",
                    )
                )
                continue

            duration_ms = int((time.perf_counter() - req_started) * 1000)

            if resp.status_code >= 400:
                results.append(
                    EvalResult(
                        record=record,
                        passed=False,
                        duration_ms=duration_ms,
                        cost_usd=None,
                        judge_results=[],
                        error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                    )
                )
                continue

            try:
                response_json = resp.json()
            except ValueError:
                results.append(
                    EvalResult(
                        record=record,
                        passed=False,
                        duration_ms=duration_ms,
                        cost_usd=None,
                        judge_results=[],
                        error=f"non-JSON response: {resp.text[:200]}",
                    )
                )
                continue

            passed, judge_results = _evaluate(record, response_json)
            cost = response_json.get("metadata", {}).get("cost_usd")
            if isinstance(cost, (int, float)):
                total_cost += float(cost)

            results.append(
                EvalResult(
                    record=record,
                    passed=passed,
                    duration_ms=duration_ms,
                    cost_usd=cost if isinstance(cost, (int, float)) else None,
                    judge_results=judge_results,
                    response_metadata=response_json.get("metadata", {}),
                )
            )

    total_duration_ms = int((time.perf_counter() - started) * 1000)
    return RunSummary(
        results=results,
        total_duration_ms=total_duration_ms,
        total_cost_usd=total_cost,
    )

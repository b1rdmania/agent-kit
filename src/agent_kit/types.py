from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class JudgeSpec:
    type: str
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "JudgeSpec":
        kind = raw["type"]
        params = {k: v for k, v in raw.items() if k != "type"}
        return cls(type=kind, params=params)


@dataclass
class EvalRecord:
    id: str
    input: dict[str, Any]
    judges: list[JudgeSpec]
    tags: list[str] = field(default_factory=list)
    notes: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EvalRecord":
        return cls(
            id=raw["id"],
            input=raw.get("input", {}),
            judges=[JudgeSpec.from_dict(j) for j in raw.get("judges", [])],
            tags=raw.get("tags", []),
            notes=raw.get("notes"),
        )


@dataclass
class JudgeResult:
    spec: JudgeSpec
    passed: bool
    detail: str | None = None


@dataclass
class EvalResult:
    record: EvalRecord
    passed: bool
    duration_ms: int
    cost_usd: float | None
    judge_results: list[JudgeResult]
    error: str | None = None
    response_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunSummary:
    results: list[EvalResult]
    total_duration_ms: int
    total_cost_usd: float

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def all_passed(self) -> bool:
        return self.passed_count == self.total

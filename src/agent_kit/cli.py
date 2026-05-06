from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from rich.console import Console

from agent_kit.runner import run
from agent_kit.types import EvalResult, RunSummary

console = Console()


def _format_cost(cost: float | None) -> str:
    if cost is None:
        return "—"
    return f"${cost:.4f}"


def _print_result(r: EvalResult) -> None:
    status = "[bold green]PASS[/]" if r.passed else "[bold red]FAIL[/]"
    console.print(
        f"{status}  {r.record.id:<32} ({r.duration_ms}ms, {_format_cost(r.cost_usd)})"
    )
    if r.error:
        console.print(f"       [red]error:[/] {r.error}")
    if not r.passed:
        for jr in r.judge_results:
            if not jr.passed:
                console.print(
                    f"       [yellow]judge:[/] {jr.spec.type} {jr.spec.params}"
                )
                if jr.detail:
                    console.print(f"              {jr.detail}")


def _print_summary(summary: RunSummary) -> None:
    console.print()
    console.print(
        f"[bold]{summary.passed_count}/{summary.total} passed[/] · "
        f"total {_format_cost(summary.total_cost_usd)} · "
        f"{summary.total_duration_ms / 1000:.1f}s"
    )


def _summary_to_dict(summary: RunSummary) -> dict:
    return {
        "passed": summary.passed_count,
        "total": summary.total,
        "all_passed": summary.all_passed,
        "total_cost_usd": summary.total_cost_usd,
        "total_duration_ms": summary.total_duration_ms,
        "results": [
            {
                "id": r.record.id,
                "tags": r.record.tags,
                "passed": r.passed,
                "duration_ms": r.duration_ms,
                "cost_usd": r.cost_usd,
                "error": r.error,
                "response_metadata": r.response_metadata,
                "judges": [
                    {
                        "type": jr.spec.type,
                        "params": jr.spec.params,
                        "passed": jr.passed,
                        "detail": jr.detail,
                    }
                    for jr in r.judge_results
                ],
            }
            for r in summary.results
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-kit")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run a dataset against an HTTP agent endpoint")
    run_p.add_argument("--dataset", required=True, type=Path)
    run_p.add_argument("--endpoint", required=True)
    run_p.add_argument(
        "--secret-env",
        default=None,
        help="Env var to read the X-Agent-Kit-Secret header from",
    )
    run_p.add_argument("--timeout", type=float, default=60.0)
    run_p.add_argument(
        "--json",
        dest="json_out",
        action="store_true",
        help="Emit machine-readable JSON to stdout instead of pretty output",
    )

    args = parser.parse_args(argv)

    if args.cmd == "run":
        secret = os.environ.get(args.secret_env) if args.secret_env else None
        if args.secret_env and not secret:
            msg = f"env var {args.secret_env} not set"
            if args.json_out:
                json.dump({"error": msg}, sys.stdout)
                sys.stdout.write("\n")
            else:
                console.print(f"[red]error:[/] {msg}", style="bold")
            return 2

        if not args.json_out:
            console.print(
                f"[dim]agent-kit · {args.dataset.name} · "
                f"endpoint={args.endpoint}[/]"
            )
            console.print()

        summary = run(
            dataset_path=args.dataset,
            endpoint=args.endpoint,
            secret=secret,
            timeout_seconds=args.timeout,
        )

        if args.json_out:
            json.dump(_summary_to_dict(summary), sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            for r in summary.results:
                _print_result(r)
            _print_summary(summary)

        return 0 if summary.all_passed else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())

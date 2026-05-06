"""
Reference implementation of the agent-kit HTTP contract.

A minimal FastAPI agent that echoes input back as output and fakes
realistic metadata. Useful as a test target, a reference for new
agent authors, and the e2e test fixture.

Run:
    uvicorn examples.stub_server:app --port 8765

Then:
    agent-kit run \\
        --dataset examples/sample.jsonl \\
        --endpoint http://localhost:8765/agent \\
        --secret-env STUB_SECRET    # optional
"""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI()

EXPECTED_SECRET = os.environ.get("STUB_SECRET")


@app.post("/agent")
async def agent(
    request: Request,
    x_agent_kit_secret: str | None = Header(default=None),
) -> dict[str, Any]:
    if EXPECTED_SECRET and x_agent_kit_secret != EXPECTED_SECRET:
        raise HTTPException(status_code=401, detail="invalid secret")

    started = time.perf_counter()
    body = await request.json()
    inp = body.get("input", {}) if isinstance(body, dict) else {}

    # Reference behaviour: echo specific known fields, otherwise return the
    # input verbatim under output.echo. Real agents put their own brain here.
    if "question" in inp and inp["question"] == "what's 2+2?":
        output = {"answer": "4"}
    elif "question" in inp:
        output = {"answer": "I am a stub. Replace me with a real agent."}
    else:
        output = {"echo": inp}

    duration_ms = int((time.perf_counter() - started) * 1000)
    return {
        "output": output,
        "metadata": {
            "model": "stub-server-v0",
            "tokens": {"input": 10, "output": 5},
            "duration_ms": duration_ms,
            "cost_usd": 0.0001,
        },
    }


@app.post("/agent/broken-no-output")
async def broken_no_output() -> dict[str, Any]:
    """Demonstrates contract violation: 200 OK but no `output` key."""
    return {"metadata": {"cost_usd": 0.0001}}


@app.post("/agent/broken-error")
async def broken_error() -> dict[str, Any]:
    """Demonstrates 200 with a top-level `error` field."""
    return {
        "error": "model rejected the prompt",
        "metadata": {"cost_usd": 0.0},
    }

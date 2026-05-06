default:
    @just --list

# Run the full test suite
test:
    .venv/bin/python -m pytest

# Boot the reference stub agent on :8765
stub:
    .venv/bin/python -m uvicorn examples.stub_server:app --port 8765 --reload

# Run the sample dataset against a stub running on :8765
demo:
    .venv/bin/agent-kit run --dataset examples/sample.jsonl --endpoint http://127.0.0.1:8765/agent

# One-shot: boot stub, wait for ready, run sample, kill stub
e2e:
    #!/usr/bin/env bash
    set -euo pipefail
    .venv/bin/python -m uvicorn examples.stub_server:app --port 8765 --log-level warning &
    pid=$!
    trap "kill $pid 2>/dev/null || true" EXIT
    for _ in $(seq 1 30); do
        curl -s -o /dev/null http://127.0.0.1:8765/agent && break
        sleep 0.2
    done
    .venv/bin/agent-kit run --dataset examples/sample.jsonl --endpoint http://127.0.0.1:8765/agent

# Set up a fresh local environment
setup:
    python3.12 -m venv .venv
    .venv/bin/pip install -q -e ".[dev]"

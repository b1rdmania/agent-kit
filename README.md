# agent-kit

Personal evaluation harness for agent products. Language-neutral. Talks to agents over HTTP. v0.1.

This is the boring infrastructure layer. Trace + eval + cost monitoring, applied across every project in one standard. Not a framework — a runner, a few judges, and a contract.

## Scope

**v0.1 ships:** JSONL dataset format, HTTP runner, programmatic judges, CLI.
**v0.1 does not ship:** BaseAgent wrappers, Langfuse SDK, LLM-as-judge, prompt versioning, CI templates. Those land when a real second user demands them.

Tracing belongs in each project (Langfuse SDKs in Python and TypeScript already exist — two lines each). The kit is deliberately language-neutral: the runner posts JSON to an HTTP endpoint and grades the response. Whether the agent is FastAPI, Next.js, or a Cloudflare Worker is irrelevant.

## The HTTP contract

Every agent under evaluation exposes one endpoint. The contract is fixed across all projects and all languages so the runner is portable.

### Request

```
POST <agent endpoint>
Content-Type: application/json
X-Agent-Kit-Secret: <shared secret>     # required in prod
```

```json
{
  "input": { "...record-specific input..." },
  "trace_id": "agent-kit-<uuid>",
  "metadata": {
    "record_id": "apr-16-pattern-id-bug",
    "source": "agent-kit-runner",
    "tags": ["regression", "session-planner"]
  }
}
```

### Response

```json
{
  "output": { "...whatever the agent produces..." },
  "metadata": {
    "model": "claude-sonnet-4-6-20260315",
    "tokens": { "input": 1234, "output": 567 },
    "duration_ms": 842,
    "cost_usd": 0.0034,
    "trace_url": "https://cloud.langfuse.com/.../traces/..."
  }
}
```

`output` is the only field the runner asserts against. `metadata` is captured for the report but never graded.

### What counts as a pass

The runner only considers a record passed when **all** of the following hold:

1. HTTP 2xx response.
2. Body is a JSON object (not array, not scalar).
3. Body contains an `output` key (its value may be `null`, but the key must exist).
4. Every judge in the record returns `passed: true`.

Anything else is a fail. `cost_usd` is captured regardless so spend is tracked even on contract violations or agent-side errors.

### Error response shape

When the agent fails internally, return HTTP 5xx **or** HTTP 200 with this shape:

```json
{ "error": "human-readable description", "metadata": { "cost_usd": 0.0001, "...": "..." } }
```

The runner treats both as a failure. Returning 200 + `error` is preferred when the agent ran the model but rejected the result, because it lets cost telemetry flow through unchanged.

## Dataset format (JSONL, one record per line)

```json
{
  "id": "apr-16-pattern-id-bug",
  "tags": ["session-planner", "regression"],
  "input": { "userId": "...", "patternScores": { "je-voudrais": 65 } },
  "judges": [
    { "type": "not_null", "path": "output.targetPattern" },
    { "type": "key_equals", "path": "output.targetPattern", "value": "je-voudrais" },
    { "type": "key_present", "path": "output.targetVocab" }
  ],
  "notes": "Apr 16 prod regression: planner looked up phrase ids in FALLBACK_PATTERNS with mismatched ids. Silent null targetPattern for ~4 days."
}
```

`expected` is *not* a field. Use explicit judges instead — they declare *what* is being asserted, not just *what value* was returned. Prevents silent test rot when output shape evolves.

## Judges (v0.1)

All deterministic. No LLM calls.

| type | params | passes when |
|---|---|---|
| `not_null` | `path` | path resolves to a non-null value |
| `key_present` | `path` | path resolves (any value, including null) |
| `key_equals` | `path`, `value` | path resolves and equals `value` |
| `key_in` | `path`, `values` | path value is in `values` list |
| `regex_match` | `path`, `pattern` | path is a string matching the regex |
| `length_bounds` | `path`, `min?`, `max?` | path is string/list with length in bounds |
| `schema_valid` | `schema` | full output validates against a JSON Schema |

`path` uses dotted notation (`output.targetPattern`, `output.cards.0.front`). Lists are indexed numerically.

## Usage

```bash
pip install git+https://github.com/b1rdmania/agent-kit.git@main

agent-kit run \
  --dataset decipher/evals/session_planner.jsonl \
  --endpoint https://decipher-two.vercel.app/api/internal/eval/session-planner \
  --secret-env INTERNAL_API_SECRET

# CI-friendly machine-readable output:
agent-kit run --dataset ... --endpoint ... --json > results.json
```

Output:

```
agent-kit · session_planner.jsonl · 5 records · endpoint=https://...

PASS  apr-16-pattern-id-bug          (842ms, $0.0034)
PASS  happy-path-due-vocab           (612ms, $0.0021)
FAIL  weak-pattern-priority          (701ms, $0.0028)
       judge: key_equals output.targetPattern
       expected: "ne-pas"
       got:      "c-est"
PASS  no-due-cards-fallback          (590ms, $0.0019)
PASS  rude-mode-excluded             (488ms, $0.0014)

4/5 passed · total $0.0116 · 3.2s
```

Exit code: 0 if all pass, 1 if any fail.

## Workflow

1. Bug or surprise hits prod.
2. Pull the failing trace from Langfuse.
3. Add a record to the relevant `evals/<agent>.jsonl` with judges that would have caught it.
4. Fix the agent. Eval now passes. Future regressions blocked.

The dataset *is* the asset. The runner is incidental.

## Try it locally

```bash
git clone https://github.com/b1rdmania/agent-kit
cd agent-kit
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Boot the reference stub agent:
uvicorn examples.stub_server:app --port 8765 &

# Run the sample dataset against it:
agent-kit run --dataset examples/sample.jsonl --endpoint http://localhost:8765/agent

# Run the test suite:
pytest
```

The stub server in `examples/stub_server.py` is the canonical reference implementation of the contract — copy its shape when wiring agent-kit into a new project.

## License

MIT.

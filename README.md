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

Errors: HTTP non-2xx is an automatic fail. The agent should still return JSON `{ "error": "...", "metadata": {...} }` so cost is captured even on failure.

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

## License

MIT.

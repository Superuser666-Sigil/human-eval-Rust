# ADR-004: Enhanced Result Schema for Auditability

## Status

Accepted

## Context

The original HumanEval result schema was minimal:

```json
{
  "task_id": "HumanEval/0",
  "completion": "...",
  "passed": true,
  "result": "passed"
}
```

This schema lacked detail for:

1. **Debugging failures**: Why did a completion fail?
2. **Distinguishing failure modes**: Compile error vs runtime error vs test failure
3. **Infrastructure issues**: Toolchain missing vs code bug
4. **Rust-specific metrics**: Compile rate, Clippy pass rate
5. **Performance analysis**: Compile time, binary size

For production model evaluation, we needed to:
- Never drop completions silently
- Distinguish infrastructure failures from code failures
- Track Rust-specific quality metrics
- Enable post-hoc analysis of failure patterns

## Decision

Implement an **enhanced result schema** with explicit fields for each failure mode:

```json
{
  "task_id": "HumanEval/0",
  "completion": "...",
  "completion_id": 0,
  "compile_ok": true,
  "test_ok": true,
  "clippy_ok": true,
  "compile_time_ms": 1234,
  "binary_size_bytes": 56789,
  "error_type": null,
  "stderr": "",
  "main_free": true,
  "passed": true,
  "result": "passed"
}
```

**Field definitions:**

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | string | Problem identifier |
| `completion` | string | Model-generated code |
| `completion_id` | int | Sample index for pass@k |
| `compile_ok` | bool | Did rustc succeed? |
| `test_ok` | bool | Did tests pass? |
| `clippy_ok` | bool | Did Clippy pass? |
| `compile_time_ms` | int | Compilation duration |
| `binary_size_bytes` | int | Binary size |
| `error_type` | string | Error category |
| `stderr` | string | Error output |
| `main_free` | bool | No fn main() present? |
| `passed` | bool | Overall success |
| `result` | string | Human-readable result |

**Error types:**
- `infra_missing_toolchain`: rustc not available
- `compile_error`: Code failed to compile
- `runtime_error`: Code crashed during execution
- `assertion_failure`: Tests failed

## Consequences

### Positive

- **Complete auditability**: Every completion has explicit status
- **Failure analysis**: Can categorize and fix model failure patterns
- **Rust-specific metrics**: Compile rate, Clippy pass rate tracked
- **Performance insights**: Compile time helps identify complex code
- **No silent drops**: Infrastructure failures explicitly recorded
- **Rule Zero compliance**: Full audit trail for trust

### Negative

- **Larger result files**: More data per result
- **Schema versioning**: Old consumers may not understand new fields
- **Processing overhead**: More fields to populate

### Neutral

- **Backward compatible**: `passed` and `result` still work for simple consumers
- **Optional metrics**: `clippy_ok`, `compile_time_ms` may be null

## Alternatives Considered

### Alternative 1: Flat Error String

Keep simple schema with detailed error in `result` field.

**Rejected because:**
- Can't easily filter/aggregate by error type
- No structured data for analysis
- String parsing is fragile

### Alternative 2: Nested Error Object

Use nested structure: `{"error": {"type": "...", "message": "..."}}`

**Rejected because:**
- More complex to consume
- Flat structure is easier to write to JSONL
- No clear benefit for our use case

### Alternative 3: Separate Metrics File

Write metrics to separate file from results.

**Rejected because:**
- Harder to correlate metrics with specific completions
- More files to manage
- Risk of desync between files

## Related

- [ADR-005](ADR-005-deterministic-compilation.md) - Reproducibility context
- [human_eval/rust_execution.py](../../human_eval/rust_execution.py) - Schema implementation
- [human_eval/evaluation.py](../../human_eval/evaluation.py) - Metrics aggregation


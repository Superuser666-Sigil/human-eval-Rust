# ADR-008: Separate Timeout Budgets for Compilation and Testing

## Status

Accepted

## Context

The original implementation used a single shared timeout for all phases (compile + clippy + test):

```python
with time_limit(timeout) as timed_out:
    compile_result = subprocess.run(..., timeout=timeout)
    clippy_result = subprocess.run(..., timeout=timeout)
    test_result = subprocess.run(..., timeout=timeout)
```

This created several problems:

1. **Budget starvation**: If compilation takes 0.9 × timeout, tests have almost no time left
2. **Poor visibility**: Can't distinguish "compile timeout" from "test timeout"
3. **Unfair evaluation**: Complex code pays double penalty (slow compile + less test time)
4. **Misleading metrics**: Single "timeout" error doesn't indicate where failure occurred
5. **Inflexible**: Can't tune timeouts per phase based on hardware characteristics

On H100 GPU instances:
- Compilation takes 2-8 seconds (cold cache, network filesystem)
- Tests typically complete in <1 second
- 10-second shared budget meant slow compiles would timeout during tests

## Decision

Implement **separate timeout budgets** for each execution phase:

```python
def rust_check_correctness(
    problem: dict,
    completion: str,
    timeout: float,                    # Default fallback
    compile_timeout: float | None = None,   # Dedicated compile budget
    run_timeout: float | None = None,       # Dedicated test budget
    clippy_timeout: float | None = None,    # Dedicated clippy budget
    ...
):
```

**Key design principles:**

1. **Independent budgets**: Each phase gets its own dedicated time
2. **Graceful defaults**: If phase timeout not specified, falls back to `timeout`
3. **Process watchdog**: Total time budget = sum of all phases + 2 second grace period
4. **Specific error types**: Distinguish `compile_timeout`, `test_timeout`, `clippy_timeout`
5. **No outer time_limit**: Remove shared timer, use per-subprocess timeouts

**Implementation:**

```python
# Set defaults
compile_timeout = compile_timeout or timeout
run_timeout = run_timeout or timeout
clippy_timeout = clippy_timeout or compile_timeout

# Process watchdog
watchdog_timeout = compile_timeout + run_timeout + clippy_timeout + 2

# Each phase uses its own timeout
compile_result = subprocess.run(..., timeout=compile_timeout)
test_result = subprocess.run(..., timeout=run_timeout)
```

**Error handling:**

```python
except subprocess.TimeoutExpired as e:
    if "rustc" in str(e.cmd):
        result_dict["error_type"] = "compile_timeout"
        result_dict["stderr"] = f"compilation timed out after {compile_timeout}s"
    else:
        result_dict["error_type"] = "test_timeout"
        result_dict["stderr"] = f"test execution timed out after {run_timeout}s"
```

## Consequences

### Positive

- **Fair evaluation**: Slow compilation doesn't penalize test execution
- **Better diagnostics**: Know exactly which phase timed out
- **Tunable performance**: Can optimize timeouts for different hardware
- **Actionable failures**: "compile_timeout" → likely complex code; "test_timeout" → likely infinite loop
- **Realistic budgets**: H100 can use compile_timeout=8s, run_timeout=5s
- **Backward compatible**: Single `timeout` still works as before

### Negative

- **More parameters**: API surface increased (though all optional)
- **Potential confusion**: Users may not understand which timeout to use
- **Process watchdog**: Can timeout even if no individual phase timeout (rare edge case)

### Neutral

- **Documentation needed**: Must explain timeout behavior clearly
- **Breaking change**: Old behavior (shared budget) no longer applies when using new parameters
- **CLI unchanged**: Default behavior with single timeout still works

## Example Usage

**Default (backward compatible):**
```python
rust_check_correctness(problem, completion, timeout=10.0)
# All phases share 10-second budget
```

**Tuned for H100:**
```python
rust_check_correctness(
    problem, completion,
    timeout=10.0,           # Fallback
    compile_timeout=8.0,    # Cold compilation on network FS
    run_timeout=5.0,        # Tests are fast
    clippy_timeout=6.0,     # Lint checks
)
# Total wall-clock budget: 8 + 5 + 6 + 2 = 21 seconds max
```

**Skip clippy on slow systems:**
```python
rust_check_correctness(
    problem, completion,
    timeout=3.0,
    compile_timeout=3.0,
    run_timeout=3.0,
    clippy_timeout=0.5,  # Fast fail if cargo slow
)
```

## Alternatives Considered

### Alternative 1: Keep Shared Timeout, Document Better

Just document that timeout is total budget.

**Rejected because:**
- Doesn't solve budget starvation problem
- Still can't distinguish timeout sources
- Poor user experience on slow-compile systems

### Alternative 2: Multiplier-Based Timeouts

Use compile_timeout_multiplier instead of absolute values.

**Rejected because:**
- Less intuitive for users
- Harder to reason about total time
- Doesn't help with baseline being wrong

### Alternative 3: Adaptive Timeouts

Measure first N compilations, adjust dynamically.

**Rejected because:**
- Complex implementation
- Unpredictable behavior
- First few completions would be sacrificed to calibration

## Migration Notes

**For users:**
- Old code continues working (single `timeout` parameter)
- New parameters are optional
- To use old behavior exactly: set all three timeouts equal to `timeout`

**For implementers:**
- Remove `time_limit()` wrapper in `_rust_unsafe_execute`
- Pass timeout parameters through multiprocessing boundary
- Update error messages to include which timeout was exceeded

## Related

- [ADR-003](ADR-003-thread-safe-timeout.md) - Thread-safe timeout mechanism
- [ADR-004](ADR-004-enhanced-result-schema.md) - Error type schema (extended with new timeout types)
- [human_eval/rust_execution.py](../../human_eval/rust_execution.py) - Implementation
- [docs/runbooks/evaluation-execution.md](../runbooks/evaluation-execution.md) - Usage guidance

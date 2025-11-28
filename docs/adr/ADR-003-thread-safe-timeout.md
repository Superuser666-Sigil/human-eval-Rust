# ADR-003: Thread-Safe Timeout Implementation

## Status

Accepted

## Context

The original HumanEval Python implementation used signal-based timeouts:

```python
import signal

def timeout_handler(signum, frame):
    raise TimeoutException("Timed out!")

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(timeout_seconds)
```

This approach had several problems:

1. **Not thread-safe**: `signal.alarm` only works in the main thread
2. **Unix-only**: `SIGALRM` doesn't exist on Windows
3. **Race conditions**: Signal delivery timing is unpredictable
4. **Process isolation issues**: Signals don't cross process boundaries cleanly

When running evaluations in parallel with `ThreadPoolExecutor`, signal-based timeouts caused:
- `ValueError: signal only works in main thread`
- Unpredictable timeout behavior
- Zombie processes when signal handlers failed

## Decision

Implement a **thread-safe timeout mechanism** using `threading.Timer` and `threading.Event`:

```python
@contextlib.contextmanager
def time_limit(seconds: float):
    """Thread-safe timeout context manager using Timer."""
    timed_out = threading.Event()

    def timeout_handler():
        timed_out.set()

    timer = threading.Timer(seconds, timeout_handler)
    timer.start()
    try:
        yield timed_out
    finally:
        if timer:
            timer.cancel()

    if timed_out.is_set():
        raise TimeoutException("Timed out!")
```

Key characteristics:
- **Cooperative**: Callers check `timed_out.is_set()` during long operations
- **Cross-platform**: Works on Windows, Linux, macOS
- **Thread-safe**: Can be used in any thread
- **Deterministic cleanup**: Timer cancelled in finally block

## Consequences

### Positive

- **Works with ThreadPoolExecutor**: Parallel evaluation now reliable
- **Cross-platform**: Same code on Windows and Unix
- **No race conditions**: Event-based signaling is predictable
- **Proper cleanup**: Timer always cancelled, no resource leaks
- **Testable**: Easy to unit test timeout behavior

### Negative

- **Cooperative checking required**: Long-running code must check the event
- **Not preemptive**: Can't forcibly interrupt stuck code
- **Slight overhead**: Timer thread created per timeout context

### Neutral

- **API change**: Callers yield an event, not raise immediately
- **Process timeout still needed**: For stuck subprocesses, use `subprocess.Popen.wait(timeout)`

## Alternatives Considered

### Alternative 1: multiprocessing.Process with Timeout

Spawn a separate process and kill it on timeout.

**Rejected because:**
- Already using multiprocessing for isolation
- Nested multiprocessing adds complexity
- Process spawn overhead is significant
- Still need thread-safe timeout for subprocess monitoring

### Alternative 2: asyncio Timeouts

Use `asyncio.wait_for()` with async execution.

**Rejected because:**
- Would require rewriting entire execution pipeline
- Sync subprocess calls still needed
- Adds complexity without clear benefit
- Not all operations are naturally async

### Alternative 3: concurrent.futures Timeout

Use `future.result(timeout=seconds)`.

**Rejected because:**
- Only works for the overall future, not fine-grained control
- Need to timeout individual operations (compile, run)
- Less control over cleanup behavior

## Related

- [ADR-001](ADR-001-firejail-first-sandboxing.md) - Process isolation context
- [human_eval/execution.py](../../human_eval/execution.py) - Implementation
- Python threading documentation: https://docs.python.org/3.12/library/threading.html


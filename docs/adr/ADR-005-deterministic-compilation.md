# ADR-005: Deterministic Compilation for Reproducibility

## Status

Accepted

## Context

Rust compilation produces different results based on:

1. **Compiler version**: Different rustc versions produce different binaries
2. **Optimization level**: `-O` flags affect timing and binary size
3. **Debug info**: Debug symbols affect binary size
4. **Incremental compilation**: Can cause non-deterministic behavior
5. **Host environment**: Build paths embedded in debug info

For reproducible benchmarking, we needed:
- Consistent compile times across runs
- Comparable binary sizes
- Version tracking for result interpretation
- Isolation from host environment effects

## Decision

Implement **deterministic compilation settings** for all evaluations:

```python
DETERMINISTIC_RUSTC_FLAGS = [
    "--edition=2021",     # Fixed Rust edition
    "--test",             # Build as test binary
    "-C", "opt-level=0",  # No optimization (consistent timing)
    "-C", "debuginfo=0",  # No debug info (consistent size)
    "-C", "incremental=false",  # Disable incremental (deterministic)
]
```

Additionally:
- Capture rustc version in evaluation metadata
- Use `--edition=2021` for modern Rust features
- Disable optimizations to measure code quality, not compiler ability

**Version capture:**
```python
def _get_rustc_version() -> str:
    result = subprocess.run(["rustc", "--version"], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else "unknown"
```

## Consequences

### Positive

- **Reproducible results**: Same code produces same metrics
- **Fair comparison**: All completions compiled identically
- **Binary size meaningful**: Reflects code complexity, not optimization
- **Compile time meaningful**: Reflects code complexity, not cache state
- **Version tracking**: Results can be interpreted with toolchain context

### Negative

- **Slower compilation**: No optimization means larger, slower binaries
- **Test execution slower**: Unoptimized binaries run slower
- **May miss optimization bugs**: Code that only fails with optimization enabled

### Neutral

- **Edition fixed at 2021**: May need update as new editions release
- **Debug symbols removed**: Can't debug test failures with debugger

## Alternatives Considered

### Alternative 1: Default Compiler Flags

Use rustc defaults without explicit flags.

**Rejected because:**
- Different rustc versions have different defaults
- Incremental compilation causes non-determinism
- Results not comparable across environments

### Alternative 2: Optimized Builds

Use `-O` or `-O2` for realistic performance.

**Rejected because:**
- Optimization introduces non-determinism
- Compile times vary more with optimization
- We're measuring code correctness, not performance

### Alternative 3: Release Profile

Use `--release` for production-like builds.

**Rejected because:**
- Longer compile times increase evaluation cost
- Optimization can mask or introduce bugs
- Inconsistent with test binary expectations

## Related

- [ADR-004](ADR-004-enhanced-result-schema.md) - Metrics that depend on determinism
- [human_eval/rust_execution.py](../../human_eval/rust_execution.py) - Flag implementation
- Rust edition guide: https://doc.rust-lang.org/edition-guide/


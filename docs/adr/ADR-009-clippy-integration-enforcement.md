# ADR-009: Clippy Integration and Enforcement Modes

## Status

Accepted

## Context

Clippy (Rust's official linter) detects code quality issues beyond what the compiler catches. The original implementation attempted to run clippy but had a critical flaw:

```python
def _run_clippy_check(source_path: str, timeout: float) -> tuple[bool, str]:
    result = subprocess.run(
        ["cargo", "clippy", "--", "-D", "warnings"],
        cwd=os.path.dirname(source_path),  # Problem: no Cargo.toml!
        ...
    )
```

**Problems:**

1. **Always failed**: Temp dirs contained only `solution.rs`, no `Cargo.toml`
2. **Misleading metrics**: `clippy_ok=False` recorded even for valid code
3. **No enforcement**: Clippy failures never blocked completions
4. **Silent degradation**: Errors swallowed, no visibility into why clippy failed

This meant:
- "We run clippy on completions" was factually incorrect
- Clippy metrics were meaningless
- No way to enforce code quality standards
- Documentation claimed features that didn't work

## Decision

Implement **working clippy integration** with **two enforcement modes**:

### 1. Fix Clippy Execution

Create minimal `Cargo.toml` when missing:

```python
def _run_clippy_check(source_path: str, timeout: float) -> tuple[bool, str]:
    cargo_toml_path = os.path.join(os.path.dirname(source_path), "Cargo.toml")
    
    if not os.path.exists(cargo_toml_path):
        # Create minimal Cargo.toml for temp directory
        minimal_cargo_toml = f'''[package]
name = "temp_eval"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "{binary_name}"
path = "{source_filename}"
'''
        with open(cargo_toml_path, "w") as f:
            f.write(minimal_cargo_toml)
    
    result = subprocess.run(
        ["cargo", "clippy", "--", "-D", "warnings"],
        cwd=os.path.dirname(source_path),
        ...
    )
```

### 2. Add Enforcement Parameter

```python
def rust_check_correctness(
    problem: dict,
    completion: str,
    timeout: float,
    clippy_required: bool = False,  # NEW: Enforcement mode
    ...
):
```

**Two modes:**

| Mode | `clippy_required` | Behavior |
|------|------------------|----------|
| **Advisory** | `False` (default) | Clippy failures recorded in `clippy_ok` but don't fail completion. For metrics/observability. |
| **Required** | `True` | Clippy failures block completion with `error_type="lint_failure"`. For quality gates. |

**Error handling:**

```python
if not clippy_ok and clippy_required:
    if "infra:" in clippy_stderr:
        result_dict["error_type"] = "infra_missing_linter"
        result_dict["stderr"] = clippy_stderr
    else:
        result_dict["error_type"] = "lint_failure"
        result_dict["stderr"] = clippy_stderr
    return  # Block completion
elif not clippy_ok:
    # Advisory mode: record but continue
    result_dict["stderr"] = clippy_stderr
```

**Infrastructure detection:**

- `infra_missing_linter`: cargo not found, Cargo.toml creation failed
- `lint_failure`: Code has actual lint issues

## Consequences

### Positive

- **Actually works**: Clippy now runs and produces meaningful results
- **Two valid modes**: Research (advisory) and production (required)
- **Better metrics**: `clippy_ok` field is now accurate
- **Clear semantics**: Infrastructure errors vs code issues distinguished
- **Backward compatible**: Default is advisory (no behavior change)
- **Quality gates**: Can enforce "no warnings" policy in CI/CD

### Negative

- **Temp file creation**: Adds Cargo.toml, slightly more I/O
- **Cleanup needed**: Must remove created Cargo.toml (best effort)
- **Cargo dependency**: Required mode needs cargo installed

### Neutral

- **Per-task policy**: Could add problem-level `clippy_required` metadata (future)
- **Custom lint rules**: Could add `clippy.toml` support (future)

## Example Usage

**Research mode (default):**
```python
result = rust_check_correctness(problem, completion, timeout=10.0)
# result["clippy_ok"] shows if lints passed, but result["passed"] only checks tests
```

**Production quality gate:**
```python
result = rust_check_correctness(
    problem, completion,
    timeout=10.0,
    clippy_required=True  # Lint failures block completion
)
# result["passed"] will be False if clippy fails
```

**CLI usage:**
```bash
# Research: metrics only
evaluate_functional_correctness samples.jsonl

# Production: enforce quality
evaluate_functional_correctness samples.jsonl --clippy-required
```

## Alternatives Considered

### Alternative 1: Skip Clippy in Temp Dirs

Only run clippy when proper workspace exists.

**Rejected because:**
- Metrics would be inconsistent (some have clippy, some don't)
- Can't enforce quality on standard evaluation
- User confusion about when clippy runs

### Alternative 2: Always Enforce Clippy

Make `clippy_required=True` the default.

**Rejected because:**
- Breaking change for HumanEval compatibility
- Research evaluations want functional correctness only
- Too opinionated for default behavior

### Alternative 3: Separate Linting Pass

Run clippy as separate evaluation step.

**Rejected because:**
- Duplicate compilation overhead
- Harder to correlate lint issues with specific completions
- More complex workflow

## Migration Notes

**For researchers:**
- No action needed
- Clippy now actually runs, `clippy_ok` field is accurate
- `passed` still only checks test results

**For production:**
- Add `--clippy-required` flag to enforce quality
- Update CI/CD to handle `lint_failure` error type
- Consider if this breaks existing pipelines (completions that passed before may fail now)

**For implementers:**
- `_run_clippy_check` now creates/cleans up Cargo.toml
- New error type: `lint_failure`
- Distinguish infra errors from code issues

## Related

- [ADR-004](ADR-004-enhanced-result-schema.md) - Error type schema (extended with `lint_failure`)
- [ADR-008](ADR-008-separate-timeout-budgets.md) - Clippy timeout handling
- [human_eval/rust_execution.py](../../human_eval/rust_execution.py) - Implementation
- Clippy documentation: https://doc.rust-lang.org/clippy/

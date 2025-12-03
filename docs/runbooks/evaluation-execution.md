# Runbook: Evaluation Execution

## Overview

Step-by-step guide for running HumanEval Rust evaluations.

## Prerequisites

- [ ] Python 3.12.10+ installed
- [ ] Rust toolchain installed (`rustc --version`)
- [ ] human-eval-rust installed (`pip install human-eval-rust`)
- [ ] Firejail installed (Linux, recommended)
- [ ] Samples file in JSONL format

## Steps

### 1. Verify Environment

```bash
# Check Python
python --version

# Check Rust
rustc --version
cargo --version

# Check Firejail (Linux)
firejail --version

# Check human-eval-rust
evaluate_functional_correctness --help
```

### 2. Validate Samples Format

Ensure samples file has correct format:
```json
{"task_id": "HumanEval/0", "completion": "fn add(a: i32, b: i32) -> i32 { a + b }"}
{"task_id": "HumanEval/1", "completion": "..."}
```

```bash
# Check first few lines
head -3 samples.jsonl

# Count samples
wc -l samples.jsonl
```

### 3. Run Quick Test

```bash
# Test with example data first
evaluate_functional_correctness data/example_rust_samples.jsonl \
    --problem_file=data/example_rust_problem.jsonl
```

Expected output: `{'pass@1': 0.5}`

### 4. Run Full Evaluation

```bash
# Default settings (24 workers, advisory clippy, no sandbox enforcement)
evaluate_functional_correctness samples.jsonl

# Custom timeout budgets (separate for compile/test/clippy)
evaluate_functional_correctness samples.jsonl \
    --compile-timeout=15.0 \
    --run-timeout=10.0 \
    --clippy-timeout=10.0

# Quality gate mode (enforce clippy, require sandbox)
evaluate_functional_correctness samples.jsonl \
    --clippy-required \
    --require-sandbox

# H100 tuning (faster compilation)
evaluate_functional_correctness samples.jsonl \
    --compile-timeout=5.0 \
    --run-timeout=5.0 \
    --clippy-timeout=5.0 \
    --n_workers=32

# Full control
evaluate_functional_correctness samples.jsonl \
    --k=1,10,100 \
    --n_workers=8 \
    --compile-timeout=20.0 \
    --run-timeout=15.0 \
    --clippy-timeout=10.0 \
    --clippy-required \
    --sandbox-mode=firejail \
    --require-sandbox
```

**Parameter reference:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--compile-timeout` | 10.0 | Seconds for `rustc` compilation |
| `--run-timeout` | 10.0 | Seconds for test execution |
| `--clippy-timeout` | 10.0 | Seconds for clippy linting |
| `--clippy-required` | False | Lint failures block completion |
| `--require-sandbox` | False | Firejail required (no fallback) |
| `--n_workers` | 24 | Parallel workers |
| `--k` | "1,10,100" | pass@k values to compute |

See [ADR-008](../adr/ADR-008-separate-timeout-budgets.md) for timeout budget rationale.

### 5. Monitor Progress

- Progress bar shows samples processed
- Estimated time remaining
- Watch for error messages

### 6. Collect Results

Results are written to `samples.jsonl_results.jsonl`:

```bash
# Check results file exists
ls -la samples.jsonl_results.jsonl

# View pass@k metrics (printed to stdout)
# View per-sample results
head -5 samples.jsonl_results.jsonl | python -m json.tool
```

## Verification

- [ ] Results file created
- [ ] All samples have results (no silent drops)
- [ ] pass@k metrics printed
- [ ] compile_rate and main_free_rate reasonable

## Rollback

If evaluation fails mid-run:
- Results file may be incomplete
- Re-run from scratch (no resume support)
- Check for zombie processes: `ps aux | grep rustc`

## Troubleshooting

### Evaluation hangs

```bash
# Kill stuck processes
pkill -9 rustc
pkill -9 firejail

# Reduce workers
evaluate_functional_correctness samples.jsonl --n_workers=4
```

### Memory exhausted

```bash
# Reduce parallel workers
evaluate_functional_correctness samples.jsonl --n_workers=4

# Free memory before running
```

### Firejail permission errors

```bash
# Check Firejail is installed
which firejail

# Run without sandbox (unsafe, local dev only)
evaluate_functional_correctness samples.jsonl \
    --sandbox-mode=none --allow-no-sandbox
```


# Runbook: SigilDERG Pipeline Ingestion

## Overview

This runbook covers the process of ingesting data from `sigil-pipeline` (SigilDERG Data Production) and transforming it into HumanEval-compatible benchmark tasks. The pipeline generates tasks across four categories: CodeGen (45%), Transform (25%), Fix (20%), and Explain (10%).

## Prerequisites

- [ ] Python 3.10+ installed
- [ ] Virtual environment activated (`.venv`)
- [ ] `sigil-pipeline>=2.4.0` installed (`pip install sigil-pipeline`)
- [ ] Rust toolchain installed (for optional workspace scaffolding validation)
- [ ] Input data file from `sigil-pipeline` (JSONL format with `{"prompt": "...", "gen": "..."}` structure)

### Verify Prerequisites

```powershell
# Check Python version
python --version

# Check sigil-pipeline installation
pip show sigil-pipeline

# Check Rust toolchain (optional, for hardening)
rustc --version
cargo --version
```

## Steps

### 1. Prepare Input Data

Ensure your `sigil-pipeline` output is in the expected format:

```json
{"prompt": "Write a Rust code snippet. Output only the code.", "gen": "pub fn example() -> i32 { ... }"}
```

Place the file in `data/` directory (e.g., `data/sigil_phase2_dataset.jsonl`).

### 2. Run Ingestion Pipeline

#### Basic Ingestion (with Ratio Enforcement)

By default, output tasks are selected to match the target category ratios (45% CodeGen, 25% Transform, 20% Fix, 10% Explain):

```powershell
cd D:\human-eval-Rust
.\.venv\Scripts\python.exe scripts/process_sigil_dataset.py `
    --input data/sigil_phase2_dataset.jsonl `
    --output data/HumanEval_rust_sigil.jsonl
```

#### Without Ratio Enforcement (All Tasks)

To include all successfully generated tasks without ratio filtering:

```powershell
.\.venv\Scripts\python.exe scripts/process_sigil_dataset.py `
    --input data/sigil_phase2_dataset.jsonl `
    --output data/HumanEval_rust_sigil.jsonl `
    --no-enforce-ratios
```

#### With Custom Category Ratios

```powershell
.\.venv\Scripts\python.exe scripts/process_sigil_dataset.py `
    --input data/sigil_phase2_dataset.jsonl `
    --output data/HumanEval_rust_sigil.jsonl `
    --category-ratios '{"codegen": 0.50, "transform": 0.25, "fix": 0.15, "explain": 0.10}'
```

#### With Workspace Scaffolding (for Hardening)

```powershell
.\.venv\Scripts\python.exe scripts/process_sigil_dataset.py `
    --input data/sigil_phase2_dataset.jsonl `
    --output data/HumanEval_rust_sigil.jsonl `
    --scaffold-workspace bench_workspace
```

#### Dependency Detection Options (v2.5.0+)

The workspace scaffolding system automatically detects external crate dependencies in your code and can add them to the workspace `Cargo.toml`.

**Interactive mode (default):**
```powershell
# Prompts for approval of detected dependencies
.\.venv\Scripts\python.exe scripts/process_sigil_dataset.py `
    --input data/sigil_phase2_dataset.jsonl `
    --scaffold-workspace bench_workspace
```

**Auto-approve all detected dependencies:**
```powershell
.\.venv\Scripts\python.exe scripts/process_sigil_dataset.py `
    --input data/sigil_phase2_dataset.jsonl `
    --scaffold-workspace bench_workspace `
    --auto-deps
```

**Skip dependency detection entirely:**
```powershell
.\.venv\Scripts\python.exe scripts/process_sigil_dataset.py `
    --input data/sigil_phase2_dataset.jsonl `
    --scaffold-workspace bench_workspace `
    --no-deps
```

**Detected Crates Registry:**
The system recognizes 15+ common Rust crates including:
- `rocket`, `tokio`, `serde`, `serde_json`
- `figment`, `async-trait`, `futures`
- `chrono`, `time`, `cookie`, `hyper`, `reqwest`

Unrecognized imports are reported but not added automatically.

#### Automated Hardening (v2.5.0+)

Run the complete hardening pipeline automatically after scaffolding:

```powershell
.\.venv\Scripts\python.exe scripts/process_sigil_dataset.py `
    --input data/sigil_phase2_dataset.jsonl `
    --scaffold-workspace bench_workspace `
    --auto-deps `
    --run-hardening
```

This executes all 4 hardening steps in sequence:
1. `cargo fmt` - Format code
2. `cargo check --all --tests` - Type checking
3. `cargo clippy --all --tests -- -D warnings -W clippy::pedantic -W clippy::nursery` - Linting
4. `cargo test --all` - Run tests

**Partial hardening (skip slow steps):**
```powershell
# Skip clippy (faster)
--run-hardening --skip-clippy

# Skip tests (for syntax validation only)
--run-hardening --skip-tests

# Skip both (fmt + check only)
--run-hardening --skip-clippy --skip-tests
```

### 3. Verify Output

```powershell
.\.venv\Scripts\python.exe -c "
import json
tasks = [json.loads(l) for l in open('data/HumanEval_rust_sigil.jsonl')]
print(f'Total tasks: {len(tasks)}')
cats = {}
for t in tasks:
    c = t.get('category', 'unknown')
    cats[c] = cats.get(c, 0) + 1
for c, n in sorted(cats.items()):
    print(f'  {c}: {n} ({n/len(tasks)*100:.1f}%)')
"
```

Expected output shows task distribution across categories.

### 4. Run Hardening Pipeline

**Option A: Automated (Recommended)**

Use `--run-hardening` flag during scaffolding (see above) to automatically run all steps.

**Option B: Manual**

If you scaffolded without `--run-hardening`, validate the generated code manually:

```powershell
cd bench_workspace

# Format code
cargo fmt

# Type checking
cargo check --all --tests

# Clippy linting (strict mode)
cargo clippy --all --tests -- -D warnings -W clippy::pedantic -W clippy::nursery

# Run tests
cargo test --all
```

**Option C: Programmatic**

Use the `run_hardening()` function directly:

```python
from human_eval.workspace_scaffold import run_hardening

result = run_hardening("bench_workspace", verbose=True)
print(result.format_report())

if result.all_passed:
    print("Ready for production!")
```

See [Rust 2024 Benchmark Hardening Pipeline](../../rust_2024_benchmark_hardening_pipeline.md) for full quality validation steps.

### 5. Merge with Existing Dataset (Optional)

To combine with the main HumanEval_rust.jsonl:

```powershell
.\.venv\Scripts\python.exe -c "
import json
from pathlib import Path

# Load existing
existing = [json.loads(l) for l in open('data/HumanEval_rust.jsonl')]
existing_ids = {t['task_id'] for t in existing}

# Load new (skip duplicates)
new_tasks = []
for line in open('data/HumanEval_rust_sigil.jsonl'):
    task = json.loads(line)
    if task['task_id'] not in existing_ids:
        new_tasks.append(task)

print(f'Existing: {len(existing)}, New: {len(new_tasks)}')

# Merge and write
combined = existing + new_tasks
with open('data/HumanEval_rust_combined.jsonl', 'w') as f:
    for task in combined:
        f.write(json.dumps(task) + '\n')
print(f'Combined: {len(combined)} tasks written')
"
```

## Verification

After ingestion, verify:

- [ ] Output file exists and is valid JSONL
- [ ] All tasks have required fields: `task_id`, `prompt`, `test`, `entry_point`, `source`, `category`
- [ ] Task IDs are in hash format: `Category/[a-f0-9]{12}`
- [ ] Source field is set to `sigil-pipeline`
- [ ] No duplicate task IDs
- [ ] Category distribution matches target ratios (within tolerance)

```powershell
# Quick validation
.\.venv\Scripts\python.exe -c "
import json, re
tasks = [json.loads(l) for l in open('data/HumanEval_rust_sigil.jsonl')]
errors = []

for t in tasks:
    if not all(k in t for k in ['task_id', 'prompt', 'test', 'entry_point', 'source', 'category']):
        errors.append(f'Missing fields: {t.get(\"task_id\", \"UNKNOWN\")}')
    if not re.match(r'^(CodeGen|Transform|Fix|Explain)/[a-f0-9]{12}$', t.get('task_id', '')):
        errors.append(f'Bad ID format: {t.get(\"task_id\")}')
    if t.get('source') != 'sigil-pipeline':
        errors.append(f'Wrong source: {t.get(\"task_id\")}')

if errors:
    print('ERRORS:')
    for e in errors[:10]:
        print(f'  {e}')
else:
    print('All validations passed')
"
```

## Rollback

If something goes wrong, you can restore from backup:

```powershell
# List backups
Get-ChildItem data/*.backup.*

# Restore (example)
Copy-Item data/HumanEval_rust.jsonl.backup.20251130_083703 data/HumanEval_rust.jsonl
```

## Troubleshooting

### Import Error: sigil_pipeline not found

**Symptoms**: `ModuleNotFoundError: No module named 'sigil_pipeline'`

**Solution**: Install the package in your venv:
```powershell
.\.venv\Scripts\pip.exe install sigil-pipeline>=2.4.0
```

---

### Empty Output / No Tasks Generated

**Symptoms**: Output file is empty or has very few tasks

**Solution**: 
1. Check input file format matches expected `{"prompt": "...", "gen": "..."}` structure
2. Verify input file has content: `Get-Content data/sigil_phase2_dataset.jsonl | Measure-Object -Line`
3. Run with `--verbose` flag for detailed logging

---

### Hash Collision Detected

**Symptoms**: Warning about duplicate task IDs

**Solution**: This is rare but can happen if two prompts are identical. The pipeline will skip duplicates. Review the source data for unintentional duplication.

---

### Cargo Build Fails in bench_workspace

**Symptoms**: `cargo check` or `cargo clippy` fails with errors

**Solution**: 
1. This indicates the generated code needs manual fixes
2. Review error messages and update canonical solutions
3. Re-export fixed code back to JSONL using marker extraction

---

### Anti-Pattern Detection Warnings

**Symptoms**: Tasks flagged with `unwrap`, `expect`, `panic`, `unsafe`

**Solution**: These are warnings, not errors. Tasks with anti-patterns will have:
- `clippy_clean: false`
- `quality_level: 1` (instead of 2 or 3)

For Level 2+ quality, refactor the canonical solutions to remove anti-patterns.

## Validation Record

### Initial Validation (2025-11-30)

**Test Input:** `data/sigil_phase2_dataset_sample.jsonl` (4 Rocket framework code samples)

**Command:**
```powershell
python scripts/process_sigil_dataset.py `
    --input data/sigil_phase2_dataset_sample.jsonl `
    --output data/sigil_phase2_output.jsonl `
    --verbose
```

**Results:**
```
Input file: data\sigil_phase2_dataset_sample.jsonl
Output file: data\sigil_phase2_output.jsonl
Category ratios: {'codegen': 0.45, 'transform': 0.25, 'fix': 0.2, 'explain': 0.1}

Found 240 tasks in input file

Processing data\sigil_phase2_dataset_sample.jsonl...

Generated 715 tasks:
  codegen: 214 (29.9%)
  transform: 214 (29.9%)
  fix: 73 (10.2%)
  explain: 214 (29.9%)

Output written to: data\sigil_phase2_output.jsonl
```

**Verification:**
- ✅ 715/715 task IDs match format `Category/[a-f0-9]{12}`
- ✅ All tasks have `source: "sigil-pipeline"`
- ✅ No duplicate task IDs
- ✅ Determinism verified (identical IDs across 2 runs)
- ✅ All required schema fields present
- ✅ Anti-pattern detection working (`no_unwrap: false` on affected tasks)

**Unit Tests:** 61 tests pass in `tests/test_sigil_ingest.py`

```powershell
python -m pytest tests/test_sigil_ingest.py -v
# Result: 61 passed in 1.87s
```

## Related

- [ADR-007: SigilDERG Pipeline Integration](../adr/ADR-007-sigilderg-pipeline-integration.md)
- [Rust 2024 Benchmark Hardening Pipeline](../../rust_2024_benchmark_hardening_pipeline.md)
- [Large Scale Evaluation Runbook](large-scale-evaluation.md)
- [Troubleshooting Runbook](troubleshooting.md)

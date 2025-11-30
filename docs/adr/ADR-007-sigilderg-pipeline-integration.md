# ADR-007: SigilDERG Pipeline Integration

## Status

**Accepted** — Validated 2025-11-30

## Context

The human-eval-Rust benchmark dataset needs to expand beyond its current ~27 CodeGen tasks to provide comprehensive evaluation coverage. The target distribution is:

- **CodeGen**: 45% — Write new code from specification
- **Transform**: 25% — Refactor, rewrite, or adapt existing code
- **Fix**: 20% — Bug-fixing and code repair
- **Explain**: 10% — Documentation, summaries, walkthroughs

SigilDERG Data Production (`sigil-pipeline` on PyPI) generates high-quality Rust code samples from real-world crates. These samples can be transformed into benchmark tasks across all four categories.

Additionally, the existing sequential task ID scheme (`CodeGen/0`, `CodeGen/1`, etc.) creates collision risks when merging data from multiple sources and makes provenance tracking difficult.

## Decision

### 1. Content-Hash Based Task IDs

Replace sequential task IDs with content-hash based IDs for deterministic, collision-free identification:

```python
import hashlib

def compute_task_hash(prompt: str, category: str) -> str:
    """Generate deterministic 12-character hash from prompt content."""
    content = f"{category}:{prompt}".encode("utf-8")
    return hashlib.sha256(content).hexdigest()[:12]

# Result: "CodeGen/a3f8c2e1b4d9"
```

This applies to:
- All existing tasks in `HumanEval_rust.jsonl` (migrated in-place)
- All new tasks from `sigil-pipeline`

### 2. Source Attribution

Add a `source` field to track data provenance:

- `"humaneval-rust"` — Original HumanEval Rust tasks
- `"sigil-pipeline"` — Tasks derived from SigilDERG Data Production

### 3. Sigil Ingestor Module

Create `human_eval/sigil_ingest.py` with `SigilIngestor` class that:

1. Parses `sigil-pipeline` output format: `{"prompt": "...", "gen": "..."}`
2. Extracts function signatures for CodeGen prompts
3. Generates Transform/Fix/Explain task variants
4. Emits HumanEval-compatible JSONL with quality metadata

### 4. Optional Workspace Scaffolding

Create `human_eval/workspace_scaffold.py` providing `--scaffold-workspace` flag to generate `bench_workspace/` structure for Rust 2024 hardening pipeline validation:

```
bench_workspace/
├── Cargo.toml              # Workspace manifest
├── .rustfmt.toml           # style_edition = "2024"
├── clippy.toml             # msrv, lint config
├── CodeGen_a3f8c2e1b4d9/
│   ├── Cargo.toml          # edition = "2024"
│   └── src/lib.rs          # BEGIN_*/END_* markers
└── ...
```

### 5. Automatic Dependency Detection (v2.5.0)

The workspace scaffolding system includes automatic detection of external crate dependencies:

```python
from human_eval.workspace_scaffold import analyze_dependencies, prompt_for_dependencies

# Analyze tasks for external crate usage
analysis = analyze_dependencies(tasks)
print(analysis.format_report())

# Interactive approval workflow
decision = prompt_for_dependencies(analysis, auto_approve=False)

# Scaffold with approved dependencies
scaffold_workspace(tasks, output_dir, dependency_decision=decision)
```

**Known Crates Registry** includes 15+ common crates:
- Web frameworks: `rocket`, `hyper`, `reqwest`
- Async runtimes: `tokio`, `async-trait`, `futures`
- Serialization: `serde`, `serde_json`
- Configuration: `figment`
- And more...

**CLI Flags:**
- `--auto-deps`: Automatically approve all detected dependencies
- `--no-deps`: Skip dependency detection entirely
- `--select-deps`: Interactive selection (default behavior)

### 6. Unified Hardening Runner (v2.5.0)

The `run_hardening()` function provides a single entrypoint for the complete hardening pipeline:

```python
from human_eval.workspace_scaffold import run_hardening

result = run_hardening(
    "bench_workspace",
    apply_fmt=True,      # Apply formatting (vs --check)
    skip_clippy=False,   # Include clippy step
    skip_tests=False,    # Include test step
    verbose=True,        # Print progress
)

print(result.format_report())
print(f"All passed: {result.all_passed}")
print(f"Check passed: {result.check_passed}")
print(f"Clippy passed: {result.clippy_passed}")
```

**CLI Integration:**
```bash
python scripts/process_sigil_dataset.py \
    --input data/sigil.jsonl \
    --scaffold-workspace bench_workspace \
    --auto-deps \
    --run-hardening
```

**Hardening Steps (in order):**
1. `cargo fmt` — Format code to Rust 2024 style
2. `cargo check --all --tests` — Type checking and borrow checking
3. `cargo clippy --all --tests -- -D warnings -W clippy::pedantic -W clippy::nursery` — Strict linting
4. `cargo test --all` — Run all tests

### 7. Quality Level Tracking

Track validation status per task using quality levels from the Rust 2024 Benchmark Hardening Pipeline:

| Level | Name | Requirements |
|-------|------|--------------|
| 0 | Unvalidated | Raw import, not yet checked |
| 1 | Valid Modern Rust | `edition=2024`, `cargo check` passes, `rustfmt` applied |
| 2 | Idiomatic & Clean | Level 1 + Clippy pedantic/nursery, no unwrap/expect/panic/unsafe |
| 3 | Semantically Hardened | Level 2 + all tests pass + property tests where applicable |

### 8. Extended JSONL Schema

```json
{
  "task_id": "CodeGen/a3f8c2e1b4d9",
  "category": "codegen",
  "subcategory": "function_impl",
  "prompt": "/// Returns the GCD of two integers.\nfn gcd(a: i32, b: i32) -> i32 {",
  "canonical_solution": "...",
  "test": "#[cfg(test)] mod tests { ... }",
  "entry_point": "gcd",
  "source": "sigil-pipeline",
  
  "edition": "2024",
  "rustfmt_style_edition": "2024",
  "typechecked": false,
  "clippy_clean": false,
  "no_unsafe": true,
  "no_unwrap": true,
  "quality_level": 0,
  "processed_date": "2025-11-30T00:00:00Z"
}
```

## Consequences

### Positive

- **Collision-free IDs**: Content-hash ensures no ID conflicts across sources
- **Deterministic**: Same prompt always generates same ID, enabling deduplication
- **Provenance tracking**: `source` field enables filtering by data origin
- **Quality visibility**: `quality_level` shows validation status at a glance
- **Hardening integration**: `--scaffold-workspace` enables full Rust 2024 pipeline
- **Dependency detection** (v2.5.0): Automatic detection and workspace-level management of external crate dependencies
- **Unified hardening runner** (v2.5.0): Single `run_hardening()` entrypoint or `--run-hardening` CLI flag
- **Ecosystem alignment**: Uses `sigil-pipeline` from PyPI (optional dependency)

### Negative

- **Breaking change**: Existing task IDs in `HumanEval_rust.jsonl` will change
- **Migration required**: One-time script needed to update existing data
- **Longer IDs**: `CodeGen/a3f8c2e1b4d9` vs `CodeGen/0` (12 chars vs 1-2 chars)

### Neutral

- `sigil-pipeline` remains in `[ecosystem]` optional dependency group
- Hardening can be run manually or via `--run-hardening` flag
- Four-category ratio (45/25/20/10) is a target, not enforced programmatically

## Alternatives Considered

### Alternative 1: Versioned File Instead of In-Place Migration

Create `HumanEval_rust_v2.jsonl` with new ID scheme, keeping original file unchanged.

**Rejected because**: Creates maintenance burden of two parallel files. Old system is permanently deprecated, clean break is preferred.

### Alternative 2: Sequential IDs with Source Prefix

Use `sigil_CodeGen/100`, `sigil_CodeGen/101` for new tasks.

**Rejected because**: Still requires coordination to avoid collisions, doesn't solve the fundamental problem, and creates inconsistent ID formats.

### Alternative 3: UUID-Based IDs

Use full UUIDs like `CodeGen/550e8400-e29b-41d4-a716-446655440000`.

**Rejected because**: Too long, not deterministic (can't deduplicate), and harder to work with in practice.

## Validation

This implementation was validated on **2025-11-30** with the following test:

### Test Input

Sample dataset `data/sigil_phase2_dataset_sample.jsonl` containing 4 production Rust code samples from the Rocket web framework (CookieJar, Error handling, async I/O utilities, and lib.rs module).

### Test Command

```powershell
python scripts/process_sigil_dataset.py \
    --input data/sigil_phase2_dataset_sample.jsonl \
    --output data/sigil_phase2_output.jsonl \
    --verbose
```

### Results

| Metric | Result |
|--------|--------|
| Input tasks | 4 |
| Generated tasks | 715 |
| Valid task IDs | 715/715 (100%) |
| Source attribution | All `sigil-pipeline` |
| Determinism | ✅ Verified (identical IDs across 2 runs) |

**Category Breakdown:**

| Category | Count | Percentage |
|----------|-------|------------|
| CodeGen | 214 | 29.9% |
| Transform | 214 | 29.9% |
| Fix | 73 | 10.2% |
| Explain | 214 | 29.9% |

**Subcategory Distribution (CodeGen):**
- async_await: 65
- iterator_combinator: 57  
- error_handling: 41
- function_impl: 29
- lifetimes: 14
- collections: 5
- generics: 3

**Schema Compliance:** All 715 tasks include required fields (`task_id`, `category`, `subcategory`, `prompt`, `canonical_solution`, `test`, `entry_point`, `source`, `edition`, `rustfmt_style_edition`, `typechecked`, `clippy_clean`, `no_unsafe`, `no_unwrap`, `quality_level`, `processed_date`).

**Anti-pattern Detection:** Working correctly (e.g., tasks containing `.unwrap()` have `no_unwrap: false`).

### Unit Tests

62 unit tests pass in `tests/test_sigil_ingest.py` covering:
- Hash determinism and uniqueness
- Task ID formatting
- Anti-pattern detection
- Code extraction (signatures, entry points, doc comments)
- Schema compliance
- Category ratio validation
- Dependency detection (v2.5.0)

## Related

- [Rust 2024 Benchmark Hardening Pipeline](../../docs/rust_2024_benchmark_hardening_pipeline.md) — Quality validation spec
- [ADR-005: Deterministic Compilation](ADR-005-deterministic-compilation.md) — Related determinism goals
- [sigil-pipeline on PyPI](https://pypi.org/project/sigil-pipeline/) — Data source package
- `human_eval/sigil_ingest.py` — Implementation
- `human_eval/workspace_scaffold.py` — Workspace generator (incl. dependency detection)
- `scripts/process_sigil_dataset.py` — CLI driver
- `scripts/migrate_task_ids.py` — One-time migration script
- `docs/runbooks/sigil-pipeline-ingestion.md` — Operational guide
- `docs/runbooks/troubleshooting.md` — Troubleshooting guide (incl. dependency issues)
- `tests/test_sigil_ingest.py` — Unit and property-based tests

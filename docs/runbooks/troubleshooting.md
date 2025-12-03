# Runbook: Troubleshooting

## Common Issues and Solutions

---

### Issue: "rustc not found in PATH"

**Symptoms:**
- `infra_missing_toolchain` error in results
- All samples fail with same error

**Solution:**
```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Verify
rustc --version
```

---

### Issue: "Firejail not available"

**Symptoms:**
- Interactive prompt appears
- Warning about unsandboxed execution

**Solution (Linux):**
```bash
# Install Firejail
sudo apt-get install firejail  # Debian/Ubuntu
sudo dnf install firejail      # Fedora
sudo pacman -S firejail        # Arch

# Verify
firejail --version
```

**Solution (Windows/macOS):**
```bash
# Accept unsandboxed mode (for trusted code only)
evaluate_functional_correctness samples.jsonl \
    --sandbox-mode=none --allow-no-sandbox
```

---

### Issue: "malloc: can't allocate region"

**Symptoms:**
- Random sample failures
- System becomes unresponsive

**Solution:**
```bash
# Reduce parallel workers
evaluate_functional_correctness samples.jsonl --n_workers=4

# Free memory before running
# Close other applications
```

---

### Issue: All samples timeout

**Symptoms:**
- 100% timeout rate
- Results show `"error_type": "compile_timeout"` or `"test_timeout"`

**Solution:**
```bash
# Increase timeout budgets (separate budgets for compile/run/clippy)
evaluate_functional_correctness samples.jsonl \
    --compile-timeout=30.0 \
    --run-timeout=30.0 \
    --clippy-timeout=20.0

# Check for infinite loops in completions
head -1 samples.jsonl | python -c "import json,sys; print(json.load(sys.stdin)['completion'])"

# Check which phase is timing out
grep -o '"error_type":"[^"]*timeout"' samples.jsonl_results.jsonl | sort | uniq -c
# If mostly compile_timeout: increase --compile-timeout
# If mostly test_timeout: increase --run-timeout
```

**Note:** Since v2.5.0, timeouts are tracked per phase (compile, run, clippy). See [ADR-008](../adr/ADR-008-separate-timeout-budgets.md).

---

### Issue: Clippy lint failures

**Symptoms:**
- `error_type: "lint_failure"` in results
- All completions fail with clippy warnings
- Happens when `--clippy-required` flag is used

**Solution:**
```bash
# Disable clippy enforcement (advisory mode - default)
evaluate_functional_correctness samples.jsonl  # No --clippy-required

# Check what lint issues exist (clippy_ok field shows results)
grep -o '"clippy_ok":[^,]*' samples.jsonl_results.jsonl | sort | uniq -c

# Increase clippy timeout if infrastructure issue
evaluate_functional_correctness samples.jsonl \
    --clippy-required \
    --clippy-timeout=20.0
```

**Note:** Since v2.5.0, clippy has two modes:
- **Advisory (default)**: Lint failures recorded but don't fail completion
- **Required**: Lint failures block completion with `lint_failure` error type

See [ADR-009](../adr/ADR-009-clippy-integration-enforcement.md) for details.

---

### Issue: "infra_missing_linter" errors

**Symptoms:**
- `error_type: "infra_missing_linter"` in results
- Clippy fails due to missing cargo

**Solution:**
```bash
# Verify cargo is installed
cargo --version

# Install if missing
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# If cargo exists but clippy fails, check temp dir access
# (Cargo.toml is now auto-generated, but may fail on read-only filesystems)
```

---

### Issue: 100% compile failures

**Symptoms:**
- `compile_rate: 0.0`
- All results show `compile_error`

**Possible Causes:**
1. Model generating Python instead of Rust
2. Missing function signature in completion
3. Rust version incompatibility

**Solution:**
```bash
# Check completion format
head -1 samples.jsonl | python -c "import json,sys; print(json.load(sys.stdin)['completion'])"

# Verify Rust version
rustc --version  # Should be 1.56+ for Edition 2021
```

---

### Issue: "disallowed usage of ..." errors

**Symptoms:**
- Samples blocked by pattern filter
- Results show `"result": "failed: disallowed usage of std::fs"`

**Explanation:**
Pattern-based security is blocking dangerous code.

**Solution (if code is trusted):**
```bash
# Disable policy enforcement
evaluate_functional_correctness samples.jsonl --no-enforce-policy
```

---

### Issue: Very slow evaluation

**Symptoms:**
- Seconds per sample instead of samples per second
- System CPU not saturated

**Solution:**
```bash
# Increase parallelism
evaluate_functional_correctness samples.jsonl --n_workers=24

# Check for bottlenecks
htop  # Monitor CPU/memory

# Reduce timeout for faster failure detection
evaluate_functional_correctness samples.jsonl --timeout=5.0
```

---

### Issue: Zombie processes after interruption

**Symptoms:**
- `rustc` or `firejail` processes lingering
- High CPU usage after evaluation stopped

**Solution:**
```bash
# Kill zombie processes
pkill -9 rustc
pkill -9 firejail

# Verify cleanup
ps aux | grep rustc
ps aux | grep firejail
```

---

### Issue: Results file not created

**Symptoms:**
- Evaluation runs but no `_results.jsonl` file

**Solution:**
```bash
# Check working directory
pwd
ls -la

# Check write permissions
touch test_write.txt
rm test_write.txt

# Run with explicit output path
evaluate_functional_correctness samples.jsonl
ls -la samples.jsonl_results.jsonl
```

---

### Issue: Unicode encoding errors

**Symptoms:**
- `UnicodeDecodeError` during parsing
- Garbled characters in output

**Solution:**
```bash
# Ensure UTF-8 encoding
file samples.jsonl  # Should show UTF-8

# Convert if needed
iconv -f ISO-8859-1 -t UTF-8 samples.jsonl > samples_utf8.jsonl
```

---

## Diagnostic Commands

```bash
# System info
uname -a
python --version
rustc --version

# Memory status
free -h

# Process monitoring
htop

# Check samples format
python -c "
import json
with open('samples.jsonl') as f:
    for i, line in enumerate(f):
        try:
            d = json.loads(line)
            assert 'task_id' in d
            assert 'completion' in d
        except Exception as e:
            print(f'Line {i+1}: {e}')
            break
    else:
        print('All samples valid')
"
```

---

## Workspace Scaffolding Issues (v2.5.0+)

### Issue: Unresolved imports in cargo check

**Symptoms:**
- `cargo check` fails with "unresolved import" errors
- Error messages like `error[E0432]: unresolved import 'rocket'`

**Cause:**
The code uses external crates that weren't added to `Cargo.toml`.

**Solution:**
```powershell
# Re-scaffold with auto-dependency detection
.\.venv\Scripts\python.exe scripts/process_sigil_dataset.py `
    --input data/sigil.jsonl `
    --scaffold-workspace bench_workspace `
    --auto-deps

# Or manually add dependencies to bench_workspace/Cargo.toml
# [workspace.dependencies]
# rocket = { version = "0.5", features = ["secrets"] }
```

---

### Issue: Unknown crate not in registry

**Symptoms:**
- Dependency analysis reports "unresolved imports"
- Warning: `[!] Unresolved imports (not in registry): some_obscure_crate`

**Cause:**
The crate isn't in the known crates registry (15+ common crates supported).

**Solution:**
1. Manually add the dependency to `bench_workspace/Cargo.toml`:
   ```toml
   [workspace.dependencies]
   some_obscure_crate = "1.0"
   ```
2. Or request the crate be added to `KNOWN_CRATES_REGISTRY` in `workspace_scaffold.py`

---

### Issue: Dependency version conflicts

**Symptoms:**
- `cargo check` fails with version incompatibility errors
- Multiple crates require different versions of the same dependency

**Solution:**
```powershell
# Check Cargo.toml for conflicting versions
cat bench_workspace/Cargo.toml

# Update to compatible versions in [workspace.dependencies]
# Run cargo update to resolve
cd bench_workspace
cargo update
```

---

## CI/CD Environment Issues

### Issue: pytest INTERNALERROR with os module corruption

**Symptoms:**

- `TypeError: 'NoneType' object is not callable` for `os.chmod`, `os.getcwd`, `os.unlink`
- Error occurs during pytest teardown, not in test code
- Only happens in containerized CI (GitHub Actions, Docker)

**Cause:**
Firejail's seccomp filters are incompatible with containerized environments.
Installing Firejail in GitHub Actions runners corrupts Python's `os` module
at the C level.

**Solution:**
Do NOT install Firejail in CI. Tests should mock Firejail functionality:

```yaml
# .github/workflows/ci.yml
# DO NOT include: sudo apt-get install -y firejail
# Tests use mocks and sandbox_mode="none"
```

**Detection in Tests:**
Use the `is_ci` fixture to detect CI environment:

```python
@pytest.fixture
def is_ci() -> bool:
    """Detect CI environment."""
    return os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"

@pytest.fixture
def skip_on_ci(is_ci: bool):
    """Skip test in CI environment."""
    if is_ci:
        pytest.skip("Test not supported in CI environment")
```

**Reference:** See [ADR-001](../adr/ADR-001-firejail-first-sandboxing.md) for
architectural context on the Firejail-first approach and its CI limitations.

---

## Getting Help

1. Check [GitHub Issues](https://github.com/Superuser666-Sigil/human-eval-Rust/issues)
2. Review [ADRs](../adr/README.md) for architectural context
3. Contact maintainer via GitHub


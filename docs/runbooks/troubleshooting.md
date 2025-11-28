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
- Results show `"result": "timed out"`

**Solution:**
```bash
# Increase timeout
evaluate_functional_correctness samples.jsonl --timeout=60.0

# Check for infinite loops in completions
head -1 samples.jsonl | python -c "import json,sys; print(json.load(sys.stdin)['completion'])"
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

## Getting Help

1. Check [GitHub Issues](https://github.com/Superuser666-Sigil/human-eval-Rust/issues)
2. Review [ADRs](../adr/README.md) for architectural context
3. Contact maintainer via GitHub


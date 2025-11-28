# Setup Guide

Complete setup instructions for HumanEval Rust evaluation harness.

## Prerequisites

### Python Environment

**Required:** Python 3.12.10 or later

```bash
# Verify Python version
python --version  # Should show 3.12.10+

# Create virtual environment
python -m venv venv

# Activate (Linux/macOS)
source venv/bin/activate

# Activate (Windows)
.\venv\Scripts\Activate.ps1
```

### Rust Toolchain

**Required:** Rust 1.56+ (Edition 2021 support)

```bash
# Install rustup (Linux/macOS)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install rustup (Windows)
# Download from https://rustup.rs

# Set stable toolchain
rustup default stable

# Verify installation
rustc --version  # Should show 1.56+
cargo --version
```

### Firejail (Linux, Recommended)

For secure sandbox execution on Linux:

```bash
# Debian/Ubuntu
sudo apt-get install firejail

# Fedora/RHEL
sudo dnf install firejail

# CentOS
sudo yum install firejail

# Arch Linux
sudo pacman -S firejail

# Verify installation
firejail --version
```

> **Note:** Firejail is Linux-only. Windows and macOS users should only evaluate trusted code.

---

## Installation

### From PyPI (Recommended)

```bash
pip install human-eval-rust
```

### With Ecosystem Packages

```bash
# Full SigilDERG ecosystem
pip install human-eval-rust[ecosystem]

# This installs:
# - human-eval-rust
# - sigil-pipeline
# - sigilderg-finetuner
```

### From Source (Development)

```bash
# Clone repository
git clone https://github.com/Superuser666-Sigil/human-eval-Rust.git
cd human-eval-Rust

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\Activate.ps1 on Windows

# Install in development mode
pip install -e .

# Install development dependencies
pip install -e ".[dev]"
```

### Verify Installation

```bash
# Check CLI is available
evaluate_functional_correctness --help

# Run example evaluation
evaluate_functional_correctness data/example_rust_samples.jsonl \
    --problem_file=data/example_rust_problem.jsonl
```

Expected output:
```
Reading samples...
4it [00:00, 1959.50it/s]
Running test suites...
100%|...| 4/4 [00:03<00:00,  1.13it/s]
Writing results to data/example_rust_samples.jsonl_results.jsonl...
{'pass@1': 0.5}
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `HUMAN_EVAL_TIMEOUT` | Per-sample timeout (seconds) | `10.0` |
| `HUMAN_EVAL_WORKERS` | Parallel worker count | `24` |
| `HUMAN_EVAL_SANDBOX` | Sandbox mode (`firejail`, `none`) | auto-detect |

### CLI Options

```bash
evaluate_functional_correctness samples.jsonl \
    --problem_file=data/HumanEval_rust.jsonl \
    --k=1,10,100 \
    --n_workers=8 \
    --timeout=5.0 \
    --sandbox-mode=firejail \
    --enforce-policy
```

| Option | Description |
|--------|-------------|
| `--k` | Pass@k values to compute |
| `--n_workers` | Parallel workers |
| `--timeout` | Per-sample timeout |
| `--sandbox-mode` | `firejail`, `none`, or auto |
| `--allow-no-sandbox` | Allow unsandboxed in non-interactive mode |
| `--enforce-policy` | Enable pattern filtering (default) |
| `--no-enforce-policy` | Disable for pure HumanEval compatibility |

---

## Development Setup

### Install Dev Dependencies

```bash
pip install -e ".[dev]"
```

This includes:
- pytest, pytest-cov, pytest-mock
- hypothesis (property-based testing)
- black, isort, flake8, mypy
- mutmut (mutation testing)

### Run Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=human_eval --cov-report=html

# Specific test file
pytest tests/test_security.py -v

# Skip slow tests
pytest tests/ -m "not slow"
```

### Code Quality

```bash
# Format code
black human_eval tests
isort human_eval tests

# Lint
flake8 human_eval tests

# Type check
mypy human_eval
```

### Run CI Locally

```bash
# Using act (requires Docker)
act -j test

# Or run test script
python test_ci_local.py
```

---

## Platform-Specific Notes

### Linux

- Full Firejail support
- Recommended for production evaluation
- All features available

### Windows

- No Firejail support
- Pattern-based filtering only
- Use `--sandbox-mode=none --allow-no-sandbox`
- Only evaluate trusted code

### macOS

- No Firejail support
- Pattern-based filtering only
- Similar to Windows limitations

### Docker

```bash
# Build container
docker build -t human-eval-rust .

# Run evaluation
docker run -v $(pwd)/samples:/samples human-eval-rust \
    evaluate_functional_correctness /samples/rust_samples.jsonl
```

---

## Troubleshooting

### "rustc not found"

```bash
# Verify Rust is installed
rustc --version

# If not found, install:
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env
```

### "Firejail not available"

On Linux, install Firejail:
```bash
sudo apt-get install firejail
```

On Windows/macOS, use without sandbox:
```bash
evaluate_functional_correctness samples.jsonl \
    --sandbox-mode=none --allow-no-sandbox
```

### "malloc: can't allocate region"

System is low on memory. Free memory or reduce workers:
```bash
evaluate_functional_correctness samples.jsonl --n_workers=4
```

### Slow Evaluation

- Reduce timeout: `--timeout=3.0`
- Reduce workers on low-memory systems: `--n_workers=4`
- Check for infinite loops in completions

### Permission Denied (Firejail)

```bash
# Check Firejail is properly installed
which firejail
firejail --version

# May need to restart shell after installation
```

---

## Next Steps

- [ECOSYSTEM_INTEGRATION.md](ECOSYSTEM_INTEGRATION.md) - Integration with Pipeline and Finetuner
- [SECURITY.md](SECURITY.md) - Security model and threat analysis
- [adr/README.md](adr/README.md) - Architecture decisions


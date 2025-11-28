# Testing CI Locally

Run the CI workflow locally before pushing to catch issues early.

---

## Option 1: pytest (Fastest)

Run the test suite directly:

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=human_eval --cov-report=html

# Run specific test categories
pytest tests/ -m "unit" -v          # Unit tests only
pytest tests/ -m "integration" -v   # Integration tests only
pytest tests/ -m "security" -v      # Security tests only
pytest tests/ -m "not slow" -v      # Skip slow tests
```

**Pros:**
- Fast execution
- Immediate feedback
- Full debug capability

**Cons:**
- Doesn't test exact GitHub Actions environment

---

## Option 2: Using `act` (GitHub Actions Runner)

`act` runs GitHub Actions workflows locally using Docker.

### Installation

**Windows:**
```powershell
choco install act-cli
# or download from https://github.com/nektos/act/releases
```

**macOS:**
```bash
brew install act
```

**Linux:**
```bash
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash
```

### Prerequisites

- Docker Desktop installed and running
- Verify: `docker ps`

### Usage

```bash
# List available jobs
act -l

# Run all workflows
act

# Run specific job
act -j test

# Run with push event
act push

# Use larger image if needed
act -P ubuntu-latest=catthehacker/ubuntu:act-latest
```

**Pros:**
- Matches GitHub Actions environment closely
- Tests the actual workflow file

**Cons:**
- Requires Docker
- Slower than direct pytest
- Some actions may not work locally

---

## Option 3: Manual Step-by-Step

Run each CI step manually:

```bash
# 1. Lint checks
black --check human_eval tests
isort --check-only human_eval tests
flake8 human_eval tests --exclude=venv,.venv

# 2. Type checking
mypy human_eval

# 3. Run tests with coverage
pytest tests/ -v --cov=human_eval --cov-report=xml

# 4. Check coverage threshold
coverage report --fail-under=90
```

---

## Test Categories

The test suite uses pytest markers:

| Marker | Description |
|--------|-------------|
| `unit` | Fast unit tests |
| `integration` | Tests requiring rustc |
| `security` | Security-focused tests |
| `resilience` | Chaos engineering tests |
| `property` | Hypothesis property-based tests |
| `slow` | Long-running tests |
| `windows_only` | Windows-specific tests |
| `unix_only` | Unix-specific tests |

### Running by Category

```bash
# Run only unit tests (fast)
pytest tests/ -m "unit"

# Run everything except slow tests
pytest tests/ -m "not slow"

# Run security tests
pytest tests/ -m "security"

# Run integration tests (requires rustc)
pytest tests/ -m "integration"
```

---

## CI Configuration

The CI workflow (`.github/workflows/ci.yml`) runs:

1. **Install Firejail** (Linux)
2. **Install Rust** (stable toolchain)
3. **Install Python dependencies**
4. **Run pytest with coverage**
5. **Check 90% coverage threshold**

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install Firejail
        run: sudo apt-get install -y firejail
      - name: Install Rust
        uses: dtolnay/rust-toolchain@stable
      - name: Install dependencies
        run: pip install -e .[dev]
      - name: Run tests
        run: pytest tests/ -v --cov=human_eval --cov-report=xml
      - name: Check coverage
        run: coverage report --fail-under=90
```

---

## Recommended Workflow

1. **During development**: Run `pytest tests/ -m "unit"` for fast feedback
2. **Before committing**: Run `pytest tests/ -v` for full suite
3. **Before pushing**: Run full CI simulation with `act` or manual steps
4. **Final check**: Push to branch and verify GitHub Actions

---

## Troubleshooting

### Docker not running (for `act`)

```bash
# Start Docker Desktop
# Verify: 
docker ps
```

### Missing dependencies

```bash
pip install -e ".[dev]"
pip install hypothesis pytest-mock pytest-benchmark
```

### Tests fail due to missing rustc

```bash
# Skip integration tests
pytest tests/ -m "not integration"

# Or install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

### Coverage below threshold

Check which lines are uncovered:
```bash
pytest tests/ --cov=human_eval --cov-report=html
# Open htmlcov/index.html in browser
```

### Firejail tests failing on Windows

Expected - Firejail is Linux-only. Tests are skipped automatically.

---

## Coverage Targets

| Module | Target |
|--------|--------|
| `human_eval/data.py` | 95% |
| `human_eval/evaluation.py` | 90% |
| `human_eval/execution.py` | 85% |
| `human_eval/rust_execution.py` | 85% |
| `human_eval/sandbox.py` | 80% |

Overall project target: **90%**


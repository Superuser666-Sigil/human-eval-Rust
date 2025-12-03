"""
Shared pytest fixtures for HumanEval Rust tests.

Provides reusable test fixtures for creating mock problems, completions, and test data.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 3.0.0
"""

import json
import os
import platform
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest


# ============================================================================
# Platform Detection Fixtures
# ============================================================================


@pytest.fixture
def is_windows() -> bool:
    """Check if running on Windows."""
    return platform.system().lower() == "windows"


@pytest.fixture
def is_unix() -> bool:
    """Check if running on Unix-like system."""
    return platform.system().lower() in ("linux", "darwin")


@pytest.fixture
def is_ci() -> bool:
    """Check if running in CI environment (GitHub Actions, etc.).

    Detects CI by checking standard CI environment variables.
    """
    return os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"


@pytest.fixture
def skip_on_ci(is_ci: bool):
    """Skip test when running in CI environment.

    Use for tests that require resources unavailable in CI containers,
    such as actual firejail sandboxing (firejail's seccomp filters
    are incompatible with containerized CI environments).
    """
    if is_ci:
        pytest.skip("Test not supported in CI environment")


@pytest.fixture
def skip_on_windows(is_windows: bool):
    """Skip test on Windows."""
    if is_windows:
        pytest.skip("Test not supported on Windows")


@pytest.fixture
def skip_on_unix(is_unix: bool):
    """Skip test on Unix-like systems."""
    if is_unix:
        pytest.skip("Test not supported on Unix")


# ============================================================================
# Toolchain Detection Fixtures
# ============================================================================


@pytest.fixture
def rustc_available() -> bool:
    """Check if rustc is available in PATH."""
    return shutil.which("rustc") is not None


@pytest.fixture
def cargo_available() -> bool:
    """Check if cargo is available in PATH."""
    return shutil.which("cargo") is not None


@pytest.fixture
def firejail_available() -> bool:
    """Check if firejail is available in PATH."""
    return shutil.which("firejail") is not None


@pytest.fixture
def require_rustc(rustc_available: bool):
    """Skip test if rustc is not available."""
    if not rustc_available:
        pytest.skip("rustc not available")


@pytest.fixture
def require_cargo(cargo_available: bool):
    """Skip test if cargo is not available."""
    if not cargo_available:
        pytest.skip("cargo not available")


@pytest.fixture
def require_firejail(firejail_available: bool, is_windows: bool):
    """Skip test if firejail is not available (never available on Windows)."""
    if is_windows or not firejail_available:
        pytest.skip("firejail not available (Linux-only)")


# ============================================================================
# Temporary Directory Fixtures
# ============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test artifacts."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """Create a temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


# ============================================================================
# Sample Problem Fixtures
# ============================================================================


@pytest.fixture
def sample_problem() -> dict[str, Any]:
    """Create a basic sample problem for testing."""
    return {
        "task_id": "Test/0",
        "prompt": "fn add(a: i32, b: i32) -> i32 {",
        "test": "#[test] fn test_add() { assert_eq!(add(1, 2), 3); }",
        "entry_point": "add",
    }


@pytest.fixture
def sample_problem_with_docs() -> dict[str, Any]:
    """Create a sample problem with documentation."""
    return {
        "task_id": "Test/1",
        "prompt": '''/// Adds two integers together.
///
/// # Examples
///
/// ```
/// assert_eq!(add(2, 3), 5);
/// ```
fn add(a: i32, b: i32) -> i32 {''',
        "test": "#[test] fn test_add() { assert_eq!(add(1, 2), 3); }",
        "entry_point": "add",
    }


@pytest.fixture
def complex_problem() -> dict[str, Any]:
    """Create a more complex problem for integration testing."""
    return {
        "task_id": "Test/Complex",
        "prompt": '''/// Checks if a vector has close elements within a given threshold.
///
/// # Arguments
///
/// * `numbers` - A vector of f64 numbers
/// * `threshold` - The maximum distance between two numbers to be considered close
///
/// # Returns
///
/// True if any two numbers are closer than threshold, false otherwise.
fn has_close_elements(numbers: Vec<f64>, threshold: f64) -> bool {''',
        "test": """
#[test]
fn test_has_close_elements() {
    assert!(has_close_elements(vec![1.0, 2.0, 3.0, 4.0, 5.0, 2.0], 0.5));
    assert!(!has_close_elements(vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0], 0.5));
}
""",
        "entry_point": "has_close_elements",
    }


# ============================================================================
# Sample Completion Fixtures
# ============================================================================


@pytest.fixture
def valid_completion() -> str:
    """A valid, passing completion."""
    return "    a + b\n}"


@pytest.fixture
def invalid_syntax_completion() -> str:
    """A completion with syntax errors."""
    return "    a + b\n    // missing closing brace"


@pytest.fixture
def failing_test_completion() -> str:
    """A completion that compiles but fails tests."""
    return "    a - b  // Wrong operation\n}"


@pytest.fixture
def malicious_completion_fs() -> str:
    """A completion attempting filesystem access."""
    return """
    use std::fs;
    fs::read_to_string("/etc/passwd").unwrap();
    a + b
}"""


@pytest.fixture
def malicious_completion_process() -> str:
    """A completion attempting process execution."""
    return """
    use std::process::Command;
    Command::new("rm").args(["-rf", "/"]).spawn().unwrap();
    a + b
}"""


@pytest.fixture
def malicious_completion_network() -> str:
    """A completion attempting network access."""
    return """
    use std::net::TcpStream;
    TcpStream::connect("evil.com:80").unwrap();
    a + b
}"""


@pytest.fixture
def malicious_completion_unsafe() -> str:
    """A completion using unsafe code."""
    return """
    unsafe {
        let ptr: *mut i32 = std::ptr::null_mut();
        *ptr = 42;
    }
    a + b
}"""


@pytest.fixture
def completion_with_main() -> str:
    """A completion that includes a main function."""
    return """
    a + b
}

fn main() {
    println!("{}", add(1, 2));
}"""


# ============================================================================
# JSONL File Fixtures
# ============================================================================


@pytest.fixture
def sample_jsonl_file(tmp_path: Path) -> Path:
    """Create a sample JSONL file with completions."""
    jsonl_file = tmp_path / "samples.jsonl"
    samples = [
        {"task_id": "Test/0", "completion": "    a + b\n}"},
        {"task_id": "Test/0", "completion": "    a - b\n}"},  # Wrong
    ]
    with open(jsonl_file, "w", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(sample) + "\n")
    return jsonl_file


@pytest.fixture
def sample_problem_file(tmp_path: Path, sample_problem: dict) -> Path:
    """Create a sample problem file."""
    problem_file = tmp_path / "problems.jsonl"
    with open(problem_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(sample_problem) + "\n")
    return problem_file


@pytest.fixture
def empty_jsonl_file(tmp_path: Path) -> Path:
    """Create an empty JSONL file."""
    jsonl_file = tmp_path / "empty.jsonl"
    jsonl_file.touch()
    return jsonl_file


@pytest.fixture
def malformed_jsonl_file(tmp_path: Path) -> Path:
    """Create a malformed JSONL file."""
    jsonl_file = tmp_path / "malformed.jsonl"
    with open(jsonl_file, "w", encoding="utf-8") as f:
        f.write('{"valid": true}\n')
        f.write("this is not json\n")
        f.write('{"also_valid": true}\n')
    return jsonl_file


# ============================================================================
# Rust Source File Fixtures
# ============================================================================


@pytest.fixture
def valid_rust_source(tmp_path: Path) -> Path:
    """Create a valid Rust source file."""
    source_file = tmp_path / "valid.rs"
    source_file.write_text("""
fn add(a: i32, b: i32) -> i32 {
    a + b
}

#[test]
fn test_add() {
    assert_eq!(add(1, 2), 3);
}
""")
    return source_file


@pytest.fixture
def invalid_rust_source(tmp_path: Path) -> Path:
    """Create an invalid Rust source file with syntax errors."""
    source_file = tmp_path / "invalid.rs"
    source_file.write_text("""
fn add(a: i32, b: i32) -> i32 {
    a + b
// Missing closing brace
""")
    return source_file


# ============================================================================
# Helper Functions
# ============================================================================


def create_mock_problem(
    task_id: str = "Mock/0",
    entry_point: str = "example",
    prompt: str | None = None,
    test: str | None = None,
) -> dict[str, Any]:
    """Helper function to create mock problems with customizable fields."""
    return {
        "task_id": task_id,
        "prompt": prompt or f"fn {entry_point}() -> i32 {{",
        "test": test or f"#[test] fn test_{entry_point}() {{ assert_eq!({entry_point}(), 42); }}",
        "entry_point": entry_point,
    }


def create_sample_jsonl(
    path: Path,
    samples: list[dict[str, Any]],
) -> Path:
    """Helper function to create a JSONL file from samples."""
    with open(path, "w", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(sample) + "\n")
    return path


def assert_result_schema(result: dict[str, Any]) -> None:
    """Helper function to validate result schema."""
    required_fields = [
        "task_id",
        "completion",
        "passed",
        "result",
    ]
    for field in required_fields:
        assert field in result, f"Result must have '{field}' field"

    # Enhanced schema fields
    enhanced_fields = [
        "compile_ok",
        "test_ok",
        "error_type",
        "stderr",
        "main_free",
    ]
    for field in enhanced_fields:
        assert field in result, f"Result should have enhanced field '{field}'"


def assert_evaluation_metrics(metrics: dict[str, Any]) -> None:
    """Helper function to validate evaluation metrics."""
    assert "compile_rate" in metrics
    assert "main_free_rate" in metrics
    assert isinstance(metrics["compile_rate"], float)
    assert isinstance(metrics["main_free_rate"], float)
    assert 0.0 <= metrics["compile_rate"] <= 1.0
    assert 0.0 <= metrics["main_free_rate"] <= 1.0

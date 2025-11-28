"""
Integration and end-to-end tests for HumanEval Rust.

Tests complete evaluation flows, parallel execution, and system integration.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
"""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from human_eval import rust_execution
from human_eval.data import read_problems, stream_jsonl, write_jsonl


class TestDataPipeline:
    """Test data loading and saving pipeline."""

    def test_read_problems_returns_dict(self, sample_problem_file: Path) -> None:
        """Test that read_problems returns a dictionary keyed by task_id."""
        problems = read_problems(str(sample_problem_file))
        assert isinstance(problems, dict)
        assert "Test/0" in problems
        assert problems["Test/0"]["entry_point"] == "add"

    def test_stream_jsonl_yields_dicts(self, sample_jsonl_file: Path) -> None:
        """Test that stream_jsonl yields dictionaries."""
        rows = list(stream_jsonl(str(sample_jsonl_file)))
        assert len(rows) == 2
        assert all(isinstance(row, dict) for row in rows)
        assert all("task_id" in row for row in rows)

    def test_write_jsonl_creates_file(self, tmp_path: Path) -> None:
        """Test that write_jsonl creates a valid JSONL file."""
        output_file = tmp_path / "output.jsonl"
        samples = [{"a": 1}, {"b": 2}]

        write_jsonl(str(output_file), samples)

        assert output_file.exists()
        rows = list(stream_jsonl(str(output_file)))
        assert rows == samples

    def test_write_jsonl_append_mode(self, tmp_path: Path) -> None:
        """Test that write_jsonl append mode works correctly."""
        output_file = tmp_path / "output.jsonl"

        write_jsonl(str(output_file), [{"first": 1}])
        write_jsonl(str(output_file), [{"second": 2}], append=True)

        rows = list(stream_jsonl(str(output_file)))
        assert len(rows) == 2
        assert rows[0] == {"first": 1}
        assert rows[1] == {"second": 2}


class TestFunctionExtraction:
    """Test function body extraction from completions."""

    def test_extracts_body_from_full_function(self, sample_problem: dict) -> None:
        """Test extraction of function body from complete function."""
        completion = "fn add(a: i32, b: i32) -> i32 { a + b }"
        body = rust_execution._extract_function_body(
            completion, sample_problem["entry_point"]
        )
        assert "a + b" in body

    def test_extracts_body_from_markdown_block(self, sample_problem: dict) -> None:
        """Test extraction of function body from markdown code block."""
        completion = """
```rust
fn add(a: i32, b: i32) -> i32 {
    a + b
}
```
"""
        body = rust_execution._extract_function_body(
            completion, sample_problem["entry_point"]
        )
        assert "a + b" in body

    def test_removes_main_function(self, sample_problem: dict) -> None:
        """Test that main functions are removed from completion."""
        completion = """
fn add(a: i32, b: i32) -> i32 {
    a + b
}

fn main() {
    println!("{}", add(1, 2));
}
"""
        body = rust_execution._extract_function_body(
            completion, sample_problem["entry_point"]
        )
        assert "fn main" not in body

    def test_handles_body_only_completion(self, sample_problem: dict) -> None:
        """Test handling of completion that's just the function body."""
        completion = "{ a + b }"
        body = rust_execution._extract_function_body(
            completion, sample_problem["entry_point"]
        )
        assert "a + b" in body


class TestCompletionValidation:
    """Test the complete validation pipeline."""

    def test_valid_completion_passes_all_checks(self) -> None:
        """Test that a valid completion passes validation and sanitization."""
        valid = "fn test() -> i32 { 42 }"

        validation_error = rust_execution._validate_completion(valid)
        assert validation_error is None

        sanitization_error = rust_execution._sanitize_rust_completion(valid)
        assert sanitization_error is None

    def test_malicious_completion_fails_sanitization(self) -> None:
        """Test that malicious completions fail sanitization."""
        malicious = 'fn test() { std::process::Command::new("rm").spawn(); }'

        validation_error = rust_execution._validate_completion(malicious)
        assert validation_error is None  # Passes validation (well-formed)

        sanitization_error = rust_execution._sanitize_rust_completion(malicious)
        assert sanitization_error is not None  # Fails sanitization


@pytest.mark.skipif(
    shutil.which("rustc") is None,
    reason="rustc not available"
)
class TestRustExecution:
    """Test Rust code execution (requires rustc)."""

    @pytest.mark.integration
    def test_valid_completion_passes(self, sample_problem: dict) -> None:
        """Test that a valid completion compiles and passes tests."""
        completion = "    a + b\n}"

        result = rust_execution.rust_check_correctness(
            sample_problem,
            completion,
            timeout=30.0,
            sandbox_mode="none",
            enforce_policy=True,
        )

        assert result["compile_ok"] is True
        assert result["test_ok"] is True
        assert result["passed"] is True

    @pytest.mark.integration
    def test_failing_completion_compiles_but_fails(self, sample_problem: dict) -> None:
        """Test that a wrong completion compiles but fails tests."""
        completion = "    a - b  // Wrong!\n}"

        result = rust_execution.rust_check_correctness(
            sample_problem,
            completion,
            timeout=30.0,
            sandbox_mode="none",
            enforce_policy=True,
        )

        assert result["compile_ok"] is True
        assert result["test_ok"] is False
        assert result["passed"] is False

    @pytest.mark.integration
    def test_syntax_error_fails_compilation(self, sample_problem: dict) -> None:
        """Test that syntax errors fail compilation."""
        completion = "    a + b  // missing closing brace"

        result = rust_execution.rust_check_correctness(
            sample_problem,
            completion,
            timeout=30.0,
            sandbox_mode="none",
            enforce_policy=True,
        )

        assert result["compile_ok"] is False
        assert result["passed"] is False

    @pytest.mark.integration
    def test_policy_blocks_dangerous_code(self, sample_problem: dict) -> None:
        """Test that policy enforcement blocks dangerous code."""
        completion = '    std::process::Command::new("ls"); a + b\n}'

        result = rust_execution.rust_check_correctness(
            sample_problem,
            completion,
            timeout=30.0,
            sandbox_mode="none",
            enforce_policy=True,
        )

        assert result["passed"] is False
        assert "disallowed" in result.get("result", "").lower()

    @pytest.mark.integration
    def test_policy_disabled_allows_code(self, sample_problem: dict) -> None:
        """Test that disabling policy allows code through (for pure HumanEval)."""
        # Note: This code will still fail compilation without std::process
        # But it should not be blocked at the policy level
        completion = "    a + b\n}"

        result = rust_execution.rust_check_correctness(
            sample_problem,
            completion,
            timeout=30.0,
            sandbox_mode="none",
            enforce_policy=False,
        )

        # Should not have policy violation
        assert "disallowed" not in result.get("result", "").lower()


class TestResultSchema:
    """Test result schema completeness."""

    @pytest.mark.skipif(
        shutil.which("rustc") is None,
        reason="rustc not available"
    )
    @pytest.mark.integration
    def test_result_contains_all_fields(self, sample_problem: dict) -> None:
        """Test that result contains all required and enhanced fields."""
        completion = "    a + b\n}"

        result = rust_execution.rust_check_correctness(
            sample_problem,
            completion,
            timeout=30.0,
            sandbox_mode="none",
            enforce_policy=True,
        )

        # Required fields
        assert "task_id" in result
        assert "completion" in result
        assert "passed" in result
        assert "result" in result

        # Enhanced schema fields
        assert "compile_ok" in result
        assert "test_ok" in result
        assert "error_type" in result
        assert "stderr" in result
        assert "main_free" in result

        # New metrics fields
        assert "clippy_ok" in result
        assert "compile_time_ms" in result
        assert "binary_size_bytes" in result

    def test_main_free_detection(self, sample_problem: dict) -> None:
        """Test main_free flag detection."""
        # Without main
        completion_no_main = "    a + b\n}"
        assert rust_execution.check_main_free(completion_no_main) is True

        # With main
        completion_with_main = """
    a + b
}

fn main() {
    println!("test");
}
"""
        assert rust_execution.check_main_free(completion_with_main) is False


class TestErrorTypes:
    """Test error type classification."""

    def test_empty_completion_classified(self, sample_problem: dict) -> None:
        """Test that empty completions are properly classified."""
        # Empty completion should fail validation
        error = rust_execution._validate_completion("")
        assert error is not None
        assert "empty" in error.lower()

    def test_oversized_completion_classified(self, sample_problem: dict) -> None:
        """Test that oversized completions are properly classified."""
        huge = "a" * (rust_execution.MAX_COMPLETION_LENGTH + 1)
        error = rust_execution._validate_completion(huge)
        assert error is not None
        assert "too long" in error.lower()


class TestDeterministicFlags:
    """Test deterministic compilation settings."""

    def test_deterministic_flags_present(self) -> None:
        """Test that deterministic rustc flags are defined."""
        flags = rust_execution.DETERMINISTIC_RUSTC_FLAGS

        assert "--edition=2021" in flags
        assert "--test" in flags
        assert "-C" in flags
        assert "opt-level=0" in flags
        assert "debuginfo=0" in flags
        assert "incremental=false" in flags


class TestParallelExecution:
    """Test parallel execution handling."""

    @pytest.mark.skipif(
        shutil.which("rustc") is None,
        reason="rustc not available"
    )
    @pytest.mark.integration
    @pytest.mark.slow
    def test_multiple_completions_processed(
        self, sample_problem: dict, tmp_path: Path
    ) -> None:
        """Test processing multiple completions for same problem."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        completions = [
            "    a + b\n}",  # Correct
            "    a - b\n}",  # Wrong
            "    a * b\n}",  # Wrong
        ]

        results = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    rust_execution.rust_check_correctness,
                    sample_problem,
                    completion,
                    30.0,
                    i,
                    "none",
                    True,
                )
                for i, completion in enumerate(completions)
            ]

            for future in as_completed(futures):
                results.append(future.result())

        assert len(results) == 3
        # At least one should pass (the correct one)
        passed = sum(1 for r in results if r["passed"])
        assert passed >= 1


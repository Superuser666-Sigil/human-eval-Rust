"""
Chaos engineering and resilience tests for HumanEval Rust.

Tests system behavior under adverse conditions:
- Timeout scenarios
- Corrupted data
- Missing toolchain
- Resource constraints

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from human_eval import rust_execution
from human_eval.data import stream_jsonl
from human_eval.execution import TimeoutException, time_limit


class TestTimeoutResilience:
    """Test resilience to timeout scenarios."""

    def test_time_limit_raises_on_timeout(self) -> None:
        """Test that time_limit raises TimeoutException when exceeded."""
        import time

        with pytest.raises(TimeoutException):
            with time_limit(0.1):
                time.sleep(0.5)

    def test_time_limit_allows_fast_operations(self) -> None:
        """Test that time_limit allows operations that complete in time."""
        result = None
        with time_limit(1.0):
            result = 42
        assert result == 42

    def test_time_limit_cleanup_on_success(self) -> None:
        """Test that timer is properly cleaned up on success."""
        import threading

        initial_threads = threading.active_count()

        for _ in range(5):
            with time_limit(1.0):
                pass

        # Allow some time for threads to clean up
        import time
        time.sleep(0.1)

        # Thread count should not grow significantly
        assert threading.active_count() <= initial_threads + 2


class TestToolchainResilience:
    """Test resilience to missing or failing toolchain."""

    def test_handles_rustc_not_found(self) -> None:
        """Test graceful handling when rustc is not found."""
        # Patch subprocess.run to simulate rustc not found (FileNotFoundError)
        with patch("human_eval.rust_execution.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("rustc not found")
            available, error = rust_execution._check_rustc_available()
            assert available is False
            assert error is not None
            assert "not found" in error.lower()

    def test_handles_rustc_timeout(self) -> None:
        """Test handling when rustc version check times out."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("rustc", 5)
            available, error = rust_execution._check_rustc_available()
            assert available is False
            assert "timed out" in error.lower()

    def test_handles_rustc_failure(self) -> None:
        """Test handling when rustc returns non-zero exit code."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            available, error = rust_execution._check_rustc_available()
            assert available is False


class TestDataResilience:
    """Test resilience to corrupted or malformed data."""

    def test_handles_empty_jsonl(self, empty_jsonl_file: Path) -> None:
        """Test handling of empty JSONL files."""
        rows = list(stream_jsonl(str(empty_jsonl_file)))
        assert rows == []

    def test_handles_whitespace_only_lines(self, tmp_path: Path) -> None:
        """Test handling of JSONL with whitespace-only lines."""
        jsonl_file = tmp_path / "whitespace.jsonl"
        jsonl_file.write_text('{"a": 1}\n   \n\t\n{"b": 2}\n')

        rows = list(stream_jsonl(str(jsonl_file)))
        assert len(rows) == 2
        assert rows[0] == {"a": 1}
        assert rows[1] == {"b": 2}

    def test_extract_function_body_empty_input(self) -> None:
        """Test function extraction with empty input."""
        result = rust_execution._extract_function_body("", "test")
        assert result == ""

    def test_extract_function_body_malformed_rust(self) -> None:
        """Test function extraction with malformed Rust code."""
        malformed = "fn test( { { { } incomplete braces"
        # Should not crash
        result = rust_execution._extract_function_body(malformed, "test")
        assert isinstance(result, str)

    def test_extract_function_body_no_matching_function(self) -> None:
        """Test function extraction when target function is not found."""
        code = "fn other_function() { 42 }"
        result = rust_execution._extract_function_body(code, "target")
        assert isinstance(result, str)


class TestSandboxResilience:
    """Test resilience of sandbox operations."""

    def test_sandbox_mode_resolution_without_firejail(self) -> None:
        """Test sandbox mode resolution when firejail is unavailable."""
        from human_eval.sandbox import check_firejail_available

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("firejail not found")
            status = check_firejail_available()
            assert status.available is False

    def test_sandbox_mode_resolution_with_timeout(self) -> None:
        """Test sandbox mode resolution when firejail check times out."""
        from human_eval.sandbox import check_firejail_available

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("firejail", 5)
            status = check_firejail_available()
            assert status.available is False
            assert "timed out" in status.error.lower()


class TestCompletionResilience:
    """Test resilience when processing completions."""

    def test_handles_binary_content_in_completion(self) -> None:
        """Test handling of binary content in completion string."""
        binary_content = "fn x() { " + "".join(chr(i) for i in range(128, 256) if chr(i).isprintable()) + " }"
        # Should not crash - we don't care about the result, just that it doesn't raise
        try:
            rust_execution._validate_completion(binary_content)
        except Exception as e:
            pytest.fail(f"_validate_completion crashed on binary content: {e}")

    def test_handles_extremely_long_line(self) -> None:
        """Test handling of completion with extremely long line."""
        long_line = "let x = \"" + "a" * 100000 + "\";"
        error = rust_execution._validate_completion(long_line)
        assert error is not None  # Should be rejected

    def test_handles_deeply_nested_code(self) -> None:
        """Test handling of deeply nested code structures."""
        nested = "fn x() { " + "{ " * 100 + "42" + " }" * 100 + " }"
        # Should not crash
        violation = rust_execution._sanitize_rust_completion(nested)
        assert violation is None  # Deep nesting alone is not dangerous


class TestResourceResilience:
    """Test resilience under resource constraints."""

    def test_reliability_context_restores_functions(self) -> None:
        """Test that ReliabilityContext properly restores patched functions."""
        import os
        import shutil

        original_chdir = os.chdir

        with rust_execution.ReliabilityContext():
            # Functions may be patched inside the context
            pass

        # After context, original should be restored
        assert os.chdir == original_chdir

    def test_resource_monitor_thread_safety(self) -> None:
        """Test that ResourceMonitor is thread-safe."""
        import threading

        from human_eval.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor(max_memory_percent=95.0, max_workers=10)
        errors: list[Exception] = []
        acquired: list[bool] = []

        def try_acquire() -> None:
            try:
                result = monitor.acquire_worker()
                acquired.append(result)
                if result:
                    monitor.release_worker()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=try_acquire) for _ in range(20)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(acquired) == 20


class TestGracefulDegradation:
    """Test graceful degradation when features are unavailable."""

    def test_clippy_check_handles_missing_cargo(self) -> None:
        """Test that clippy check handles missing cargo gracefully."""
        with patch("shutil.which", return_value=None):
            # When cargo is not available, clippy should fail gracefully
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError("cargo not found")
                try:
                    result = rust_execution._run_clippy_check("/fake/path", 10.0)
                    # Should return failure
                    assert result[0] is False
                except FileNotFoundError:
                    # Also acceptable - explicit failure
                    pass

    def test_main_free_check_handles_edge_cases(self) -> None:
        """Test main_free check with various edge cases."""
        # Empty string
        assert rust_execution.check_main_free("") is True

        # Just whitespace
        assert rust_execution.check_main_free("   \n\t  ") is True

        # Main in line comment
        assert rust_execution.check_main_free("// fn main() {}") is True

        # Main in block comment
        assert rust_execution.check_main_free("/* fn main() {} */") is True

        # Main in string
        assert rust_execution.check_main_free('let s = "fn main() {}";') is True

        # Main in raw string
        assert rust_execution.check_main_free('let s = r"fn main() {}";') is True

        # Actual main
        assert rust_execution.check_main_free("fn main() {}") is False

        # Main with whitespace variations
        assert rust_execution.check_main_free("fn  main  ()") is False
        assert rust_execution.check_main_free("fn\nmain()") is False


class TestConcurrencyResilience:
    """Test resilience under concurrent load."""

    def test_concurrent_validation(self) -> None:
        """Test concurrent completion validation."""
        import threading

        errors: list[Exception] = []
        results: list[str | None] = []

        completions = [
            "fn x() { 42 }",
            "",
            "std::fs::read",
            "fn y() { let z = vec![1,2,3]; }",
        ] * 25

        def validate(completion: str) -> None:
            try:
                result = rust_execution._validate_completion(completion)
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=validate, args=(c,)) for c in completions
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 100

    def test_concurrent_sanitization(self) -> None:
        """Test concurrent completion sanitization."""
        import threading

        errors: list[Exception] = []
        results: list[str | None] = []

        completions = [
            "fn x() { 42 }",
            "fn y() { std::process::Command::new(\"ls\"); }",
            "fn z() { vec![1,2,3] }",
        ] * 33

        def sanitize(completion: str) -> None:
            try:
                result = rust_execution._sanitize_rust_completion(completion)
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=sanitize, args=(c,)) for c in completions
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 99


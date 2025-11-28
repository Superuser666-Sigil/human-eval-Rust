"""
Property-based tests using Hypothesis.

Tests invariants and properties that should hold for all inputs,
helping find edge cases that traditional tests might miss.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
"""

import pytest

# Try to import hypothesis, skip tests if not available
try:
    from hypothesis import assume, given, settings
    from hypothesis import strategies as st

    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False

    # Create dummy decorators for when hypothesis is not installed
    def given(*args, **kwargs):  # type: ignore[no-redef]
        def decorator(func):  # type: ignore[no-untyped-def]
            return pytest.mark.skip(reason="hypothesis not installed")(func)

        return decorator

    def settings(*args, **kwargs):  # type: ignore[no-redef]
        def decorator(func):  # type: ignore[no-untyped-def]
            return func

        return decorator

    class st:  # type: ignore[no-redef]
        @staticmethod
        def text(*args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        @staticmethod
        def integers(*args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        @staticmethod
        def floats(*args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        @staticmethod
        def booleans():  # type: ignore[no-untyped-def]
            return None

    def assume(condition):  # type: ignore[no-redef]
        pass


from human_eval import rust_execution
from human_eval.data import stream_jsonl, write_jsonl


@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
class TestValidationProperties:
    """Property-based tests for input validation."""

    @given(st.text(min_size=0, max_size=10000))
    @settings(max_examples=200)
    def test_validate_completion_never_crashes(self, content: str) -> None:
        """Validation should never crash on any input string."""
        # Should not raise any exception
        result = rust_execution._validate_completion(content)
        assert result is None or isinstance(result, str)

    @given(st.text(min_size=0, max_size=1000))
    @settings(max_examples=100)
    def test_validation_is_deterministic(self, content: str) -> None:
        """Same input should always produce same validation result."""
        result1 = rust_execution._validate_completion(content)
        result2 = rust_execution._validate_completion(content)
        assert result1 == result2

    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=50)
    def test_short_valid_completions_pass(self, content: str) -> None:
        """Short completions without null bytes should pass length validation."""
        assume("\x00" not in content)
        result = rust_execution._validate_completion(content)
        # Should not fail on length/line count for short content
        if result is not None:
            assert "too long" not in result
            assert "lines" not in result


@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
class TestSanitizationProperties:
    """Property-based tests for pattern sanitization."""

    @given(st.text(min_size=0, max_size=5000))
    @settings(max_examples=200)
    def test_sanitize_completion_never_crashes(self, content: str) -> None:
        """Sanitization should never crash on any input string."""
        # Should not raise any exception
        result = rust_execution._sanitize_rust_completion(content)
        assert result is None or isinstance(result, str)

    @given(st.text(min_size=0, max_size=1000))
    @settings(max_examples=100)
    def test_sanitization_is_deterministic(self, content: str) -> None:
        """Same input should always produce same sanitization result."""
        result1 = rust_execution._sanitize_rust_completion(content)
        result2 = rust_execution._sanitize_rust_completion(content)
        assert result1 == result2

    @given(st.text(min_size=1, max_size=200, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_ "))
    @settings(max_examples=100)
    def test_safe_alphanumeric_content_passes(self, content: str) -> None:
        """Pure alphanumeric content should not trigger security blocks."""
        result = rust_execution._sanitize_rust_completion(content)
        assert result is None, f"Alphanumeric content should pass: {content}"


@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
class TestFunctionExtractionProperties:
    """Property-based tests for function body extraction."""

    @given(st.text(min_size=0, max_size=2000))
    @settings(max_examples=100)
    def test_extract_function_body_never_crashes(self, content: str) -> None:
        """Function extraction should never crash on any input."""
        # Should not raise any exception
        result = rust_execution._extract_function_body(content, "test")
        assert isinstance(result, str)

    @given(st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz_"))
    @settings(max_examples=50)
    def test_extract_function_body_returns_string(self, entry_point: str) -> None:
        """Function extraction should always return a string."""
        code = f"fn {entry_point}() {{ 42 }}"
        result = rust_execution._extract_function_body(code, entry_point)
        assert isinstance(result, str)


@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
class TestMainFreeCheckProperties:
    """Property-based tests for main function detection."""

    @given(st.text(min_size=0, max_size=1000))
    @settings(max_examples=100)
    def test_check_main_free_never_crashes(self, content: str) -> None:
        """Main check should never crash on any input."""
        result = rust_execution.check_main_free(content)
        assert isinstance(result, bool)

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=50)
    def test_check_main_free_is_deterministic(self, content: str) -> None:
        """Same input should always produce same result."""
        result1 = rust_execution.check_main_free(content)
        result2 = rust_execution.check_main_free(content)
        assert result1 == result2

    @given(st.text(min_size=1, max_size=100, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_ "))
    @settings(max_examples=50)
    def test_content_without_main_keyword_passes(self, content: str) -> None:
        """Content without 'main' keyword should pass main-free check."""
        assume("main" not in content)
        assume("fn" not in content)
        result = rust_execution.check_main_free(content)
        assert result is True


@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
class TestUnicodeNormalizationProperties:
    """Property-based tests for Unicode normalization."""

    @given(st.text(min_size=0, max_size=1000))
    @settings(max_examples=100)
    def test_normalize_unicode_never_crashes(self, content: str) -> None:
        """Unicode normalization should never crash on any input."""
        result = rust_execution._normalize_unicode(content)
        assert isinstance(result, str)

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=50)
    def test_normalize_unicode_is_idempotent(self, content: str) -> None:
        """Normalizing already normalized content should be idempotent."""
        once = rust_execution._normalize_unicode(content)
        twice = rust_execution._normalize_unicode(once)
        assert once == twice

    @given(st.text(min_size=1, max_size=100, alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"))
    @settings(max_examples=50)
    def test_ascii_content_unchanged(self, content: str) -> None:
        """Pure ASCII content should be unchanged by normalization."""
        result = rust_execution._normalize_unicode(content)
        assert result == content


@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
class TestPassAtKProperties:
    """Property-based tests for pass@k calculation."""

    @given(
        st.integers(min_value=1, max_value=100),
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100)
    def test_pass_at_k_in_valid_range(
        self, n_samples: int, n_correct: int, k: int
    ) -> None:
        """pass@k should always be between 0 and 1."""
        import numpy as np

        from human_eval.evaluation import estimate_pass_at_k

        # n_correct cannot exceed n_samples
        assume(n_correct <= n_samples)
        # k cannot exceed n_samples
        assume(k <= n_samples)

        result = estimate_pass_at_k([n_samples], [n_correct], k)
        assert len(result) == 1
        assert 0.0 <= result[0] <= 1.0

    @given(
        st.integers(min_value=1, max_value=50),
        st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_all_correct_gives_one(self, n_samples: int, k: int) -> None:
        """When all samples pass, pass@k should be 1.0."""
        import numpy as np

        from human_eval.evaluation import estimate_pass_at_k

        assume(k <= n_samples)

        result = estimate_pass_at_k([n_samples], [n_samples], k)
        assert np.isclose(result[0], 1.0)

    @given(
        st.integers(min_value=1, max_value=50),
        st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_none_correct_gives_zero(self, n_samples: int, k: int) -> None:
        """When no samples pass, pass@k should be 0.0."""
        import numpy as np

        from human_eval.evaluation import estimate_pass_at_k

        assume(k <= n_samples)

        result = estimate_pass_at_k([n_samples], [0], k)
        assert np.isclose(result[0], 0.0)


@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
class TestResourceMonitorProperties:
    """Property-based tests for resource monitoring."""

    @given(
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=50)
    def test_resource_monitor_creation_never_crashes(
        self, max_memory_percent: float, max_workers: int
    ) -> None:
        """ResourceMonitor should accept any reasonable configuration."""
        from human_eval.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor(
            max_memory_percent=max_memory_percent,
            max_workers=max_workers,
        )
        assert monitor.max_memory_percent == max_memory_percent
        assert monitor.max_workers == max_workers

    @given(st.integers(min_value=1, max_value=20))
    @settings(max_examples=30)
    def test_acquire_release_is_balanced(self, n_workers: int) -> None:
        """Acquiring and releasing workers should be balanced."""
        from human_eval.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor(max_memory_percent=99.0, max_workers=n_workers)

        # Acquire all workers
        acquired_count = 0
        for _ in range(n_workers):
            if monitor.acquire_worker():
                acquired_count += 1

        # Release all workers
        for _ in range(acquired_count):
            monitor.release_worker()

        # Should be back to 0 active workers
        assert monitor._active_workers == 0


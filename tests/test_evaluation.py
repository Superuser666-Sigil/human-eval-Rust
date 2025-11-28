"""
Evaluation module tests for HumanEval Rust.

Tests pass@k calculation, metrics computation, and evaluation flow.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
"""

import numpy as np
import pytest

from human_eval import EvaluationError
from human_eval.evaluation import estimate_pass_at_k


class TestPassAtKCalculation:
    """Test pass@k estimation."""

    def test_pass_at_k_basic(self) -> None:
        """Test basic pass@k calculation."""
        total = [10, 10]
        correct = [5, 3]
        result = estimate_pass_at_k(total, correct, 1)
        assert len(result) == 2
        assert all(0.0 <= r <= 1.0 for r in result)

    def test_pass_at_k_edge_cases(self) -> None:
        """Test pass@k edge cases."""
        total = [1, 2]
        correct = [1, 0]
        result = estimate_pass_at_k(total, correct, 1)
        assert np.isclose(result[0], 1.0)
        assert result[1] >= 0.0

    def test_pass_at_k_all_correct(self) -> None:
        """Test pass@k when all samples are correct."""
        total = [10, 10]
        correct = [10, 10]
        result = estimate_pass_at_k(total, correct, 1)
        assert np.allclose(result, [1.0, 1.0])

    def test_pass_at_k_none_correct(self) -> None:
        """Test pass@k when no samples are correct."""
        total = [10, 10]
        correct = [0, 0]
        result = estimate_pass_at_k(total, correct, 1)
        assert np.allclose(result, [0.0, 0.0])

    def test_pass_at_k_single_sample(self) -> None:
        """Test pass@k with single sample."""
        total = [1]
        correct = [1]
        result = estimate_pass_at_k(total, correct, 1)
        assert np.isclose(result[0], 1.0)

    def test_pass_at_k_k_equals_n(self) -> None:
        """Test pass@k when k equals n."""
        total = [5]
        correct = [3]
        result = estimate_pass_at_k(total, correct, 5)
        # When k = n and c > 0, pass@k should be 1.0
        assert result[0] > 0.0

    def test_pass_at_k_with_numpy_arrays(self) -> None:
        """Test pass@k with numpy arrays as input."""
        total = np.array([10, 10])
        correct = np.array([5, 3])
        result = estimate_pass_at_k(total, correct, 1)
        assert len(result) == 2

    def test_pass_at_k_with_int_samples(self) -> None:
        """Test pass@k with integer num_samples."""
        correct = [5, 3]
        result = estimate_pass_at_k(10, correct, 1)
        assert len(result) == 2


class TestPassAtKMathematicalProperties:
    """Test mathematical properties of pass@k."""

    def test_pass_at_k_monotonic_in_k(self) -> None:
        """Test that pass@k increases with k."""
        total = [10]
        correct = [3]

        pass_1 = estimate_pass_at_k(total, correct, 1)[0]
        pass_5 = estimate_pass_at_k(total, correct, 5)[0]
        pass_10 = estimate_pass_at_k(total, correct, 10)[0]

        assert pass_1 <= pass_5 <= pass_10

    def test_pass_at_k_monotonic_in_correct(self) -> None:
        """Test that pass@k increases with number correct."""
        total = [10]

        pass_1_correct = estimate_pass_at_k(total, [1], 1)[0]
        pass_5_correct = estimate_pass_at_k(total, [5], 1)[0]
        pass_10_correct = estimate_pass_at_k(total, [10], 1)[0]

        assert pass_1_correct <= pass_5_correct <= pass_10_correct

    def test_pass_at_k_bounded(self) -> None:
        """Test that pass@k is always between 0 and 1."""
        for n in [1, 5, 10, 50]:
            for c in range(n + 1):
                for k in [1, 5, 10]:
                    if k <= n:
                        result = estimate_pass_at_k([n], [c], k)[0]
                        assert 0.0 <= result <= 1.0


class TestEvaluationError:
    """Test EvaluationError exception."""

    def test_evaluation_error_is_exception(self) -> None:
        """Test that EvaluationError is an Exception."""
        assert issubclass(EvaluationError, Exception)

    def test_evaluation_error_message(self) -> None:
        """Test EvaluationError message."""
        error = EvaluationError("test error")
        assert str(error) == "test error"

    def test_evaluation_error_can_be_raised(self) -> None:
        """Test that EvaluationError can be raised and caught."""
        with pytest.raises(EvaluationError) as exc_info:
            raise EvaluationError("missing completions")
        assert "missing completions" in str(exc_info.value)


class TestEstimatorFormula:
    """Test the estimator formula implementation."""

    def test_estimator_n_minus_c_less_than_k(self) -> None:
        """Test estimator when n - c < k (guaranteed pass)."""
        # When there are more correct samples than needed
        total = [10]
        correct = [8]
        result = estimate_pass_at_k(total, correct, 5)
        assert np.isclose(result[0], 1.0)

    def test_estimator_exact_formula(self) -> None:
        """Test estimator against known values."""
        # Manual calculation: n=10, c=5, k=1
        # pass@1 = 1 - (5/10) = 0.5
        total = [10]
        correct = [5]
        result = estimate_pass_at_k(total, correct, 1)
        assert np.isclose(result[0], 0.5, atol=0.01)


class TestRustcVersionCapture:
    """Test rustc version capture for reproducibility."""

    def test_get_rustc_version_exists(self) -> None:
        """Test that _get_rustc_version function exists."""
        from human_eval.evaluation import _get_rustc_version

        # Should not raise
        result = _get_rustc_version()
        assert isinstance(result, str)

    def test_get_rustc_version_returns_string(self) -> None:
        """Test that rustc version returns a string."""
        from human_eval.evaluation import _get_rustc_version

        import shutil

        if shutil.which("rustc"):
            version = _get_rustc_version()
            assert "rustc" in version.lower() or version == "unknown"
        else:
            version = _get_rustc_version()
            assert version == "unknown"


class TestResolveLanguage:
    """Test language resolution."""

    def test_resolve_language_rust(self) -> None:
        """Test that Rust language is resolved correctly."""
        from human_eval.evaluation import _resolve_language

        result = _resolve_language("rust", "problems.jsonl")
        assert result == "rust"

    def test_resolve_language_none(self) -> None:
        """Test that None defaults to Rust."""
        from human_eval.evaluation import _resolve_language

        result = _resolve_language(None, "problems.jsonl")
        assert result == "rust"

    def test_resolve_language_rejects_python(self) -> None:
        """Test that Python is rejected."""
        from human_eval.evaluation import _resolve_language

        with pytest.raises(ValueError) as exc_info:
            _resolve_language("python", "problems.jsonl")
        assert "rust" in str(exc_info.value).lower()

    def test_resolve_language_case_insensitive(self) -> None:
        """Test that language resolution is case-insensitive."""
        from human_eval.evaluation import _resolve_language

        result = _resolve_language("RUST", "problems.jsonl")
        assert result == "rust"

        result = _resolve_language("Rust", "problems.jsonl")
        assert result == "rust"

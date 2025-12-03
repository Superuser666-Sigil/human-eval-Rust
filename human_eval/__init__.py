"""
HumanEval Rust evaluation package.

Provides evaluation harness for the HumanEval Rust problem solving dataset.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 3.0.0
"""

__version__ = "3.0.0"

# Export rust_execution module so it can be imported
# Use relative import to avoid circular dependency issues
from . import rust_execution


class EvaluationError(Exception):
    """Raised when evaluation cannot proceed due to data issues."""

    pass


__all__ = ["rust_execution", "__version__", "EvaluationError"]

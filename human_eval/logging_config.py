"""
Logging configuration for HumanEval Rust evaluation.

Provides structured logging setup for CLI and library usage.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 2.1.0
"""

import logging
import sys


def setup_logging(
    level: int = logging.INFO, json_format: bool = False
) -> logging.Logger:
    """Configure logging for human-eval-rust."""

    logger = logging.getLogger("human_eval")
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    if json_format:
        formatter = logging.Formatter(
            '{"time": "%(asctime)s", "level": "%(levelname)s", '
            '"module": "%(module)s", "message": "%(message)s"}'
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(module)s: %(message)s"
        )
    handler.setFormatter(formatter)
    if not logger.handlers:
        logger.addHandler(handler)

    return logger


# Module-level logger for convenience imports
logger = logging.getLogger("human_eval")


__all__ = ["setup_logging", "logger"]

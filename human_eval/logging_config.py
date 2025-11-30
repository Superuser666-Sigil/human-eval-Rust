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


logger = logging.getLogger("human_eval")

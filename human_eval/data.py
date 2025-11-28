"""
Data loading utilities for HumanEval Rust dataset.

Provides functions to read and write JSONL files containing problems and completions.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 2.0.0
"""

import gzip
import importlib.resources
import json
import os
from collections.abc import Iterable

ROOT = os.path.dirname(os.path.abspath(__file__))
HUMAN_EVAL_RUST = os.path.join(ROOT, "..", "data", "HumanEval_rust.jsonl")


def get_human_eval_dataset(language: str | None = None) -> str:
    """Returns path to HumanEval dataset, using importlib.resources."""

    if language and language.lower() != "rust":
        raise ValueError(f"Only Rust is supported. Got language: {language}")

    with importlib.resources.as_file(
        importlib.resources.files("human_eval").joinpath("../data/HumanEval_rust.jsonl")
    ) as path:
        return str(path)


def read_problems(evalset_file: str | None = None) -> dict[str, dict]:
    """Reads problems from the specified file, or defaults to the Rust dataset."""

    if evalset_file is None:
        evalset_file = get_human_eval_dataset()
    return {task["task_id"]: task for task in stream_jsonl(evalset_file)}


def stream_jsonl(filename: str) -> Iterable[dict]:
    """
    Parses each jsonl line and yields it as a dictionary
    """
    if filename.endswith(".gz"):
        with open(filename, "rb") as gzfp:
            with gzip.open(gzfp, "rt") as fp:
                for line in fp:
                    if any(not x.isspace() for x in line):
                        yield json.loads(line)
    else:
        with open(filename, "r") as fp:
            for line in fp:
                if any(not x.isspace() for x in line):
                    yield json.loads(line)


def write_jsonl(filename: str, data: Iterable[dict], append: bool = False):
    """
    Writes an iterable of dictionaries to jsonl
    """
    if append:
        mode = "ab"
    else:
        mode = "wb"
    filename = os.path.expanduser(filename)
    if filename.endswith(".gz"):
        with open(filename, mode) as fp:
            with gzip.GzipFile(fileobj=fp, mode="wb") as gzfp:
                for x in data:
                    gzfp.write((json.dumps(x) + "\n").encode("utf-8"))
    else:
        with open(filename, mode) as fp:
            for x in data:
                fp.write((json.dumps(x) + "\n").encode("utf-8"))

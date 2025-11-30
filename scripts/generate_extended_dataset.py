"""Utility to generate the extended Rust dataset."""

from __future__ import annotations

import json
from pathlib import Path


def generate(output: str = "data/HumanEval_rust_extended.jsonl") -> None:
    problems = []
    for idx in range(2):
        problems.append(
            {
                "task_id": f"Extended/{idx}",
                "prompt": (
                    "fn identity(x: i32) -> i32 {"
                    if idx == 0
                    else "fn sum_slice(values: &[i32]) -> i32 {"
                ),
                "test": (
                    "#[test] fn test_identity() { assert_eq!(identity(5), 5); }"
                    if idx == 0
                    else "#[test] fn test_sum() { assert_eq!(sum_slice(&[1,2,3]), 6); }"
                ),
                "entry_point": "identity" if idx == 0 else "sum_slice",
            }
        )

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as fp:
        for problem in problems:
            fp.write(json.dumps(problem) + "\n")


if __name__ == "__main__":
    generate()

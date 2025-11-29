"""
Utility to generate the extended Rust dataset.

Generates additional Rust programming problems beyond the core HumanEval set.
Currently provides stub problems for testing; extend for production use.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 2.3.0
"""

import json
from pathlib import Path


def generate(output: str = "data/HumanEval_rust_extended.jsonl") -> None:
    """
    Generate the extended HumanEval Rust dataset.

    Creates additional Rust programming problems in JSONL format compatible
    with the main HumanEval Rust evaluation harness.

    Args:
        output: Path to write the generated dataset. Defaults to
            'data/HumanEval_rust_extended.jsonl'.

    Note:
        Currently generates stub problems for testing purposes.
        Extend the problems list for production-quality datasets.
    """
    problems = [
        {
            "task_id": "Extended/0",
            "prompt": "fn identity(x: i32) -> i32 {",
            "canonical_solution": "    x\n}\n",
            "test": "#[test] fn test_identity() { assert_eq!(identity(5), 5); }",
            "entry_point": "identity",
        },
        {
            "task_id": "Extended/1",
            "prompt": "fn sum_slice(values: &[i32]) -> i32 {",
            "canonical_solution": "    values.iter().sum()\n}\n",
            "test": "#[test] fn test_sum() { assert_eq!(sum_slice(&[1,2,3]), 6); }",
            "entry_point": "sum_slice",
        },
    ]

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as fp:
        for problem in problems:
            fp.write(json.dumps(problem) + "\n")


__all__ = ["generate"]


if __name__ == "__main__":
    generate()

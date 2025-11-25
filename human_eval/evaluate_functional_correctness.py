import fire
import sys

from typing import Optional

from human_eval.data import get_human_eval_dataset
from human_eval.evaluation import evaluate_functional_correctness


def entry_point(
    sample_file: str,
    k: str = "1,10,100",
    n_workers: int = 4,
    timeout: float = 3.0,
    problem_file: Optional[str] = None,
    language: Optional[str] = None,
):
    """
    Evaluate HumanEval Rust completions and write a "<input>_results.jsonl"
    file containing pass/fail metadata.

    Arguments:
      sample_file: Path to a JSONL file containing Rust completions with
        `task_id` and `completion` fields.
      k: Comma-separated list of pass@k values to compute (e.g. "1,10,100").
      n_workers: Number of parallel workers to use when running tests.
      timeout: Per-sample timeout in seconds for compilation/execution.
      problem_file: Optional dataset override. If omitted, defaults to the
        Rust HumanEval dataset.
      language: Kept for API compatibility but only "rust" is supported.
        If not provided, defaults to "rust".
    """
    k = list(map(int, k.split(",")))
    if problem_file is None:
        problem_file = get_human_eval_dataset(language)

    results = evaluate_functional_correctness(
        sample_file,
        k,
        n_workers,
        timeout,
        problem_file,
        language,
    )
    print(results)


def main():
    fire.Fire(entry_point)


sys.exit(main())

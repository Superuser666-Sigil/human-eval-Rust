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
    sandbox_mode: Optional[str] = None,
    enforce_policy: bool = True,
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
      sandbox_mode: Sandbox mode ("docker", "firejail", "none", or None for auto-detect).
        Docker is recommended for production use. None auto-detects available sandbox.
      enforce_policy: Whether to enforce pattern-based policy filtering (default: True).
        Set to False for pure HumanEval compatibility without security filtering.
        Use --no-enforce-policy to disable policy enforcement.
    """
    k = list(map(int, k.split(",")))
    if problem_file is None:
        problem_file = get_human_eval_dataset(language)

    # Auto-detect sandbox mode if not specified
    if sandbox_mode is None or sandbox_mode == "auto":
        try:
            from human_eval.sandbox import check_docker_available, check_firejail_available
            
            if check_docker_available():
                sandbox_mode = "docker"
                print("Using Docker sandboxing (auto-detected)", file=__import__("sys").stderr)
            elif check_firejail_available():
                sandbox_mode = "firejail"
                print("Using Firejail sandboxing (auto-detected)", file=__import__("sys").stderr)
            else:
                sandbox_mode = "none"
                print("WARNING: No sandboxing available (Docker/Firejail not found)", file=__import__("sys").stderr)
                print("         Evaluation will run with process isolation only.", file=__import__("sys").stderr)
                print("         Install Docker for secure evaluation in production.", file=__import__("sys").stderr)
        except ImportError:
            sandbox_mode = "none"
    elif sandbox_mode == "none":
        print("WARNING: Sandboxing disabled via --sandbox-mode=none", file=__import__("sys").stderr)
        print("         This is UNSAFE for untrusted LLM-generated code!", file=__import__("sys").stderr)
    else:
        print(f"Using {sandbox_mode} sandboxing", file=__import__("sys").stderr)

    results = evaluate_functional_correctness(
        sample_file,
        k,
        n_workers,
        timeout,
        problem_file,
        language,
        sandbox_mode,
        enforce_policy,
    )
    print(results)


def main():
    fire.Fire(entry_point)


sys.exit(main())

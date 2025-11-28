"""
Command-line entry point for HumanEval Rust functional correctness evaluation.

Provides CLI interface using Fire for evaluating Rust code completions.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 2.1.0
"""

import sys

import fire

from human_eval.data import get_human_eval_dataset
from human_eval.evaluation import evaluate_functional_correctness


def entry_point(
    sample_file: str,
    k: str = "1,10,100",
    n_workers: int = 24,  # Optimized for H100: 24 workers (26 vCPUs - 2 reserved)
    timeout: float = 10.0,  # Optimized for H100: 10s timeout (was 3.0s) for compilation latency
    problem_file: str | None = None,
    language: str | None = None,
    sandbox_mode: str | None = None,
    allow_no_sandbox: bool = False,
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
      sandbox_mode: Sandbox mode ("firejail" or "none").
        - firejail (recommended): Uses Firejail for Linux process isolation
        - none: No sandboxing (UNSAFE - only for local dev with trusted code)
        If not specified, auto-detects Firejail availability.
      allow_no_sandbox: Allow proceeding without sandbox in non-interactive mode.
        Use with --sandbox-mode=none or when Firejail is unavailable.
        Required for automated pipelines that accept unsandboxed execution.
      enforce_policy: Whether to enforce pattern-based policy filtering (default: True).
        Set to False for pure HumanEval compatibility without security filtering.
        Use --no-enforce-policy to disable policy enforcement.
    """
    k_list: list[int] = list(map(int, k.split(",")))
    if problem_file is None:
        problem_file = get_human_eval_dataset(language)

    # Resolve sandbox mode with user interaction if needed
    try:
        from human_eval.sandbox import check_firejail_available, resolve_sandbox_mode

        # Determine if we're in interactive mode (stdin is a TTY)
        non_interactive = not sys.stdin.isatty()

        resolved_mode = resolve_sandbox_mode(
            sandbox_mode=sandbox_mode,
            allow_no_sandbox=allow_no_sandbox,
            non_interactive=non_interactive,
        )

        if resolved_mode == "firejail":
            status = check_firejail_available()
            print(f"Using Firejail sandboxing ({status.version})", file=sys.stderr)
        elif resolved_mode == "none":
            if not allow_no_sandbox:
                print(
                    "⚠ WARNING: Running without sandbox. This is UNSAFE for untrusted code!",
                    file=sys.stderr,
                )

        sandbox_mode = resolved_mode

    except ImportError:
        # Sandbox module not available
        sandbox_mode = "none"
        print(
            "WARNING: Sandbox module not available, running without sandboxing",
            file=sys.stderr,
        )
    except SystemExit:
        # User cancelled the prompt
        raise

    results = evaluate_functional_correctness(
        sample_file,
        k_list,
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


if __name__ == "__main__":
sys.exit(main())

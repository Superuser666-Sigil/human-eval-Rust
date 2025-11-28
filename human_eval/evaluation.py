"""
Functional correctness evaluation for HumanEval Rust completions.

Implements pass@k estimation and parallel test execution.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 2.0.0
"""

import itertools
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import tqdm

from human_eval.data import (
    get_human_eval_dataset,
    read_problems,
    stream_jsonl,
    write_jsonl,
)
from human_eval.execution import check_correctness
from human_eval.rust_execution import check_main_free


def estimate_pass_at_k(
    num_samples: int | list[int] | np.ndarray,
    num_correct: list[int] | np.ndarray,
    k: int,
) -> np.ndarray:
    """
    Estimates pass@k of each problem and returns them in an array.
    """

    def estimator(n: int, c: int, k: int) -> float:
        """
        Calculates 1 - comb(n - c, k) / comb(n, k).
        """
        if n - c < k:
            return 1.0
        return 1.0 - np.prod(1.0 - k / np.arange(n - c + 1, n + 1))

    if isinstance(num_samples, int):
        num_samples_it = itertools.repeat(num_samples, len(num_correct))
    else:
        assert len(num_samples) == len(num_correct)
        num_samples_it = iter(num_samples)

    return np.array(
        [estimator(int(n), int(c), k) for n, c in zip(num_samples_it, num_correct)]
    )


def _resolve_language(language: str | None, problem_file: str) -> str:
    """
    Resolves the language for evaluation. Only Rust is supported.
    """
    if language and language.lower() != "rust":
        raise ValueError(
            f"Only Rust is supported. Got language: {language}. "
            "This evaluator only supports Rust code evaluation."
        )
    return "rust"


def evaluate_functional_correctness(
    sample_file: str,
    k: list[int] = [1, 10, 100],
    n_workers: int = 4,
    timeout: float = 3.0,
    problem_file: str | None = None,
    language: str | None = None,
    sandbox_mode: str | None = None,
    enforce_policy: bool = True,
):
    """
    Evaluates the functional correctness of generated samples, and writes
    results to f"{sample_file}_results.jsonl" (one JSON object per sample result).

    Args:
        sample_file: Path to JSONL file with completions
        k: List of pass@k values to compute
        n_workers: Number of parallel workers
        timeout: Per-sample timeout in seconds
        problem_file: Optional problem dataset file
        language: Language (only "rust" supported)
        sandbox_mode: Sandbox mode ("firejail", "none", or None for auto-detect)
        enforce_policy: Whether to enforce pattern-based policy filtering (default: True).
            Set to False for pure HumanEval compatibility without security filtering.
    """

    if problem_file is None:
        problem_file = get_human_eval_dataset(language or "rust")

    resolved_language = _resolve_language(language, problem_file)

    problems = read_problems(problem_file)

    # Check the generated samples against test suites.
    with ThreadPoolExecutor(max_workers=n_workers) as executor:

        futures = []
        completion_id = Counter()
        n_samples = 0
        results = defaultdict(list)

        print("Reading samples...")
        for sample in tqdm.tqdm(stream_jsonl(sample_file)):
            task_id = sample["task_id"]
            problem = problems.get(task_id)

            if problem is None:
                raise KeyError(f"Unknown task_id '{task_id}' in {sample_file}.")

            completion = sample["completion"]
            args = (
                problem,
                completion,
                timeout,
                completion_id[task_id],
                resolved_language,
                sandbox_mode,
                enforce_policy,
            )
            future = executor.submit(check_correctness, *args)
            futures.append(future)
            completion_id[task_id] += 1
            n_samples += 1

        assert len(completion_id) == len(problems), "Some problems are not attempted."

        print("Running test suites...")
        all_results_list = []
        for future in tqdm.tqdm(as_completed(futures), total=len(futures)):
            result = future.result()
            results[result["task_id"]].append((result["completion_id"], result))
            all_results_list.append(result)

    # Track compile rate and main-free rate
    compile_ok_count = sum(1 for r in all_results_list if r.get("compile_ok") is True)
    compile_total = sum(1 for r in all_results_list if r.get("compile_ok") is not None)
    compile_rate = compile_ok_count / compile_total if compile_total > 0 else 0.0

    main_free_count = sum(1 for r in all_results_list if r.get("main_free") is True)
    main_free_rate = (
        main_free_count / len(all_results_list) if all_results_list else 0.0
    )

    # Calculate pass@k.
    total, correct = [], []
    for result in results.values():
        result.sort()
        passed = [r[1]["passed"] for r in result]
        total.append(len(passed))
        correct.append(sum(passed))
    total = np.array(total)
    correct = np.array(correct)

    ks = k
    pass_at_k = {
        f"pass@{k}": estimate_pass_at_k(total, correct, k).mean()
        for k in ks
        if (total >= k).all()
    }

    # Add compile rate and main-free rate to metrics
    pass_at_k["compile_rate"] = compile_rate
    pass_at_k["main_free_rate"] = main_free_rate

    # Print metrics
    print("\nMetrics:")
    print(f"  Compile rate: {compile_rate:.4f} ({compile_rate * 100:.2f}%)")
    print(f"  Main-free rate: {main_free_rate:.4f} ({main_free_rate * 100:.2f}%)")
    for metric, value in sorted(pass_at_k.items()):
        if metric not in ("compile_rate", "main_free_rate"):
            print(f"  {metric}: {value:.4f} ({value * 100:.2f}%)")

    # Finally, save the results in one file:
    # Writes to "<sample_file>_results.jsonl" (one JSON object per sample result)
    # Ensure all completions are included (never drop silently)
    def combine_results():
        # Read all samples to ensure we don't miss any
        samples_by_task = defaultdict(list)
        for sample in stream_jsonl(sample_file):
            samples_by_task[sample["task_id"]].append(sample)

        # Match results with samples
        for task_id in sorted(samples_by_task.keys()):
            task_samples = samples_by_task[task_id]
            task_results = results.get(task_id, [])
            task_results.sort()

            # Ensure we have a result for every sample
            for i, sample in enumerate(task_samples):
                if i < len(task_results):
                    result = task_results[i][1]
                    # Merge enhanced schema into sample
                    sample.update(
                        {
                            "compile_ok": result.get("compile_ok"),
                            "test_ok": result.get("test_ok"),
                            "error_type": result.get("error_type"),
                            "stderr": result.get("stderr", ""),
                            "main_free": result.get("main_free"),
                            "result": result.get("result", ""),
                            "passed": result.get("passed", False),
                        }
                    )
                else:
                    # Missing result - create placeholder (never drop silently)
                    sample.update(
                        {
                            "compile_ok": None,
                            "test_ok": None,
                            "error_type": "runtime_error",
                            "stderr": "missing result",
                            "main_free": check_main_free(sample.get("completion", "")),
                            "result": "filtered: missing result",
                            "passed": False,
                        }
                    )
            yield sample

    out_file = sample_file + "_results.jsonl"
    print(f"Writing results to {out_file}...")
    write_jsonl(out_file, tqdm.tqdm(combine_results(), total=n_samples))

    return pass_at_k

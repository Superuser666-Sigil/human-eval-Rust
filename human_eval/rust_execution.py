import multiprocessing
import os
import subprocess
from typing import Dict, Optional

from human_eval.execution import (
    TimeoutException,
    create_tempdir,
    reliability_guard,
    time_limit,
)

DISALLOWED_COMPLETION_PATTERNS = [
    "std::fs",
    "std::process",
    "command::new",
    "std::thread::spawn",
    "unsafe",
]


def _sanitize_rust_completion(completion: str) -> Optional[str]:
    lowered_completion = completion.lower()
    for pattern in DISALLOWED_COMPLETION_PATTERNS:
        if pattern in lowered_completion:
            return f"disallowed usage of {pattern}"
    return None


def _rust_unsafe_execute(problem: Dict, completion: str, timeout: float, result):
    with create_tempdir() as temp_dir:
        import shutil

        rmtree = shutil.rmtree
        rmdir = os.rmdir
        chdir = os.chdir
        popen = subprocess.Popen

        reliability_guard()
        subprocess.Popen = popen

        try:
            violation = _sanitize_rust_completion(completion)
            if violation:
                result.append(f"failed: {violation}")
                return

            source_path = os.path.join(temp_dir, "solution.rs")
            test_binary = os.path.join(temp_dir, "solution_test")

            with open(source_path, "w", encoding="utf-8") as source_file:
                source_file.write(problem["prompt"])
                source_file.write(completion)
                source_file.write("\n\n")
                source_file.write(problem["test"])
                source_file.write("\n")

            compile_command = [
                "rustc",
                "--edition=2021",
                "--test",
                source_path,
                "-o",
                test_binary,
            ]

            try:
                with time_limit(timeout):
                    compile_result = subprocess.run(
                        compile_command,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )

                    if compile_result.returncode != 0:
                        failure = compile_result.stderr.strip() or compile_result.stdout.strip()
                        result.append(f"failed: {failure or 'compile error'}")
                        return

                    test_result = subprocess.run(
                        [test_binary],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )
            except (TimeoutException, subprocess.TimeoutExpired):
                result.append("timed out")
                return
            except BaseException as exc:  # noqa: BLE001
                result.append(f"failed: {exc}")
                return

            if test_result.returncode == 0:
                result.append("passed")
            else:
                failure = test_result.stderr.strip() or test_result.stdout.strip()
                result.append(f"failed: {failure or 'tests failed'}")
        finally:
            shutil.rmtree = rmtree
            os.rmdir = rmdir
            os.chdir = chdir
            subprocess.Popen = popen


def rust_check_correctness(
    problem: Dict, completion: str, timeout: float, completion_id: Optional[int] = None
) -> Dict:
    """
    Evaluate a Rust completion by compiling and running its tests.
    """

    manager = multiprocessing.Manager()
    result = manager.list()

    process = multiprocessing.Process(
        target=_rust_unsafe_execute, args=(problem, completion, timeout, result)
    )
    process.start()
    process.join(timeout=timeout + 1)
    if process.is_alive():
        process.kill()

    if not result:
        result.append("timed out")

    return dict(
        task_id=problem["task_id"],
        passed=result[0] == "passed",
        result=result[0],
        completion_id=completion_id,
    )

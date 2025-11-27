"""
Rust-specific execution module for HumanEval evaluation.

Handles compilation and test execution of Rust code completions with sandboxing support.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 1.3.8
"""

import multiprocessing
import os
import subprocess

# Use relative import to avoid circular dependency with execution.py
from .execution import TimeoutException, create_tempdir, reliability_guard, time_limit

# Try to import sandbox module (optional)
try:
    from .sandbox import SandboxError, run_binary_sandboxed, run_rustc_sandboxed

    SANDBOX_AVAILABLE = True
except ImportError:
    SANDBOX_AVAILABLE = False
    SandboxError = Exception

    # Define stub functions to satisfy type checker
    # These will never be called because SANDBOX_AVAILABLE is False
    def run_rustc_sandboxed(
        source_file: str,
        output_binary: str,
        command_args: list[str],
        timeout: float = 30.0,
        capture_output: bool = True,
        sandbox_mode: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        raise RuntimeError("Sandbox not available")

    def run_binary_sandboxed(
        binary_path: str,
        timeout: float = 30.0,
        capture_output: bool = True,
        sandbox_mode: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        raise RuntimeError("Sandbox not available")


DISALLOWED_COMPLETION_PATTERNS = [
    # Filesystem operations
    "std::fs",
    "std::path",
    "std::io::write",
    "std::io::read",
    "std::io::copy",
    "std::io::create",
    "std::io::remove",
    "std::io::rename",
    "std::io::metadata",
    "std::io::symlink",
    "std::io::hard_link",
    "std::io::canonicalize",
    "std::io::read_dir",
    "std::io::read_to_string",
    "std::io::read_to_end",
    "std::io::read_exact",
    "std::io::write_all",
    "std::io::write_fmt",
    "std::io::flush",
    "std::io::seek",
    "std::io::set_permissions",
    "std::io::remove_file",
    "std::io::remove_dir",
    "std::io::remove_dir_all",
    "std::io::create_dir",
    "std::io::create_dir_all",
    "std::io::rename",
    "std::io::copy",
    "std::io::hard_link",
    "std::io::symlink_metadata",
    "std::io::read_link",
    "std::io::canonicalize",
    "std::io::File::create",
    "std::io::File::open",
    "std::io::File::create_new",
    "std::io::File::read",
    "std::io::File::write",
    # Process and system operations
    "std::process",
    "std::process::Command",
    "std::process::Command::new",
    "std::process::Command::spawn",
    "std::process::Command::output",
    "std::process::Command::status",
    "std::process::exit",
    "std::process::abort",
    "std::process::id",
    "std::process::parent_id",
    "command::new",
    "command::spawn",
    "command::output",
    # Network operations
    "std::net",
    "std::net::TcpStream",
    "std::net::TcpListener",
    "std::net::UdpSocket",
    "std::net::UnixStream",
    "std::net::UnixListener",
    "std::net::SocketAddr",
    "std::net::IpAddr",
    "std::net::Ipv4Addr",
    "std::net::Ipv6Addr",
    "std::net::ToSocketAddrs",
    "std::net::lookup_host",
    "reqwest",
    "ureq",
    "hyper",
    "tokio::net",
    "tokio::net::TcpStream",
    "tokio::net::TcpListener",
    "tokio::net::UdpSocket",
    "tokio::net::UnixStream",
    "tokio::net::UnixListener",
    # Threading and concurrency
    "std::thread",
    "std::thread::spawn",
    "std::thread::Builder",
    "std::thread::Thread",
    "std::thread::park",
    "std::thread::yield_now",
    "std::thread::sleep",
    "std::thread::available_parallelism",
    "std::sync::mpsc",
    "std::sync::mpsc::channel",
    "std::sync::mpsc::sync_channel",
    "std::sync::Arc",
    "std::sync::Mutex",
    "std::sync::RwLock",
    "std::sync::Condvar",
    "std::sync::Barrier",
    "std::sync::Once",
    "std::sync::atomic",
    "tokio::spawn",
    "tokio::task",
    "tokio::runtime",
    # Unsafe code
    "unsafe",
    "unsafe fn",
    "unsafe trait",
    "unsafe impl",
    "unsafe block",
    "unsafe {}",
    # Memory operations
    "std::alloc",
    "std::alloc::alloc",
    "std::alloc::dealloc",
    "std::alloc::realloc",
    "std::alloc::Layout",
    "std::ptr",
    "std::ptr::null",
    "std::ptr::null_mut",
    "std::ptr::read",
    "std::ptr::write",
    "std::ptr::copy",
    "std::ptr::copy_nonoverlapping",
    "std::ptr::swap",
    "std::ptr::replace",
    "std::ptr::drop_in_place",
    "std::mem",
    "std::mem::forget",
    "std::mem::transmute",
    "std::mem::zeroed",
    "std::mem::uninitialized",
    "std::mem::replace",
    "std::mem::swap",
    "std::mem::take",
    "std::mem::size_of",
    "std::mem::align_of",
    "std::mem::size_of_val",
    "std::mem::align_of_val",
    "std::mem::needs_drop",
    "std::mem::drop",
    "std::mem::forget",
    "std::mem::transmute",
    "std::mem::zeroed",
    "std::mem::uninitialized",
    "std::mem::MaybeUninit",
    # Environment and system
    "std::env",
    "std::env::var",
    "std::env::vars",
    "std::env::set_var",
    "std::env::remove_var",
    "std::env::current_dir",
    "std::env::set_current_dir",
    "std::env::args",
    "std::env::args_os",
    "std::env::consts",
    "std::env::home_dir",
    "std::env::temp_dir",
    # Time and system calls
    "std::time::SystemTime",
    "std::time::UNIX_EPOCH",
    "std::time::Duration",
    "std::time::Instant",
    # External process execution
    "std::os",
    "std::os::unix",
    "std::os::windows",
    "std::os::linux",
    "std::os::macos",
    # FFI (Foreign Function Interface)
    "extern",
    'extern "C"',
    'extern "system"',
    "libc",
    "winapi",
    # Dynamic loading
    "std::ffi",
    "std::ffi::CString",
    "std::ffi::CStr",
    "std::ffi::OsString",
    "std::ffi::OsStr",
    "std::ffi::NulError",
    # Signal handling
    "std::signal",
    "libc::signal",
    # Other dangerous patterns
    "std::panic",
    "std::panic::panic",
    "std::panic::panic_any",
    "std::panic::set_hook",
    "std::panic::take_hook",
    "std::panic::catch_unwind",
    "std::panic::resume_unwind",
    "std::panic::AssertUnwindSafe",
]


def _sanitize_rust_completion(completion: str) -> str | None:
    lowered_completion = completion.lower()
    for pattern in DISALLOWED_COMPLETION_PATTERNS:
        if pattern.lower() in lowered_completion:
            return f"disallowed usage of {pattern}"
    return None


def _extract_function_body(completion: str, entry_point: str) -> str:
    """
    Extract the function body from a completion, removing extra code like main() functions.

    Args:
        completion: Raw completion text from the model
        entry_point: Name of the function we're looking for (e.g., "has_close_elements")

    Returns:
        Cleaned completion with only the target function body
    """
    import re

    # Step 1: Remove markdown code blocks
    if "```rust" in completion:
        # Extract content between ```rust and ```
        rust_match = re.search(r"```rust\s*(.*?)\s*```", completion, re.DOTALL)
        if rust_match:
            completion = rust_match.group(1)
    elif "```" in completion:
        # Generic code block
        code_match = re.search(r"```[^\n]*\s*(.*?)\s*```", completion, re.DOTALL)
        if code_match:
            completion = code_match.group(1)

    completion = completion.strip()

    # Step 2: Try to find the function that matches entry_point
    # Pattern: fn entry_point(...) -> ... { ... }
    # Note: Construct pattern carefully to avoid f-string bracket issues
    # The pattern matches: fn entry_point(...) -> [anything except {] { ... }
    not_brace_pattern = r"[^{]"  # Match any character except opening brace
    fn_pattern = rf"fn\s+{re.escape(entry_point)}\s*\([^)]*\)\s*(?:->{not_brace_pattern}*)?\s*\{{"
    fn_match = re.search(fn_pattern, completion, re.MULTILINE | re.DOTALL)

    if fn_match:
        # Found the target function, extract from the opening brace
        start_pos = fn_match.end() - 1  # Position of opening brace
        brace_count = 0
        end_pos = start_pos

        # Find matching closing brace
        for i in range(start_pos, len(completion)):
            if completion[i] == "{":
                brace_count += 1
            elif completion[i] == "}":
                brace_count -= 1
                if brace_count == 0:
                    end_pos = i + 1
                    break

        if brace_count == 0:
            # Extract just the function body (without the function signature)
            # The prompt already has the signature, we just need the body
            function_body = completion[start_pos + 1:end_pos - 1].strip()
            return function_body

    # Step 2b: If completion is just the function body (no signature), check if it starts with {
    # This handles cases where the model generates just the body
    if completion.strip().startswith("{"):
        # Extract content between first { and matching }
        brace_count = 0
        start_pos = 0
        end_pos = len(completion)

        for i, char in enumerate(completion):
            if char == "{":
                if brace_count == 0:
                    start_pos = i + 1
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    end_pos = i
                    return completion[start_pos:end_pos].strip()

        # If we didn't find a matching brace, return everything after the first {
        if brace_count > 0:
            return completion[start_pos:].strip()

    # Step 3: If we didn't find the target function, try to extract any function body
    # and remove main() functions
    lines = completion.split("\n")
    cleaned_lines = []
    in_main = False
    brace_count = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip standalone main() functions
        if re.match(r"^fn\s+main\s*\([^)]*\)\s*(?:->[^{]*)?\s*\{", stripped):
            in_main = True
            brace_count = 1
            # Skip until matching closing brace
            i += 1
            while i < len(lines) and brace_count > 0:
                line = lines[i]
                brace_count += line.count("{") - line.count("}")
                i += 1
            continue

        # Skip lines that are part of a main() function we're skipping
        if in_main:
            brace_count += line.count("{") - line.count("}")
            if brace_count <= 0:
                in_main = False
            i += 1
            continue

        # Keep other lines
        cleaned_lines.append(line)
        i += 1

    result = "\n".join(cleaned_lines).strip()

    # Step 4: Remove common extra patterns
    # Remove "Example usage:" or "// Example usage:" blocks
    result = re.sub(
        r"(?i)(//\s*)?(example\s+usage|usage\s+example):.*", "", result, flags=re.DOTALL
    )

    # Remove standalone use statements that aren't needed (keep them if they're at the top)
    # This is tricky, so we'll be conservative and only remove obviously wrong ones
    result = re.sub(
        r"^use\s+std::collections::Vec;?\s*$", "", result, flags=re.MULTILINE
    )  # Vec is in std::vec, not collections

    return result.strip()


def _rust_unsafe_execute(
    problem: dict,
    completion: str,
    timeout: float,
    result,
    sandbox_mode: str | None = None,
    enforce_policy: bool = True,
):
    with create_tempdir() as temp_dir:
        import shutil

        rmtree = shutil.rmtree
        rmdir = os.rmdir
        chdir = os.chdir
        popen = subprocess.Popen

        reliability_guard()
        subprocess.Popen = popen

        try:
            # Clean up completion: extract function body and remove extra code
            entry_point = problem.get("entry_point", "")
            cleaned_completion = _extract_function_body(completion, entry_point)

            # Policy enforcement (pattern filtering) - can be disabled for pure HumanEval compatibility
            if enforce_policy:
                violation = _sanitize_rust_completion(cleaned_completion)
                if violation:
                    result.append(f"failed: {violation}")
                    return

            source_path = os.path.join(temp_dir, "solution.rs")
            test_binary = os.path.join(temp_dir, "solution_test")

            with open(source_path, "w", encoding="utf-8") as source_file:
                source_file.write(problem["prompt"])
                source_file.write(cleaned_completion)
                source_file.write("\n\n")
                source_file.write(problem["test"])
                source_file.write("\n")

            compile_args = ["--edition=2021", "--test"]

            # Use sandboxing if available and requested
            # sandbox_mode=None means "auto-detect" (use sandbox if available)
            # sandbox_mode="none" means explicitly disable sandboxing
            # The sandbox module handles None as auto-detect
            effective_mode = sandbox_mode  # None = auto-detect in sandbox.py

            use_sandbox = SANDBOX_AVAILABLE and effective_mode != "none"

            try:
                with time_limit(timeout):
                    if use_sandbox:
                        try:
                            compile_result = run_rustc_sandboxed(
                                source_path,
                                test_binary,
                                compile_args,
                                timeout=timeout,
                                capture_output=True,
                                sandbox_mode=effective_mode,  # may be None -> auto-detect
                            )
                        except SandboxError as e:
                            result.append(f"failed: sandbox error: {e}")
                            return
                    else:
                        compile_result = subprocess.run(
                            ["rustc"] + compile_args + [source_path, "-o", test_binary],
                            capture_output=True,
                            text=True,
                            timeout=timeout,
                        )

                    if compile_result.returncode != 0:
                        failure = (
                            compile_result.stderr.strip()
                            or compile_result.stdout.strip()
                        )
                        result.append(f"failed: {failure or 'compile error'}")
                        return

                    # Run tests (also sandboxed if using sandbox)
                    if use_sandbox:
                        try:
                            test_result = run_binary_sandboxed(
                                test_binary,
                                timeout=timeout,
                                capture_output=True,
                                sandbox_mode=effective_mode,  # may be None -> auto-detect
                            )
                        except SandboxError as e:
                            result.append(f"failed: sandbox error: {e}")
                            return
                    else:
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
    problem: dict,
    completion: str,
    timeout: float,
    completion_id: int | None = None,
    sandbox_mode: str | None = None,
    enforce_policy: bool = True,
) -> dict:
    """
    Evaluate a Rust completion by compiling and running its tests.

    Args:
        problem: Problem dictionary with prompt, test, etc.
        completion: Generated code completion
        timeout: Timeout in seconds
        completion_id: Optional completion ID for tracking
        sandbox_mode: Optional sandbox mode ("docker", "firejail", "none", or None for auto-detect)
        enforce_policy: Whether to enforce pattern-based policy filtering (default: True).
            Set to False for pure HumanEval compatibility without security filtering.

    Returns:
        Dictionary with task_id, passed, result, and completion_id
    """

    manager = multiprocessing.Manager()
    result = manager.list()

    process = multiprocessing.Process(
        target=_rust_unsafe_execute,
        args=(problem, completion, timeout, result, sandbox_mode, enforce_policy),
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

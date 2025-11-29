"""
Rust-specific execution module for HumanEval evaluation.

Handles compilation and test execution of Rust code completions with sandboxing support.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 2.1.0
"""

import multiprocessing
import os
import re
import shutil
import subprocess
import time
import unicodedata

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
    # Compile-time code execution
    "include!",
    "include_str!",
    "include_bytes!",
    "env!",
    "option_env!",
    "concat!",
    "file!",
    "line!",
    "column!",
    "module_path!",
    # Assembly
    "asm!",
    "global_asm!",
    # FFI/Linking
    "#[link",
    "#[no_mangle]",
    "#[export_name",
    "build.rs",
    # Proc macros
    "proc_macro",
    "#[derive(",
    # Additional dangerous patterns
    "std::intrinsics",
    "core::intrinsics",
]


def _normalize_unicode(text: str) -> str:
    """Normalize Unicode to ASCII to prevent homoglyph attacks."""

    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _sanitize_rust_completion(completion: str) -> str | None:
    """Check for disallowed patterns with Unicode normalization."""

    normalized = _normalize_unicode(completion.lower())

    for pattern in DISALLOWED_COMPLETION_PATTERNS:
        if pattern.lower() in normalized:
            return f"disallowed usage of {pattern}"

    if re.search(
        r"r#*\".*?(unsafe|std::fs|std::process).*?\"#*",
        completion,
        re.IGNORECASE | re.DOTALL,
    ):
        return "disallowed pattern in raw string"

    return None


MAX_COMPLETION_LENGTH = 100_000
MAX_COMPLETION_LINES = 5_000


def _validate_completion(completion: str) -> str | None:
    """Validate completion content. Returns error message or None."""

    if not completion:
        return "empty completion"

    if len(completion) > MAX_COMPLETION_LENGTH:
        return f"completion too long ({len(completion)} > {MAX_COMPLETION_LENGTH})"

    if completion.count("\n") > MAX_COMPLETION_LINES:
        return f"too many lines (> {MAX_COMPLETION_LINES})"

    if "\x00" in completion:
        return "null byte in completion"

    try:
        completion.encode("utf-8")
    except UnicodeEncodeError:
        return "invalid UTF-8 encoding"

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
            function_body = completion[start_pos + 1 : end_pos - 1].strip()
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


def _check_rustc_available(sandbox_mode: str | None = None) -> tuple[bool, str | None]:
    """
    Preflight check for rustc availability.
    Returns (available, error_message).
    """
    try:
        # Check local rustc (for firejail, none, or any mode - firejail uses host rustc)
        result = subprocess.run(
            ["rustc", "--version"],
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if result.returncode == 0:
            return True, None
        return False, "rustc --version failed"
    except FileNotFoundError:
        return False, "rustc not found in PATH"
    except subprocess.TimeoutExpired:
        return False, "rustc version check timed out"
    except Exception as e:
        return False, f"rustc check error: {e}"


def check_main_free(completion: str) -> bool:
    """Check if completion contains fn main."""
    import re

    # Check for fn main() patterns
    main_pattern = r"fn\s+main\s*\("
    return not bool(re.search(main_pattern, completion, re.IGNORECASE))


def _run_clippy_check(source_path: str, timeout: float) -> tuple[bool, str]:
    """Run clippy on compiled code and return (passed, warnings)."""

    result = subprocess.run(
        ["cargo", "clippy", "--", "-D", "warnings"],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=os.path.dirname(source_path),
    )
    return result.returncode == 0, result.stderr


class ReliabilityContext:
    """Context manager that provides isolated reliability guards.

    IMPORTANT: This must save and restore ALL functions that reliability_guard()
    modifies, otherwise the os module will be corrupted for subsequent code
    (including pytest teardown), causing TypeError: 'NoneType' object is not callable.
    """

    # Sentinel for "module not present in sys.modules"
    _NOT_PRESENT = object()

    def __init__(self, maximum_memory_bytes: int | None = None):
        self.maximum_memory_bytes = maximum_memory_bytes
        self._original_os: dict[str, object] = {}
        self._original_shutil: dict[str, object] = {}
        self._original_subprocess: dict[str, object] = {}
        self._original_builtins: dict[str, object] = {}
        self._original_sys_modules: dict[str, object] = {}
        self._faulthandler_was_enabled: bool = False
        self._original_help: object = None

    def __enter__(self):
        import builtins
        import faulthandler
        import sys

        # Store faulthandler state - reliability_guard calls faulthandler.disable()
        self._faulthandler_was_enabled = faulthandler.is_enabled()

        # Store __builtins__["help"] - reliability_guard sets it to None
        # Note: __builtins__ can be a dict or module depending on context
        if isinstance(__builtins__, dict):
            self._original_help = __builtins__.get("help")
        else:
            self._original_help = getattr(__builtins__, "help", None)

        # Store ALL os module functions that reliability_guard() sets to None
        self._original_os = {
            "kill": getattr(os, "kill", None),
            "system": getattr(os, "system", None),
            "putenv": getattr(os, "putenv", None),
            "remove": getattr(os, "remove", None),
            "removedirs": getattr(os, "removedirs", None),
            "rmdir": getattr(os, "rmdir", None),
            "fchdir": getattr(os, "fchdir", None),
            "setuid": getattr(os, "setuid", None),
            "fork": getattr(os, "fork", None),
            "forkpty": getattr(os, "forkpty", None),
            "killpg": getattr(os, "killpg", None),
            "rename": getattr(os, "rename", None),
            "renames": getattr(os, "renames", None),
            "truncate": getattr(os, "truncate", None),
            "replace": getattr(os, "replace", None),
            "unlink": getattr(os, "unlink", None),
            "fchmod": getattr(os, "fchmod", None),
            "fchown": getattr(os, "fchown", None),
            "chmod": getattr(os, "chmod", None),
            "chown": getattr(os, "chown", None),
            "chroot": getattr(os, "chroot", None),
            "lchflags": getattr(os, "lchflags", None),
            "lchmod": getattr(os, "lchmod", None),
            "lchown": getattr(os, "lchown", None),
            "getcwd": getattr(os, "getcwd", None),
            "chdir": getattr(os, "chdir", None),
        }

        # Store shutil functions
        self._original_shutil = {
            "rmtree": getattr(shutil, "rmtree", None),
            "move": getattr(shutil, "move", None),
            "chown": getattr(shutil, "chown", None),
        }

        # Store subprocess functions
        self._original_subprocess = {
            "Popen": getattr(subprocess, "Popen", None),
        }

        # Store builtins
        self._original_builtins = {
            "exit": getattr(builtins, "exit", None),
            "quit": getattr(builtins, "quit", None),
        }

        # Store sys.modules entries that reliability_guard sets to None
        for mod_name in ("ipdb", "joblib", "resource", "psutil", "tkinter"):
            self._original_sys_modules[mod_name] = sys.modules.get(
                mod_name, self._NOT_PRESENT
            )

        reliability_guard(self.maximum_memory_bytes)
        return self

    def __exit__(self, *args):
        import builtins
        import faulthandler
        import sys

        # Restore faulthandler state
        if self._faulthandler_was_enabled:
            faulthandler.enable()

        # Restore __builtins__["help"]
        if self._original_help is not None:
            if isinstance(__builtins__, dict):
                __builtins__["help"] = self._original_help
            else:
                setattr(__builtins__, "help", self._original_help)

        # Restore ALL os module functions
        for name, func in self._original_os.items():
            if func is not None:
                setattr(os, name, func)

        # Restore shutil functions
        for name, func in self._original_shutil.items():
            if func is not None:
                setattr(shutil, name, func)

        # Restore subprocess functions
        for name, func in self._original_subprocess.items():
            if func is not None:
                setattr(subprocess, name, func)

        # Restore builtins
        for name, func in self._original_builtins.items():
            if func is not None:
                setattr(builtins, name, func)

        # Restore sys.modules entries
        for mod_name, original in self._original_sys_modules.items():
            if original is self._NOT_PRESENT:
                # Module wasn't present before, remove if reliability_guard added None
                sys.modules.pop(mod_name, None)
            else:
                # Restore original value (could be None or actual module)
                sys.modules[mod_name] = original


DETERMINISTIC_RUSTC_FLAGS = [
    "--edition=2021",
    "--test",
    "-C",
    "opt-level=0",
    "-C",
    "debuginfo=0",
    "-C",
    "incremental=false",
]


def _rust_unsafe_execute(
    problem: dict,
    completion: str,
    timeout: float,
    result,
    sandbox_mode: str | None = None,
    enforce_policy: bool = True,
):
    """
    Execute Rust code and return enhanced result schema.
    Result dict structure:
    {
        "compile_ok": bool | None,
        "test_ok": bool | None,
        "error_type": str | None,  # "infra_missing_toolchain" | "compile_error" | "runtime_error" | "assertion_failure"
        "stderr": str,
        "passed": bool,
        "main_free": bool,
        "result": str,  # Legacy field for compatibility
    }
    """
    with create_tempdir() as temp_dir, ReliabilityContext():
        result_dict = {
            "compile_ok": None,
            "test_ok": None,
            "clippy_ok": None,
            "compile_time_ms": None,
            "binary_size_bytes": None,
            "error_type": None,
            "stderr": "",
            "passed": False,
            "main_free": check_main_free(completion),
            "result": "",
        }

        rustc_available, rustc_error = _check_rustc_available(sandbox_mode)
        if not rustc_available:
            result_dict["error_type"] = "infra_missing_toolchain"
            result_dict["stderr"] = rustc_error or "rustc not available"
            result_dict["result"] = f"failed: {result_dict['stderr']}"
            result.append(result_dict)
            return

        validation_error = _validate_completion(completion)
        if validation_error:
            result_dict["error_type"] = "compile_error"
            result_dict["stderr"] = validation_error
            result_dict["result"] = f"filtered: {validation_error}"
            result.append(result_dict)
            return

        entry_point = problem.get("entry_point", "")
        cleaned_completion = _extract_function_body(completion, entry_point)

        if enforce_policy:
            violation = _sanitize_rust_completion(cleaned_completion)
            if violation:
                result_dict["error_type"] = "compile_error"
                result_dict["stderr"] = violation
                result_dict["result"] = f"failed: {violation}"
                result.append(result_dict)
                return

        source_path = os.path.join(temp_dir, "solution.rs")
        test_binary = os.path.join(temp_dir, "solution_test")

        with open(source_path, "w", encoding="utf-8") as source_file:
            source_file.write(problem["prompt"])
            source_file.write(cleaned_completion)
            source_file.write("\n\n")
            source_file.write(problem["test"])
            source_file.write("\n")

        compile_args = DETERMINISTIC_RUSTC_FLAGS.copy()

        effective_mode = sandbox_mode
        use_sandbox = SANDBOX_AVAILABLE and effective_mode != "none"

        timed_out = None
        try:
            with time_limit(timeout) as timed_out_event:
                timed_out = timed_out_event
                start_time = time.perf_counter()
                if use_sandbox:
                    try:
                        compile_result = run_rustc_sandboxed(
                            source_path,
                            test_binary,
                            compile_args,
                            timeout=timeout,
                            capture_output=True,
                            sandbox_mode=effective_mode,
                        )
                    except SandboxError as e:
                        result_dict["error_type"] = "infra_missing_toolchain"
                        result_dict["stderr"] = str(e)
                        result_dict["result"] = f"failed: sandbox error: {e}"
                        result.append(result_dict)
                        return
                else:
                    compile_result = subprocess.run(
                        ["rustc"] + compile_args + [source_path, "-o", test_binary],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )

                result_dict["compile_time_ms"] = int(
                    (time.perf_counter() - start_time) * 1000
                )
                result_dict["compile_ok"] = compile_result.returncode == 0
                if compile_result.returncode != 0:
                    failure = (
                        compile_result.stderr.strip() or compile_result.stdout.strip()
                    )
                    result_dict["error_type"] = "compile_error"
                    result_dict["stderr"] = failure or "compile error"
                    result_dict["result"] = f"failed: {result_dict['stderr']}"
                    result.append(result_dict)
                    return

                if os.path.exists(test_binary):
                    result_dict["binary_size_bytes"] = os.path.getsize(test_binary)

                if shutil.which("cargo"):
                    try:
                        clippy_ok, clippy_stderr = _run_clippy_check(
                            source_path, timeout
                        )
                        result_dict["clippy_ok"] = clippy_ok
                        if not clippy_ok:
                            result_dict["stderr"] = clippy_stderr
                    except Exception as exc:  # noqa: BLE001
                        result_dict["clippy_ok"] = False
                        result_dict["stderr"] = str(exc)

                if use_sandbox:
                    try:
                        test_result = run_binary_sandboxed(
                            test_binary,
                            timeout=timeout,
                            capture_output=True,
                            sandbox_mode=effective_mode,
                        )
                    except SandboxError as e:
                        result_dict["error_type"] = "runtime_error"
                        result_dict["stderr"] = str(e)
                        result_dict["result"] = f"failed: sandbox error: {e}"
                        result.append(result_dict)
                        return
                else:
                    test_result = subprocess.run(
                        [test_binary],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )

                if timed_out and timed_out.is_set():
                    raise TimeoutException("Timed out!")

                result_dict["test_ok"] = test_result.returncode == 0
                if test_result.returncode == 0:
                    result_dict["passed"] = True
                    result_dict["result"] = "passed"
                else:
                    failure = test_result.stderr.strip() or test_result.stdout.strip()
                    result_dict["error_type"] = "assertion_failure"
                    result_dict["stderr"] = failure or "tests failed"
                    result_dict["result"] = f"failed: {result_dict['stderr']}"

        except (TimeoutException, subprocess.TimeoutExpired):
            result_dict["error_type"] = "runtime_error"
            result_dict["stderr"] = "timeout"
            result_dict["result"] = "timed out"
        except BaseException as exc:  # noqa: BLE001
            result_dict["error_type"] = "runtime_error"
            result_dict["stderr"] = str(exc)
            result_dict["result"] = f"failed: {exc}"

            result.append(result_dict)


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
        sandbox_mode: Optional sandbox mode ("firejail", "none", or None for auto-detect)
        enforce_policy: Whether to enforce pattern-based policy filtering (default: True).
            Set to False for pure HumanEval compatibility without security filtering.

    Returns:
        Dictionary with enhanced schema:
        {
            "task_id": str,
            "completion": str,
            "completion_id": int | None,
            "compile_ok": bool | None,
            "test_ok": bool | None,
            "error_type": str | None,
            "stderr": str,
            "passed": bool,
            "main_free": bool,
            "result": str,  # Legacy field
        }
    """

    manager = multiprocessing.Manager()
    try:
        result = manager.list()

        process = multiprocessing.Process(
            target=_rust_unsafe_execute,
            args=(problem, completion, timeout, result, sandbox_mode, enforce_policy),
        )
        process.start()
        process.join(timeout=timeout + 1)
        if process.is_alive():
            process.kill()
            process.join()

        if not result:
            result_dict = {
                "compile_ok": None,
                "test_ok": None,
                "error_type": "runtime_error",
                "stderr": "process timeout",
                "passed": False,
                "main_free": check_main_free(completion),
                "result": "timed out",
            }
            result.append(result_dict)

        result_dict = (
            result[0]
            if isinstance(result[0], dict)
            else {"result": result[0], "passed": result[0] == "passed"}
        )

        return dict(
            task_id=problem["task_id"],
            completion=completion,
            completion_id=completion_id,
            compile_ok=result_dict.get("compile_ok"),
            test_ok=result_dict.get("test_ok"),
            clippy_ok=result_dict.get("clippy_ok"),
            compile_time_ms=result_dict.get("compile_time_ms"),
            binary_size_bytes=result_dict.get("binary_size_bytes"),
            error_type=result_dict.get("error_type"),
            stderr=result_dict.get("stderr", ""),
            passed=result_dict.get("passed", False),
            main_free=result_dict.get("main_free", check_main_free(completion)),
            result=result_dict.get("result", ""),
        )
    finally:
        manager.shutdown()

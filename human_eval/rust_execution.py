"""
Rust-specific execution module for HumanEval evaluation.

Handles compilation and test execution of Rust code completions with sandboxing support.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 3.0.0
"""

import multiprocessing
import os
import re
import shutil
import subprocess
import time
import unicodedata

# Use relative import to avoid circular dependency with execution.py
from .execution import create_tempdir, reliability_guard

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
    # Note: std::time::Instant is allowed for benchmarking
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
    # Note: #[derive( is checked separately to allow safe derives
    # Additional dangerous patterns
    "std::intrinsics",
    "core::intrinsics",
]

# Safe derive macros that are allowed
SAFE_DERIVE_MACROS = {
    "Debug", "Clone", "Copy", "PartialEq", "Eq", "PartialOrd", "Ord",
    "Hash", "Default", "Display"
}


def _strip_comments_and_strings(code: str) -> str:
    """Strip comments and string literals from Rust code for security checking.
    
    This prevents false positives from doc comments and string literals
    that contain keywords.
    
    Args:
        code: Rust source code
    
    Returns:
        Code with comments and strings replaced with whitespace
    """
    import re
    
    # Strip line comments (// ...)
    code = re.sub(r"//[^\n]*", "", code)
    
    # Strip block comments (/* ... */)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    
    # Strip string literals (both "..." and r"..." raw strings)
    # This is simplified - handles most common cases
    code = re.sub(r'r#*"(?:[^"\\]|\\.)*"#*', '""', code)
    code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
    
    # Strip char literals
    code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
    
    return code


# Homoglyph mapping for characters that NFKD doesn't normalize to ASCII
# These are visually similar to ASCII letters but aren't decomposed by Unicode normalization
HOMOGLYPH_MAP: dict[str, str] = {
    # Latin small capitals (Phonetic Extensions block)
    "\u1d00": "a",  # ᴀ LATIN LETTER SMALL CAPITAL A
    "\u0299": "b",  # ʙ LATIN LETTER SMALL CAPITAL B
    "\u1d04": "c",  # ᴄ LATIN LETTER SMALL CAPITAL C
    "\u1d05": "d",  # ᴅ LATIN LETTER SMALL CAPITAL D
    "\u1d07": "e",  # ᴇ LATIN LETTER SMALL CAPITAL E
    "\ua730": "f",  # ꜰ LATIN LETTER SMALL CAPITAL F
    "\u0262": "g",  # ɢ LATIN LETTER SMALL CAPITAL G
    "\u029c": "h",  # ʜ LATIN LETTER SMALL CAPITAL H
    "\u026a": "i",  # ɪ LATIN LETTER SMALL CAPITAL I
    "\u1d0a": "j",  # ᴊ LATIN LETTER SMALL CAPITAL J
    "\u1d0b": "k",  # ᴋ LATIN LETTER SMALL CAPITAL K
    "\u029f": "l",  # ʟ LATIN LETTER SMALL CAPITAL L
    "\u1d0d": "m",  # ᴍ LATIN LETTER SMALL CAPITAL M
    "\u0274": "n",  # ɴ LATIN LETTER SMALL CAPITAL N
    "\u1d0f": "o",  # ᴏ LATIN LETTER SMALL CAPITAL O
    "\u1d18": "p",  # ᴘ LATIN LETTER SMALL CAPITAL P
    # No small capital Q in standard Unicode
    "\u0280": "r",  # ʀ LATIN LETTER SMALL CAPITAL R
    "\ua731": "s",  # ꜱ LATIN LETTER SMALL CAPITAL S
    "\u1d1b": "t",  # ᴛ LATIN LETTER SMALL CAPITAL T
    "\u1d1c": "u",  # ᴜ LATIN LETTER SMALL CAPITAL U
    "\u1d20": "v",  # ᴠ LATIN LETTER SMALL CAPITAL V
    "\u1d21": "w",  # ᴡ LATIN LETTER SMALL CAPITAL W
    # No small capital X in standard Unicode
    "\u028f": "y",  # ʏ LATIN LETTER SMALL CAPITAL Y
    "\u1d22": "z",  # ᴢ LATIN LETTER SMALL CAPITAL Z
    # Other common homoglyphs
    "\u0430": "a",  # а CYRILLIC SMALL LETTER A
    "\u0435": "e",  # е CYRILLIC SMALL LETTER IE
    "\u043e": "o",  # о CYRILLIC SMALL LETTER O
    "\u0440": "p",  # р CYRILLIC SMALL LETTER ER
    "\u0441": "c",  # с CYRILLIC SMALL LETTER ES
    "\u0445": "x",  # х CYRILLIC SMALL LETTER HA
    "\u0443": "y",  # у CYRILLIC SMALL LETTER U
    "\u0410": "A",  # А CYRILLIC CAPITAL LETTER A
    "\u0412": "B",  # В CYRILLIC CAPITAL LETTER VE
    "\u0415": "E",  # Е CYRILLIC CAPITAL LETTER IE
    "\u041a": "K",  # К CYRILLIC CAPITAL LETTER KA
    "\u041c": "M",  # М CYRILLIC CAPITAL LETTER EM
    "\u041d": "H",  # Н CYRILLIC CAPITAL LETTER EN
    "\u041e": "O",  # О CYRILLIC CAPITAL LETTER O
    "\u0420": "P",  # Р CYRILLIC CAPITAL LETTER ER
    "\u0421": "C",  # С CYRILLIC CAPITAL LETTER ES
    "\u0422": "T",  # Т CYRILLIC CAPITAL LETTER TE
    "\u0425": "X",  # Х CYRILLIC CAPITAL LETTER HA
    "\u0427": "Y",  # Ч looks like Y in some fonts
}


def _normalize_unicode(text: str) -> str:
    """Normalize Unicode to ASCII to prevent homoglyph attacks.
    
    Uses both NFKD normalization and explicit homoglyph mapping for characters
    that don't decompose to ASCII equivalents.
    """
    # First apply explicit homoglyph mapping
    mapped = "".join(HOMOGLYPH_MAP.get(c, c) for c in text)
    # Then apply NFKD and strip remaining non-ASCII
    return unicodedata.normalize("NFKD", mapped).encode("ascii", "ignore").decode("ascii")


def _sanitize_rust_completion(completion: str) -> str | None:
    """Check for disallowed patterns with Unicode normalization.
    
    Strips comments and string literals before checking to avoid false positives
    from documentation and example code.
    """
    # First normalize Unicode to prevent homoglyph attacks
    normalized = _normalize_unicode(completion.lower())
    
    # Strip comments and strings from the normalized version for pattern checking
    # This prevents false positives from doc comments like "/// Example using std::fs"
    stripped = _strip_comments_and_strings(normalized)
    
    # Check for disallowed patterns in the stripped code
    for pattern in DISALLOWED_COMPLETION_PATTERNS:
        if pattern.lower() in stripped:
            return f"disallowed usage of {pattern}"
    
    # Special check for #[derive( - only block if it contains unsafe traits
    # Allow safe derives like #[derive(Debug, Clone)]
    derive_pattern = r"#\[derive\s*\(([^)]+)\)"
    for match in re.finditer(derive_pattern, stripped, re.IGNORECASE):
        derives = match.group(1)
        # Parse the comma-separated list of derives
        derive_list = [d.strip() for d in derives.split(',')]
        # Check if any derive is not in the safe list
        for derive in derive_list:
            # Remove any paths (e.g., serde::Deserialize -> Deserialize)
            derive_name = derive.split('::')[-1].strip()
            if derive_name and derive_name not in SAFE_DERIVE_MACROS:
                # Check if it looks dangerous (contains keywords like unsafe, arbitrary)
                dangerous_keywords = ['unsafe', 'arbitrary', 'deserialize', 'serialize']
                if any(kw in derive_name.lower() for kw in dangerous_keywords):
                    return f"disallowed derive macro: {derive_name}"
    
    # Check for dangerous patterns in raw strings (still check original, not stripped)
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


def _strip_markdown_code_blocks(completion: str) -> str:
    """Remove markdown code blocks from completion."""
    if "```rust" in completion:
        rust_match = re.search(r"```rust\s*(.*?)\s*```", completion, re.DOTALL)
        if rust_match:
            return rust_match.group(1)
    elif "```" in completion:
        code_match = re.search(r"```[^\n]*\s*(.*?)\s*```", completion, re.DOTALL)
        if code_match:
            return code_match.group(1)
    return completion


def _strip_leading_attributes(completion: str) -> str:
    """Remove leading attribute lines (starting with #[) from completion."""
    stripped_lines = []
    for line in completion.split('\n'):
        stripped_line = line.strip()
        if stripped_line.startswith('#[') and not stripped_line.startswith('#!['):
            continue
        stripped_lines.append(line)
    return '\n'.join(stripped_lines)


def _find_matching_brace(text: str, start_pos: int) -> int | None:
    """Find the position after the matching closing brace starting from start_pos.
    
    Returns the position after the closing brace, or None if not found.
    """
    brace_count = 0
    for i in range(start_pos, len(text)):
        if text[i] == "{":
            brace_count += 1
        elif text[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                return i + 1
    return None


def _extract_target_function_body(text: str, entry_point: str) -> str | None:
    """Try to extract the body of a specific function by name.
    
    Returns the function body if found, None otherwise.
    """
    escaped_entry = re.escape(entry_point)
    
    # Try with DOTALL to handle multiline signatures
    fn_pattern = (
        rf"fn\s+{escaped_entry}\s*<[^>]*>?\s*\([^)]*\)\s*"
        rf"(?:->\s*[^{{}}where]+)?\s*(?:where\s+[^{{}}]+)?\s*\{{"
    )
    fn_match = re.search(fn_pattern, text, re.MULTILINE | re.DOTALL)
    
    if not fn_match:
        # Fallback to simpler pattern without where clause handling
        not_brace_pattern = r"[^{]"
        fn_pattern = rf"fn\s+{escaped_entry}\s*\([^)]*\)\s*(?:->{not_brace_pattern}*)?\s*\{{"
        fn_match = re.search(fn_pattern, text, re.MULTILINE | re.DOTALL)

    if fn_match:
        start_pos = fn_match.end() - 1  # Position of opening brace
        end_pos = _find_matching_brace(text, start_pos)
        if end_pos is not None:
            return text[start_pos + 1 : end_pos - 1].strip()
    
    return None


def _extract_body_from_braces(text: str) -> str | None:
    """Extract content from text that starts with a brace block.
    
    Returns the content between braces if found, None otherwise.
    """
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    
    brace_count = 0
    start_pos = 0
    
    for i, char in enumerate(stripped):
        if char == "{":
            if brace_count == 0:
                start_pos = i + 1
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0:
                return stripped[start_pos:i].strip()

    # If we didn't find a matching brace, return everything after the first {
    if brace_count > 0:
        return stripped[start_pos:].strip()
    
    return None


def _remove_main_functions(text: str) -> str:
    """Remove standalone main() functions from code."""
    lines = text.split("\n")
    cleaned_lines = []
    in_main = False
    brace_count = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if re.match(r"^fn\s+main\s*\([^)]*\)\s*(?:->[^{]*)?\s*\{", stripped):
            in_main = True
            brace_count = 1
            i += 1
            while i < len(lines) and brace_count > 0:
                line = lines[i]
                brace_count += line.count("{") - line.count("}")
                i += 1
            continue

        if in_main:
            brace_count += line.count("{") - line.count("}")
            if brace_count <= 0:
                in_main = False
            i += 1
            continue

        cleaned_lines.append(line)
        i += 1

    return "\n".join(cleaned_lines).strip()


def _clean_extra_patterns(text: str) -> str:
    """Remove common extra patterns like example usage blocks."""
    result = re.sub(
        r"(?i)(//\s*)?(example\s+usage|usage\s+example):.*", "", text, flags=re.DOTALL
    )
    result = re.sub(
        r"^use\s+std::collections::Vec;?\s*$", "", result, flags=re.MULTILINE
    )
    return result.strip()


def _extract_function_body(completion: str, entry_point: str) -> str:
    """
    Extract the function body from a completion, removing extra code like main() functions.

    Args:
        completion: Raw completion text from the model
        entry_point: Name of the function we're looking for (e.g., "has_close_elements")

    Returns:
        Cleaned completion with only the target function body
    """
    # Step 1: Remove markdown code blocks
    completion = _strip_markdown_code_blocks(completion).strip()

    # Step 2: Strip leading attributes
    current_completion = _strip_leading_attributes(completion)
    
    # Step 3: Try to find the target function
    body = _extract_target_function_body(current_completion, entry_point)
    if body is not None:
        return body

    # Step 4: Check if completion is just a brace-enclosed body
    body = _extract_body_from_braces(current_completion)
    if body is not None:
        return body

    # Step 5: Remove main() functions and clean up
    result = _remove_main_functions(current_completion)
    result = _clean_extra_patterns(result)

    return result


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
    """Check if completion contains fn main outside of comments and strings."""
    import re

    # Strip line comments (// ...)
    code = re.sub(r"//[^\n]*", "", completion)
    # Strip block comments (/* ... */)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    # Strip string literals (both "..." and r"..." raw strings)
    # This is a simplified approach - handles most common cases
    code = re.sub(r'r?"(?:[^"\\]|\\.)*"', '""', code)
    # Strip char literals
    code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)

    # Check for fn main() patterns in the cleaned code
    main_pattern = r"fn\s+main\s*\("
    return not bool(re.search(main_pattern, code, re.IGNORECASE))


def _run_clippy_check(source_path: str, timeout: float) -> tuple[bool, str]:
    """Run clippy on compiled code and return (passed, warnings).
    
    Creates a minimal Cargo.toml if one doesn't exist to enable clippy checking
    in temporary directories.
    """
    source_dir = os.path.dirname(source_path)
    cargo_toml_path = os.path.join(source_dir, "Cargo.toml")
    
    # Check if Cargo.toml exists, create minimal one if not
    created_cargo_toml = False
    if not os.path.exists(cargo_toml_path):
        # Create minimal Cargo.toml for clippy checking
        source_filename = os.path.basename(source_path)
        binary_name = os.path.splitext(source_filename)[0]
        
        minimal_cargo_toml = f'''[package]
name = "temp_eval"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "{binary_name}"
path = "{source_filename}"
'''
        try:
            with open(cargo_toml_path, "w", encoding="utf-8") as f:
                f.write(minimal_cargo_toml)
            created_cargo_toml = True
        except OSError as e:
            return False, f"infra: failed to create Cargo.toml: {e}"
    
    try:
        result = subprocess.run(
            ["cargo", "clippy", "--", "-D", "warnings"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=source_dir,
        )
        return result.returncode == 0, result.stderr
    finally:
        # Clean up created Cargo.toml
        if created_cargo_toml and os.path.exists(cargo_toml_path):
            try:
                os.remove(cargo_toml_path)
            except OSError:
                pass  # Best effort cleanup


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
                sys.modules[mod_name] = original  # type: ignore[assignment]


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


def _compile_rust_code(
    source_path: str,
    test_binary: str,
    compile_args: list[str],
    compile_timeout: float,
    use_sandbox: bool,
    sandbox_mode: str | None,
) -> tuple[subprocess.CompletedProcess, float]:
    """Compile Rust code with or without sandbox.
    
    Returns:
        Tuple of (compile_result, compile_time_seconds)
    """
    start_time = time.perf_counter()
    
    if use_sandbox:
        compile_result = run_rustc_sandboxed(
            source_path,
            test_binary,
            compile_args,
            timeout=compile_timeout,
            capture_output=True,
            sandbox_mode=sandbox_mode,
        )
    else:
        compile_result = subprocess.run(
            ["rustc"] + compile_args + [source_path, "-o", test_binary],
            capture_output=True,
            text=True,
            timeout=compile_timeout,
        )
    
    compile_time = time.perf_counter() - start_time
    return compile_result, compile_time


def _run_clippy_phase(
    source_path: str,
    clippy_timeout: float,
    clippy_required: bool,
    result_dict: dict,
) -> bool:
    """Run clippy check and update result_dict.
    
    Returns:
        True if should continue execution, False if should return early
    """
    if not shutil.which("cargo"):
        if clippy_required:
            result_dict["clippy_ok"] = False
            result_dict["error_type"] = "infra_missing_linter"
            result_dict["stderr"] = "cargo not found (required for clippy)"
            result_dict["result"] = "failed: cargo not available"
            return False
        return True
    
    try:
        clippy_ok, clippy_stderr = _run_clippy_check(source_path, clippy_timeout)
        result_dict["clippy_ok"] = clippy_ok
        
        # Check if clippy stderr indicates infrastructure problem
        is_infra_error = clippy_stderr and "infra:" in clippy_stderr
        
        if not clippy_ok and clippy_required:
            if is_infra_error:
                result_dict["error_type"] = "infra_missing_linter"
                result_dict["stderr"] = clippy_stderr
                result_dict["result"] = f"failed: {clippy_stderr}"
            else:
                result_dict["error_type"] = "lint_failure"
                result_dict["stderr"] = clippy_stderr
                result_dict["result"] = "failed: clippy check failed"
            return False
        elif not clippy_ok and not is_infra_error:
            # Advisory mode: record but don't fail
            result_dict["stderr"] = clippy_stderr
            
    except subprocess.TimeoutExpired:
        result_dict["clippy_ok"] = False
        if clippy_required:
            result_dict["error_type"] = "clippy_timeout"
            result_dict["stderr"] = "clippy check timed out"
            result_dict["result"] = "failed: clippy timeout"
            return False
        else:
            result_dict["stderr"] = "clippy check timed out (advisory)"
            
    except Exception as exc:  # noqa: BLE001
        result_dict["clippy_ok"] = False
        if clippy_required:
            result_dict["error_type"] = "infra_missing_linter"
            result_dict["stderr"] = str(exc)
            result_dict["result"] = f"failed: clippy error: {exc}"
            return False
        else:
            result_dict["stderr"] = str(exc)
    
    return True


def _run_test_binary(
    test_binary: str,
    run_timeout: float,
    use_sandbox: bool,
    sandbox_mode: str | None,
) -> subprocess.CompletedProcess:
    """Execute the test binary with or without sandbox."""
    if use_sandbox:
        return run_binary_sandboxed(
            test_binary,
            timeout=run_timeout,
            capture_output=True,
            sandbox_mode=sandbox_mode,
        )
    else:
        return subprocess.run(
            [test_binary],
            capture_output=True,
            text=True,
            timeout=run_timeout,
        )


def _rust_unsafe_execute(
    problem: dict,
    completion: str,
    timeout: float,
    result,
    sandbox_mode: str | None = None,
    enforce_policy: bool = True,
    compile_timeout: float | None = None,
    run_timeout: float | None = None,
    clippy_timeout: float | None = None,
    clippy_required: bool = False,
):
    """
    Execute Rust code and return enhanced result schema.
    
    Args:
        problem: Problem dictionary with prompt, test, etc.
        completion: Generated code completion
        timeout: Default timeout in seconds (used if specific timeouts not provided)
        result: List to append result dict to
        sandbox_mode: Optional sandbox mode ("firejail", "none", or None for auto-detect)
        enforce_policy: Whether to enforce pattern-based policy filtering
        compile_timeout: Timeout for compilation phase (defaults to timeout)
        run_timeout: Timeout for test execution phase (defaults to timeout)
        clippy_timeout: Timeout for clippy check (defaults to compile_timeout)
        clippy_required: Whether clippy passing is required for completion to pass (default: False)
    
    Result dict structure:
    {
        "compile_ok": bool | None,
        "test_ok": bool | None,
        "error_type": str | None,
            # One of: "infra_missing_toolchain", "compile_error", "runtime_error",
            # "assertion_failure", "compile_timeout", "test_timeout",
            # "clippy_timeout", "lint_failure", "infra_missing_linter"
        "stderr": str,
        "passed": bool,
        "main_free": bool,
        "result": str,  # Legacy field for compatibility
    }

    Note: Unlike Python execution, Rust code runs in a separate subprocess after
    compilation. ReliabilityContext/reliability_guard is NOT used here because:
    1. Rust code doesn't have access to Python's os/subprocess modules
    2. We need those modules to compile and execute the Rust binary
    3. Sandbox isolation is handled via firejail or other sandbox modes
    
    Timeout behavior:
    - Each phase (compile, clippy, test) has its own dedicated timeout budget
    - If phase-specific timeouts are not provided, they default to the main timeout
    - A process watchdog monitors total execution time with 2 second grace period
    """
    # Set default timeouts
    if compile_timeout is None:
        compile_timeout = timeout
    if run_timeout is None:
        run_timeout = timeout
    if clippy_timeout is None:
        clippy_timeout = compile_timeout
    
    with create_tempdir() as temp_dir:
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

        try:
            # Compile phase
            try:
                compile_result, compile_time = _compile_rust_code(
                    source_path, test_binary, compile_args,
                    compile_timeout, use_sandbox, effective_mode
                )
            except SandboxError as e:
                result_dict["error_type"] = "infra_missing_toolchain"
                result_dict["stderr"] = str(e)
                result_dict["result"] = f"failed: sandbox error: {e}"
                result.append(result_dict)
                return

            result_dict["compile_time_ms"] = int(compile_time * 1000)
            result_dict["compile_ok"] = compile_result.returncode == 0
            
            if compile_result.returncode != 0:
                failure = compile_result.stderr.strip() or compile_result.stdout.strip()
                result_dict["error_type"] = "compile_error"
                result_dict["stderr"] = failure or "compile error"
                result_dict["result"] = f"failed: {result_dict['stderr']}"
                result.append(result_dict)
                return

            if os.path.exists(test_binary):
                result_dict["binary_size_bytes"] = os.path.getsize(test_binary)

            # Clippy phase
            if not _run_clippy_phase(source_path, clippy_timeout, clippy_required, result_dict):
                result.append(result_dict)
                return

            # Test execution phase
            try:
                test_result = _run_test_binary(
                    test_binary, run_timeout, use_sandbox, effective_mode
                )
            except SandboxError as e:
                result_dict["error_type"] = "runtime_error"
                result_dict["stderr"] = str(e)
                result_dict["result"] = f"failed: sandbox error: {e}"
                result.append(result_dict)
                return

            result_dict["test_ok"] = test_result.returncode == 0
            if test_result.returncode == 0:
                result_dict["passed"] = True
                result_dict["result"] = "passed"
            else:
                failure = test_result.stderr.strip() or test_result.stdout.strip()
                result_dict["error_type"] = "assertion_failure"
                result_dict["stderr"] = failure or "tests failed"
                result_dict["result"] = f"failed: {result_dict['stderr']}"

        except subprocess.TimeoutExpired as e:
            # Determine which phase timed out based on the command
            if "rustc" in str(e.cmd):
                result_dict["error_type"] = "compile_timeout"
                result_dict["stderr"] = f"compilation timed out after {compile_timeout}s"
                result_dict["result"] = "failed: compile timeout"
            else:
                result_dict["error_type"] = "test_timeout"
                result_dict["stderr"] = f"test execution timed out after {run_timeout}s"
                result_dict["result"] = "failed: test timeout"
        except BaseException as exc:  # noqa: BLE001
            result_dict["error_type"] = "runtime_error"
            result_dict["stderr"] = str(exc)
            result_dict["result"] = f"failed: {exc}"

        # Always append result (was previously only in BaseException handler - bug!)
        result.append(result_dict)


def rust_check_correctness(
    problem: dict,
    completion: str,
    timeout: float,
    completion_id: int | None = None,
    sandbox_mode: str | None = None,
    enforce_policy: bool = True,
    compile_timeout: float | None = None,
    run_timeout: float | None = None,
    clippy_timeout: float | None = None,
    clippy_required: bool = False,
) -> dict:
    """
    Evaluate a Rust completion by compiling and running its tests.

    Args:
        problem: Problem dictionary with prompt, test, etc.
        completion: Generated code completion
        timeout: Default timeout in seconds (used if phase timeouts not specified)
        completion_id: Optional completion ID for tracking
        sandbox_mode: Optional sandbox mode ("firejail", "none", or None for auto-detect)
        enforce_policy: Whether to enforce pattern-based policy filtering (default: True).
            Set to False for pure HumanEval compatibility without security filtering.
        compile_timeout: Timeout for compilation phase (defaults to timeout)
        run_timeout: Timeout for test execution phase (defaults to timeout) 
        clippy_timeout: Timeout for clippy check (defaults to compile_timeout)
        clippy_required: Whether clippy passing is required for completion to pass (default: False).
            In advisory mode (False), clippy failures are recorded but don't fail the completion.
            In required mode (True), clippy failures cause the completion to fail with
            error_type="lint_failure".

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

        # Set default timeouts for process watchdog calculation
        effective_compile_timeout = compile_timeout if compile_timeout is not None else timeout
        effective_run_timeout = run_timeout if run_timeout is not None else timeout
        effective_clippy_timeout = (
            clippy_timeout if clippy_timeout is not None else effective_compile_timeout
        )
        
        # Process watchdog: total budget + grace period
        watchdog_timeout = (
            effective_compile_timeout + effective_run_timeout + effective_clippy_timeout + 2
        )

        process = multiprocessing.Process(
            target=_rust_unsafe_execute,
            args=(problem, completion, timeout, result, sandbox_mode, enforce_policy, 
                  compile_timeout, run_timeout, clippy_timeout, clippy_required),
        )
        process.start()
        process.join(timeout=watchdog_timeout)
        if process.is_alive():
            process.kill()
            process.join()

        if not result:
            result_dict = {
                "compile_ok": None,
                "test_ok": None,
                "error_type": "runtime_error",
                "stderr": "process watchdog timeout",
                "passed": False,
                "main_free": check_main_free(completion),
                "result": "timed out: process watchdog",
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

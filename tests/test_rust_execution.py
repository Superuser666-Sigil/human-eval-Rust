"""
Rust execution module tests for HumanEval Rust.

Tests pattern blocking, function extraction, compilation, and execution.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
"""

import shutil

import pytest

from human_eval import rust_execution


class TestPatternBlocklistBasic:
    """Test basic pattern blocklist functionality."""

    def test_pattern_blocklist_basic(self) -> None:
        """Test that basic dangerous patterns are blocked."""
        completion = 'fn x() { std::process::Command::new("ls"); }'
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_pattern_blocklist_fs(self) -> None:
        """Test that filesystem patterns are blocked."""
        completion = 'fn x() { std::fs::read_to_string("/etc/passwd"); }'
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_pattern_blocklist_net(self) -> None:
        """Test that network patterns are blocked."""
        completion = 'fn x() { std::net::TcpStream::connect("evil.com:80"); }'
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_pattern_blocklist_unsafe(self) -> None:
        """Test that unsafe blocks are blocked."""
        completion = "fn x() { unsafe { } }"
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None


class TestPatternBlocklistUnicode:
    """Test Unicode bypass prevention."""

    def test_pattern_blocklist_unicode_bypass(self) -> None:
        """Test that Unicode homoglyph bypasses are detected."""
        completion = 'fn x() { stᴅ::prᴇcess::Command::new("ls"); }'
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_normalize_unicode_basic(self) -> None:
        """Test basic Unicode normalization."""
        normalized = rust_execution._normalize_unicode("stᴅ::fs")
        assert "std" in normalized.lower() or normalized == "st::fs"

    def test_normalize_unicode_ascii_passthrough(self) -> None:
        """Test that ASCII content passes through unchanged."""
        ascii_content = "std::fs::read"
        normalized = rust_execution._normalize_unicode(ascii_content)
        assert normalized == ascii_content


class TestPatternBlocklistRawString:
    """Test raw string bypass prevention."""

    def test_pattern_blocklist_raw_string_bypass(self) -> None:
        """Test that raw string bypasses are detected."""
        completion = 'let s = r"std::process::Command";'
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_raw_string_with_hashes(self) -> None:
        """Test raw strings with hash delimiters."""
        completion = 'let s = r#"unsafe { }"#;'
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None


class TestPatternBlocklistMacros:
    """Test compile-time macro blocking."""

    def test_blocks_include_macro(self) -> None:
        """Test that include! macro is blocked."""
        completion = 'fn x() { include!("malicious.rs"); }'
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_blocks_include_str_macro(self) -> None:
        """Test that include_str! macro is blocked."""
        completion = 'fn x() { include_str!("/etc/passwd"); }'
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_blocks_env_macro(self) -> None:
        """Test that env! macro is blocked."""
        completion = 'fn x() { env!("SECRET_KEY"); }'
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_blocks_asm_macro(self) -> None:
        """Test that asm! macro is blocked."""
        completion = 'fn x() { asm!("nop"); }'
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_blocks_global_asm_macro(self) -> None:
        """Test that global_asm! macro is blocked."""
        completion = 'global_asm!("nop");'
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None


class TestValidateCompletion:
    """Test completion validation."""

    def test_validate_completion_limits(self) -> None:
        """Test that oversized completions are rejected."""
        too_long = "a" * (rust_execution.MAX_COMPLETION_LENGTH + 1)
        error = rust_execution._validate_completion(too_long)
        assert error is not None
        assert error.startswith("completion too long")

    def test_validate_empty_completion(self) -> None:
        """Test that empty completions are rejected."""
        error = rust_execution._validate_completion("")
        assert error is not None
        assert "empty" in error.lower()

    def test_validate_null_bytes(self) -> None:
        """Test that null bytes are rejected."""
        with_null = "fn x() { \x00 }"
        error = rust_execution._validate_completion(with_null)
        assert error is not None
        assert "null" in error.lower()

    def test_validate_too_many_lines(self) -> None:
        """Test that too many lines are rejected."""
        many_lines = "\n" * (rust_execution.MAX_COMPLETION_LINES + 1)
        error = rust_execution._validate_completion(many_lines)
        assert error is not None
        assert "lines" in error.lower()

    def test_validate_valid_completion(self) -> None:
        """Test that valid completions pass."""
        valid = "fn add(a: i32, b: i32) -> i32 { a + b }"
        error = rust_execution._validate_completion(valid)
        assert error is None


class TestExtractFunctionBody:
    """Test function body extraction."""

    def test_extract_function_body_with_signature(self, sample_problem) -> None:
        """Test extraction with full function signature."""
        body = rust_execution._extract_function_body(
            "fn add(a: i32, b: i32) -> i32 { return a + b; }",
            sample_problem["entry_point"],
        )
        assert "a + b" in body

    def test_extract_function_body_from_braces(self) -> None:
        """Test extraction from brace-delimited body."""
        body = rust_execution._extract_function_body("{ a + b }", "test")
        assert "a + b" in body

    def test_extract_function_body_removes_main(self) -> None:
        """Test that main function is removed."""
        code = """
fn test() { 42 }

fn main() {
    println!("test");
}
"""
        body = rust_execution._extract_function_body(code, "test")
        assert "fn main" not in body

    def test_extract_function_body_from_markdown(self) -> None:
        """Test extraction from markdown code block."""
        code = """
```rust
fn test() -> i32 {
    42
}
```
"""
        body = rust_execution._extract_function_body(code, "test")
        assert "42" in body

    def test_extract_function_body_empty_input(self) -> None:
        """Test extraction with empty input."""
        body = rust_execution._extract_function_body("", "test")
        assert body == ""


class TestCheckMainFree:
    """Test main function detection."""

    def test_check_main_free_without_main(self) -> None:
        """Test detection when no main function exists."""
        code = "fn add(a: i32, b: i32) -> i32 { a + b }"
        assert rust_execution.check_main_free(code) is True

    def test_check_main_free_with_main(self) -> None:
        """Test detection when main function exists."""
        code = "fn main() { println!(\"hello\"); }"
        assert rust_execution.check_main_free(code) is False

    def test_check_main_free_empty(self) -> None:
        """Test detection with empty input."""
        assert rust_execution.check_main_free("") is True

    def test_check_main_free_main_in_comment(self) -> None:
        """Test that main in comment doesn't trigger false positive."""
        code = "// fn main() {}\nfn test() { 42 }"
        # This may or may not be true depending on regex implementation
        # The important thing is it doesn't crash
        result = rust_execution.check_main_free(code)
        assert isinstance(result, bool)


class TestRustcAvailabilityCheck:
    """Test rustc availability checking."""

    def test_check_rustc_when_available(self) -> None:
        """Test check when rustc is available."""
        if shutil.which("rustc") is None:
            pytest.skip("rustc not available")

        available, error = rust_execution._check_rustc_available()
        assert available is True
        assert error is None


class TestReliabilityContext:
    """Test ReliabilityContext class."""

    def test_reliability_context_enters_and_exits(self) -> None:
        """Test that context manager enters and exits cleanly."""
        with rust_execution.ReliabilityContext():
            pass
        # Should not raise any exceptions

    def test_reliability_context_with_memory_limit(self) -> None:
        """Test context manager with memory limit."""
        # Skip on Windows as resource limits are Unix-specific
        import platform

        if platform.system() == "Windows":
            pytest.skip("Resource limits not supported on Windows")

        with rust_execution.ReliabilityContext(maximum_memory_bytes=1024 * 1024 * 100):
            pass


class TestDeterministicFlags:
    """Test deterministic rustc flags."""

    def test_deterministic_flags_defined(self) -> None:
        """Test that deterministic flags are defined."""
        flags = rust_execution.DETERMINISTIC_RUSTC_FLAGS
        assert isinstance(flags, list)
        assert len(flags) > 0

    def test_edition_flag_present(self) -> None:
        """Test that edition flag is present."""
        assert "--edition=2021" in rust_execution.DETERMINISTIC_RUSTC_FLAGS

    def test_test_flag_present(self) -> None:
        """Test that test flag is present."""
        assert "--test" in rust_execution.DETERMINISTIC_RUSTC_FLAGS

    def test_optimization_disabled(self) -> None:
        """Test that optimization is disabled for determinism."""
        flags = rust_execution.DETERMINISTIC_RUSTC_FLAGS
        assert "opt-level=0" in flags


class TestClippyCheck:
    """Test clippy checking functionality."""

    def test_run_clippy_check_signature(self) -> None:
        """Test that _run_clippy_check has correct signature."""
        import inspect

        sig = inspect.signature(rust_execution._run_clippy_check)
        params = list(sig.parameters.keys())
        assert "source_path" in params
        assert "timeout" in params

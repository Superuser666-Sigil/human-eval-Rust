"""
Security-focused test cases for HumanEval Rust.

Tests input validation, pattern blocking, sandbox escape prevention,
and other security-sensitive functionality.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
"""

import pytest

from human_eval import rust_execution
from human_eval.sandbox import FIREJAIL_SECURITY_OPTS


class TestPatternBlocklist:
    """Test pattern blocklist functionality."""

    @pytest.mark.parametrize(
        "dangerous_pattern",
        [
            "std::fs::read_to_string",
            "std::fs::write",
            "std::process::Command",
            "std::net::TcpStream",
            "unsafe { }",
            "std::ptr::null_mut",
            "std::mem::transmute",
            "std::env::var",
            "include!",
            "asm!",
            "global_asm!",
            "#[link",
            "proc_macro",
            "std::intrinsics",
            "core::intrinsics",
        ],
    )
    def test_blocks_dangerous_patterns(self, dangerous_pattern: str) -> None:
        """Test that dangerous patterns are detected and blocked."""
        completion = f'fn x() {{ {dangerous_pattern}("test"); }}'
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None, f"Should block pattern: {dangerous_pattern}"

    @pytest.mark.parametrize(
        "safe_pattern",
        [
            "let x = 42;",
            "println!(\"hello\");",
            "vec![1, 2, 3]",
            "String::from(\"test\")",
            "Option::Some(42)",
            "Result::Ok(42)",
            ".iter().map(|x| x * 2)",
            "HashMap::new()",
        ],
    )
    def test_allows_safe_patterns(self, safe_pattern: str) -> None:
        """Test that safe patterns are allowed."""
        completion = f"fn x() {{ {safe_pattern} }}"
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is None, f"Should allow safe pattern: {safe_pattern}"


class TestUnicodeBypassPrevention:
    """Test prevention of Unicode homoglyph attacks."""

    @pytest.mark.parametrize(
        "unicode_bypass,description",
        [
            ("stᴅ::fs", "Latin small letter D"),
            ("std::ꜰs", "Latin letter small capital F"),
            ("std::fꜱ", "Latin small letter S with hook"),
            ("unsaꜰe", "unsafe with homoglyph"),
            ("stᴅ::ᴘrocess", "process with homoglyphs"),
        ],
    )
    def test_blocks_unicode_homoglyph_bypass(
        self, unicode_bypass: str, description: str
    ) -> None:
        """Test that Unicode homoglyph bypasses are detected."""
        completion = f'fn x() {{ {unicode_bypass}::something("test"); }}'
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None, f"Should block Unicode bypass: {description}"


class TestRawStringBypassPrevention:
    """Test prevention of raw string bypass attempts."""

    @pytest.mark.parametrize(
        "raw_string_bypass",
        [
            'r"std::process::Command"',
            'r#"unsafe { }"#',
            'r##"std::fs::read"##',
        ],
    )
    def test_blocks_raw_string_bypass(self, raw_string_bypass: str) -> None:
        """Test that raw string bypasses are detected."""
        completion = f"fn x() {{ let s = {raw_string_bypass}; }}"
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None, f"Should block raw string: {raw_string_bypass}"


class TestInputValidation:
    """Test input validation functions."""

    def test_rejects_empty_completion(self) -> None:
        """Test that empty completions are rejected."""
        error = rust_execution._validate_completion("")
        assert error is not None
        assert "empty" in error.lower()

    def test_rejects_oversized_completion(self) -> None:
        """Test that oversized completions are rejected."""
        huge_completion = "a" * (rust_execution.MAX_COMPLETION_LENGTH + 1)
        error = rust_execution._validate_completion(huge_completion)
        assert error is not None
        assert "too long" in error.lower()

    def test_rejects_too_many_lines(self) -> None:
        """Test that completions with too many lines are rejected."""
        many_lines = "\n" * (rust_execution.MAX_COMPLETION_LINES + 1)
        error = rust_execution._validate_completion(many_lines)
        assert error is not None
        assert "lines" in error.lower()

    def test_rejects_null_bytes(self) -> None:
        """Test that completions with null bytes are rejected."""
        with_null = "fn x() { \x00 }"
        error = rust_execution._validate_completion(with_null)
        assert error is not None
        assert "null" in error.lower()

    def test_accepts_valid_completion(self) -> None:
        """Test that valid completions are accepted."""
        valid = "fn add(a: i32, b: i32) -> i32 { a + b }"
        error = rust_execution._validate_completion(valid)
        assert error is None


class TestFirejailSecurityOptions:
    """Test Firejail security configuration."""

    def test_seccomp_enabled(self) -> None:
        """Test that seccomp is in security options."""
        assert "--seccomp" in FIREJAIL_SECURITY_OPTS

    def test_caps_dropped(self) -> None:
        """Test that capabilities are dropped."""
        assert "--caps.drop=all" in FIREJAIL_SECURITY_OPTS

    def test_noroot(self) -> None:
        """Test that noroot is enabled."""
        assert "--noroot" in FIREJAIL_SECURITY_OPTS

    def test_nogroups(self) -> None:
        """Test that supplementary groups are disabled."""
        assert "--nogroups" in FIREJAIL_SECURITY_OPTS

    def test_private_tmp(self) -> None:
        """Test that private /tmp is enabled."""
        assert "--private-tmp" in FIREJAIL_SECURITY_OPTS

    def test_read_only_root(self) -> None:
        """Test that root filesystem is read-only."""
        assert "--read-only=/" in FIREJAIL_SECURITY_OPTS

    def test_file_size_limit(self) -> None:
        """Test that file size limit is set."""
        assert any("--rlimit-fsize" in opt for opt in FIREJAIL_SECURITY_OPTS)

    def test_process_limit(self) -> None:
        """Test that process limit is set (fork bomb prevention)."""
        assert any("--rlimit-nproc" in opt for opt in FIREJAIL_SECURITY_OPTS)

    def test_cpu_limit(self) -> None:
        """Test that CPU time limit is set."""
        assert any("--rlimit-cpu" in opt for opt in FIREJAIL_SECURITY_OPTS)


class TestMaliciousCompletionBlocking:
    """Test blocking of known malicious completion patterns."""

    def test_blocks_filesystem_read(self, sample_problem) -> None:
        """Test that filesystem read attempts are blocked."""
        malicious = 'std::fs::read_to_string("/etc/passwd")'
        completion = f"fn add(a: i32, b: i32) -> i32 {{ {malicious}; a + b }}"
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_blocks_filesystem_write(self, sample_problem) -> None:
        """Test that filesystem write attempts are blocked."""
        malicious = 'std::fs::write("/tmp/evil", b"data")'
        completion = f"fn add(a: i32, b: i32) -> i32 {{ {malicious}; a + b }}"
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_blocks_command_execution(self, sample_problem) -> None:
        """Test that command execution attempts are blocked."""
        malicious = 'std::process::Command::new("rm").arg("-rf").arg("/").spawn()'
        completion = f"fn add(a: i32, b: i32) -> i32 {{ {malicious}; a + b }}"
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_blocks_network_access(self, sample_problem) -> None:
        """Test that network access attempts are blocked."""
        malicious = 'std::net::TcpStream::connect("evil.com:80")'
        completion = f"fn add(a: i32, b: i32) -> i32 {{ {malicious}; a + b }}"
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_blocks_environment_access(self, sample_problem) -> None:
        """Test that environment variable access is blocked."""
        malicious = 'std::env::var("SECRET_KEY")'
        completion = f"fn add(a: i32, b: i32) -> i32 {{ {malicious}; a + b }}"
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_blocks_memory_manipulation(self, sample_problem) -> None:
        """Test that memory manipulation is blocked."""
        malicious = "std::mem::transmute::<u64, *mut u8>(0)"
        completion = f"fn add(a: i32, b: i32) -> i32 {{ {malicious}; a + b }}"
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_blocks_ffi(self, sample_problem) -> None:
        """Test that FFI declarations are blocked."""
        malicious = 'extern "C" { fn evil(); }'
        completion = f"{malicious} fn add(a: i32, b: i32) -> i32 {{ a + b }}"
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None

    def test_blocks_inline_assembly(self, sample_problem) -> None:
        """Test that inline assembly is blocked."""
        malicious = 'asm!("nop")'
        completion = f"fn add(a: i32, b: i32) -> i32 {{ {malicious}; a + b }}"
        violation = rust_execution._sanitize_rust_completion(completion)
        assert violation is not None


class TestThreadSafety:
    """Test thread safety of security functions."""

    def test_sanitize_is_thread_safe(self) -> None:
        """Test that _sanitize_rust_completion is thread-safe."""
        import threading

        results: list[str | None] = []
        errors: list[Exception] = []

        completions = [
            "fn x() { std::fs::read_to_string(\"/etc/passwd\"); }",
            "fn y() { let z = 42; }",
            "fn z() { std::process::Command::new(\"ls\"); }",
        ]

        def sanitize_completion(completion: str) -> None:
            try:
                result = rust_execution._sanitize_rust_completion(completion)
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=sanitize_completion, args=(c,))
            for c in completions * 10
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 30

    def test_validate_is_thread_safe(self) -> None:
        """Test that _validate_completion is thread-safe."""
        import threading

        results: list[str | None] = []
        errors: list[Exception] = []

        completions = [
            "fn x() { 42 }",
            "",
            "a" * 1000,
            "valid\ncode",
        ]

        def validate_completion(completion: str) -> None:
            try:
                result = rust_execution._validate_completion(completion)
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=validate_completion, args=(c,))
            for c in completions * 10
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 40


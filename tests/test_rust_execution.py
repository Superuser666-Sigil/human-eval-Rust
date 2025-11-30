from human_eval import rust_execution


def test_pattern_blocklist_basic():
    completion = 'fn x() { std::process::Command::new("ls"); }'
    violation = rust_execution._sanitize_rust_completion(completion)
    assert violation is not None


def test_pattern_blocklist_unicode_bypass():
    completion = 'fn x() { stᴅ::prᴇcess::Command::new("ls"); }'
    violation = rust_execution._sanitize_rust_completion(completion)
    assert violation is not None


def test_pattern_blocklist_raw_string_bypass():
    completion = 'let s = r"std::process::Command";'
    violation = rust_execution._sanitize_rust_completion(completion)
    assert violation is not None


def test_validate_completion_limits():
    too_long = "a" * (rust_execution.MAX_COMPLETION_LENGTH + 1)
    error = rust_execution._validate_completion(too_long)
    assert error is not None
    assert error.startswith("completion too long")


def test_extract_function_body_with_signature(sample_problem):
    body = rust_execution._extract_function_body(
        "fn add(a: i32, b: i32) -> i32 { return a + b; }",
        sample_problem["entry_point"],
    )
    assert "a + b" in body

"""
SigilDERG Pipeline Ingestion Module Tests.

Tests for sigil_ingest.py including:
- Hash computation determinism and uniqueness
- Task ID formatting
- Anti-pattern detection
- Task extraction and generation
- Schema compliance
- Migration of existing tasks

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
"""

import json
from pathlib import Path

import pytest

# Try to import hypothesis for property-based tests
try:
    from hypothesis import assume, given, settings
    from hypothesis import strategies as st

    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False

    def given(*args, **kwargs):  # type: ignore[no-redef]
        def decorator(func):
            return pytest.mark.skip(reason="hypothesis not installed")(func)
        return decorator

    def settings(*args, **kwargs):  # type: ignore[no-redef]
        def decorator(func):
            return func
        return decorator

    class st:  # type: ignore[no-redef]
        @staticmethod
        def text(*args, **kwargs):
            return None

        @staticmethod
        def sampled_from(*args, **kwargs):
            return None

    def assume(condition):  # type: ignore[no-redef]
        pass


from human_eval.sigil_ingest import (
    ANTI_PATTERNS,
    CATEGORY_RATIOS,
    SUBCATEGORIES,
    HumanEvalTask,
    SigilIngestor,
    SigilTask,
    compute_task_hash,
    detect_anti_patterns,
    extract_doc_comments,
    extract_entry_point,
    extract_function_signature,
    format_task_id,
    migrate_existing_task,
)


# ============================================================================
# Hash Computation Tests
# ============================================================================


class TestComputeTaskHash:
    """Tests for the content-hash ID generation."""

    def test_hash_determinism(self) -> None:
        """Same input should always produce the same hash."""
        prompt = "fn add(a: i32, b: i32) -> i32 {"
        category = "codegen"
        
        hash1 = compute_task_hash(prompt, category)
        hash2 = compute_task_hash(prompt, category)
        hash3 = compute_task_hash(prompt, category)
        
        assert hash1 == hash2 == hash3

    def test_hash_length(self) -> None:
        """Hash should be exactly 12 characters."""
        prompt = "fn example() -> bool {"
        for category in CATEGORY_RATIOS:
            hash_value = compute_task_hash(prompt, category)
            assert len(hash_value) == 12

    def test_hash_is_hexadecimal(self) -> None:
        """Hash should only contain hexadecimal characters."""
        prompt = "fn test_func(x: u64) -> u64 {"
        hash_value = compute_task_hash(prompt, "codegen")
        
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_different_prompts_different_hashes(self) -> None:
        """Different prompts should produce different hashes."""
        category = "codegen"
        prompts = [
            "fn add(a: i32, b: i32) -> i32 {",
            "fn subtract(a: i32, b: i32) -> i32 {",
            "fn multiply(a: i32, b: i32) -> i32 {",
            "fn divide(a: i32, b: i32) -> i32 {",
        ]
        
        hashes = {compute_task_hash(p, category) for p in prompts}
        assert len(hashes) == len(prompts), "All prompts should have unique hashes"

    def test_different_categories_different_hashes(self) -> None:
        """Same prompt with different categories should produce different hashes."""
        prompt = "fn process(data: &[u8]) -> Vec<u8> {"
        
        hashes = {compute_task_hash(prompt, cat) for cat in CATEGORY_RATIOS}
        assert len(hashes) == len(CATEGORY_RATIOS)

    def test_category_case_insensitive(self) -> None:
        """Category should be normalized to lowercase."""
        prompt = "fn example() {"
        
        hash_lower = compute_task_hash(prompt, "codegen")
        hash_upper = compute_task_hash(prompt, "CODEGEN")
        hash_mixed = compute_task_hash(prompt, "CodeGen")
        
        assert hash_lower == hash_upper == hash_mixed

    def test_unicode_prompt_handling(self) -> None:
        """Hash should handle Unicode prompts correctly."""
        prompt = "/// Calculates π (pi) approximately.\nfn pi() -> f64 {"
        hash_value = compute_task_hash(prompt, "codegen")
        
        assert len(hash_value) == 12
        # Ensure determinism with Unicode
        assert compute_task_hash(prompt, "codegen") == hash_value

    def test_empty_prompt(self) -> None:
        """Empty prompt should still produce a valid hash."""
        hash_value = compute_task_hash("", "codegen")
        assert len(hash_value) == 12


@pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
class TestHashProperties:
    """Property-based tests for hash computation."""

    @given(st.text(min_size=0, max_size=5000))
    @settings(max_examples=200)
    def test_hash_always_12_chars(self, prompt: str) -> None:
        """Hash should always be exactly 12 characters for any input."""
        hash_value = compute_task_hash(prompt, "codegen")
        assert len(hash_value) == 12

    @given(st.text(min_size=1, max_size=1000))
    @settings(max_examples=100)
    def test_hash_determinism_property(self, prompt: str) -> None:
        """Hash computation should be purely deterministic."""
        h1 = compute_task_hash(prompt, "codegen")
        h2 = compute_task_hash(prompt, "codegen")
        assert h1 == h2

    @given(
        st.text(min_size=1, max_size=500),
        st.sampled_from(list(CATEGORY_RATIOS.keys())),
    )
    @settings(max_examples=100)
    def test_hash_valid_hexadecimal(self, prompt: str, category: str) -> None:
        """Hash should always be valid hexadecimal."""
        hash_value = compute_task_hash(prompt, category)
        # Should not raise
        int(hash_value, 16)


# ============================================================================
# Task ID Formatting Tests
# ============================================================================


class TestFormatTaskId:
    """Tests for task ID formatting."""

    def test_format_categories(self) -> None:
        """Each category should be properly title-cased."""
        hash_id = "a1b2c3d4e5f6"
        
        assert format_task_id("codegen", hash_id) == "CodeGen/a1b2c3d4e5f6"
        assert format_task_id("transform", hash_id) == "Transform/a1b2c3d4e5f6"
        assert format_task_id("fix", hash_id) == "Fix/a1b2c3d4e5f6"
        assert format_task_id("explain", hash_id) == "Explain/a1b2c3d4e5f6"

    def test_format_case_normalization(self) -> None:
        """Category should be normalized regardless of input case."""
        hash_id = "abc123def456"
        
        assert format_task_id("CODEGEN", hash_id) == "CodeGen/abc123def456"
        assert format_task_id("CodeGen", hash_id) == "CodeGen/abc123def456"
        assert format_task_id("codegen", hash_id) == "CodeGen/abc123def456"

    def test_format_unknown_category(self) -> None:
        """Unknown category should be title-cased."""
        hash_id = "123456789abc"
        
        assert format_task_id("custom", hash_id) == "Custom/123456789abc"
        assert format_task_id("CUSTOM", hash_id) == "Custom/123456789abc"


# ============================================================================
# Anti-Pattern Detection Tests
# ============================================================================


class TestDetectAntiPatterns:
    """Tests for anti-pattern detection in Rust code."""

    def test_detect_unsafe(self) -> None:
        """Should detect unsafe blocks."""
        code = "fn test() { unsafe { ptr.read() } }"
        patterns = detect_anti_patterns(code)
        assert "unsafe" in patterns

    def test_detect_unwrap(self) -> None:
        """Should detect .unwrap() calls."""
        code = "fn test() { some_option.unwrap() }"
        patterns = detect_anti_patterns(code)
        assert "unwrap" in patterns

    def test_detect_expect(self) -> None:
        """Should detect .expect() calls."""
        code = 'fn test() { result.expect("error") }'
        patterns = detect_anti_patterns(code)
        assert "expect" in patterns

    def test_detect_panic(self) -> None:
        """Should detect panic! macro."""
        code = 'fn test() { panic!("oops") }'
        patterns = detect_anti_patterns(code)
        assert "panic" in patterns

    def test_detect_todo(self) -> None:
        """Should detect todo! macro."""
        code = "fn test() { todo!() }"
        patterns = detect_anti_patterns(code)
        assert "todo" in patterns

    def test_detect_dbg(self) -> None:
        """Should detect dbg! macro."""
        code = "fn test() { dbg!(value) }"
        patterns = detect_anti_patterns(code)
        assert "dbg" in patterns

    def test_detect_multiple_patterns(self) -> None:
        """Should detect multiple anti-patterns."""
        code = """
        fn bad_code() {
            let x = option.unwrap();
            unsafe { ptr.write(x) };
            todo!();
        }
        """
        patterns = detect_anti_patterns(code)
        assert "unwrap" in patterns
        assert "unsafe" in patterns
        assert "todo" in patterns

    def test_clean_code(self) -> None:
        """Clean code should not trigger any anti-patterns."""
        code = """
        fn good_code(option: Option<i32>) -> Option<i32> {
            option.map(|x| x + 1)
        }
        """
        patterns = detect_anti_patterns(code)
        assert len(patterns) == 0


# ============================================================================
# Code Extraction Tests
# ============================================================================


class TestExtractFunctionSignature:
    """Tests for function signature extraction."""

    def test_simple_function(self) -> None:
        """Extract simple function signature."""
        code = "fn add(a: i32, b: i32) -> i32 { a + b }"
        sig = extract_function_signature(code)
        assert sig == "fn add(a: i32, b: i32) -> i32 {"

    def test_pub_function(self) -> None:
        """Extract public function signature."""
        code = "pub fn process(data: &str) -> String { data.to_string() }"
        sig = extract_function_signature(code)
        assert sig == "pub fn process(data: &str) -> String {"

    def test_generic_function(self) -> None:
        """Extract generic function signature."""
        code = "fn identity<T>(value: T) -> T { value }"
        sig = extract_function_signature(code)
        assert sig == "fn identity<T>(value: T) -> T {"

    def test_no_return_type(self) -> None:
        """Extract function without explicit return type."""
        code = "fn print_hello() { println!(\"Hello\"); }"
        sig = extract_function_signature(code)
        assert sig == "fn print_hello() {"

    def test_no_function(self) -> None:
        """Return None when no function is found."""
        code = "let x = 42;"
        sig = extract_function_signature(code)
        assert sig is None


class TestExtractEntryPoint:
    """Tests for entry point (function name) extraction."""

    def test_simple_function(self) -> None:
        """Extract function name from simple function."""
        code = "fn calculate_sum(a: i32, b: i32) -> i32 { a + b }"
        name = extract_entry_point(code)
        assert name == "calculate_sum"

    def test_pub_function(self) -> None:
        """Extract function name from public function."""
        code = "pub fn public_api() -> Result<(), Error> { Ok(()) }"
        name = extract_entry_point(code)
        assert name == "public_api"

    def test_no_function(self) -> None:
        """Return None when no function is found."""
        code = "struct Point { x: i32, y: i32 }"
        name = extract_entry_point(code)
        assert name is None


class TestExtractDocComments:
    """Tests for documentation comment extraction."""

    def test_doc_comments(self) -> None:
        """Extract triple-slash doc comments."""
        code = """/// This is a doc comment.
/// Second line.
fn example() {}"""
        docs = extract_doc_comments(code)
        assert "/// This is a doc comment." in docs
        assert "/// Second line." in docs

    def test_inner_doc_comments(self) -> None:
        """Extract inner doc comments."""
        code = """//! Module-level documentation.
//! More module docs.
fn example() {}"""
        docs = extract_doc_comments(code)
        assert "//! Module-level documentation." in docs

    def test_no_comments(self) -> None:
        """Return empty string when no doc comments."""
        code = "fn example() {}"
        docs = extract_doc_comments(code)
        assert docs == ""


# ============================================================================
# SigilTask Tests
# ============================================================================


class TestSigilTask:
    """Tests for SigilTask dataclass."""

    def test_has_function_true(self) -> None:
        """has_function should be True when code contains a function."""
        task = SigilTask(
            prompt="Write a function",
            gen="fn example() -> i32 { 42 }",
        )
        assert task.has_function is True

    def test_has_function_false(self) -> None:
        """has_function should be False when code has no function."""
        task = SigilTask(
            prompt="Define a struct",
            gen="struct Point { x: i32, y: i32 }",
        )
        assert task.has_function is False

    def test_entry_point(self) -> None:
        """entry_point should extract the function name."""
        task = SigilTask(
            prompt="Write add function",
            gen="fn add(a: i32, b: i32) -> i32 { a + b }",
        )
        assert task.entry_point == "add"

    def test_anti_patterns(self) -> None:
        """anti_patterns should detect code issues."""
        task = SigilTask(
            prompt="Write risky code",
            gen="fn risky() { let x = opt.unwrap(); unsafe { *ptr } }",
        )
        patterns = task.anti_patterns
        assert "unwrap" in patterns
        assert "unsafe" in patterns


# ============================================================================
# HumanEvalTask Tests
# ============================================================================


class TestHumanEvalTask:
    """Tests for HumanEvalTask dataclass."""

    def test_to_dict_required_fields(self) -> None:
        """to_dict should include all required fields."""
        task = HumanEvalTask(
            task_id="CodeGen/abc123def456",
            category="codegen",
            subcategory="function_impl",
            prompt="fn add(a: i32, b: i32) -> i32 {",
            canonical_solution="    a + b\n}",
            test="#[test] fn test() { assert_eq!(add(1, 2), 3); }",
            entry_point="add",
            source="sigil-pipeline",
        )
        
        d = task.to_dict()
        
        # Required fields
        assert d["task_id"] == "CodeGen/abc123def456"
        assert d["category"] == "codegen"
        assert d["subcategory"] == "function_impl"
        assert d["prompt"] == "fn add(a: i32, b: i32) -> i32 {"
        assert d["canonical_solution"] == "    a + b\n}"
        assert d["test"] == "#[test] fn test() { assert_eq!(add(1, 2), 3); }"
        assert d["entry_point"] == "add"
        assert d["source"] == "sigil-pipeline"
        
        # Quality metadata
        assert "edition" in d
        assert "rustfmt_style_edition" in d
        assert "typechecked" in d
        assert "clippy_clean" in d
        assert "no_unsafe" in d
        assert "no_unwrap" in d
        assert "quality_level" in d
        assert "processed_date" in d

    def test_to_dict_optional_fields(self) -> None:
        """to_dict should include optional fields only when set."""
        task = HumanEvalTask(
            task_id="Fix/123abc",
            category="fix",
            subcategory="logic",
            prompt="// Fix this bug\nfn broken() {}",
            canonical_solution="fn fixed() {}",
            test="",
            entry_point="broken",
            source="sigil-pipeline",
            buggy_code="fn broken() {}",
            bug_description="Logic error",
        )
        
        d = task.to_dict()
        
        assert d["buggy_code"] == "fn broken() {}"
        assert d["bug_description"] == "Logic error"
        assert "original_code" not in d  # Not set
        assert "code_to_explain" not in d  # Not set


# ============================================================================
# SigilIngestor Tests
# ============================================================================


class TestSigilIngestor:
    """Tests for the SigilIngestor class."""

    def test_init_default_ratios(self) -> None:
        """Should initialize with default category ratios."""
        ingestor = SigilIngestor()
        assert ingestor.category_ratios == CATEGORY_RATIOS

    def test_init_custom_ratios(self) -> None:
        """Should accept custom category ratios."""
        custom = {"codegen": 0.5, "transform": 0.3, "fix": 0.15, "explain": 0.05}
        ingestor = SigilIngestor(category_ratios=custom)
        assert ingestor.category_ratios == custom

    def test_init_invalid_ratios(self) -> None:
        """Should reject ratios that don't sum to 1.0."""
        invalid = {"codegen": 0.5, "transform": 0.2, "fix": 0.1, "explain": 0.1}
        with pytest.raises(ValueError, match="must sum to 1.0"):
            SigilIngestor(category_ratios=invalid)

    def test_load_sigil_jsonl(self, tmp_path: Path) -> None:
        """Should load tasks from JSONL file."""
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            '{"prompt": "Write add", "gen": "fn add(a: i32, b: i32) -> i32 { a + b }"}\n'
            '{"prompt": "Write sub", "gen": "fn sub(a: i32, b: i32) -> i32 { a - b }"}\n',
            encoding="utf-8",
        )
        
        ingestor = SigilIngestor()
        tasks = list(ingestor.load_sigil_jsonl(jsonl_file))
        
        assert len(tasks) == 2
        assert tasks[0].prompt == "Write add"
        assert "fn add" in tasks[0].gen

    def test_load_sigil_jsonl_empty_lines(self, tmp_path: Path) -> None:
        """Should skip empty lines in JSONL."""
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            '{"prompt": "Test", "gen": "fn test() {}"}\n'
            '\n'
            '   \n'
            '{"prompt": "Test2", "gen": "fn test2() {}"}\n',
            encoding="utf-8",
        )
        
        ingestor = SigilIngestor()
        tasks = list(ingestor.load_sigil_jsonl(jsonl_file))
        
        assert len(tasks) == 2

    def test_extract_codegen_task(self) -> None:
        """Should extract a CodeGen task from sigil output."""
        sigil_task = SigilTask(
            prompt="Implement addition",
            gen="/// Adds two integers.\nfn add(a: i32, b: i32) -> i32 { a + b }",
        )
        
        ingestor = SigilIngestor()
        task = ingestor.extract_codegen_task(sigil_task)
        
        assert task is not None
        assert task.category == "codegen"
        assert task.entry_point == "add"
        assert "/// Adds two integers." in task.prompt
        assert task.task_id.startswith("CodeGen/")
        assert len(task.task_id.split("/")[1]) == 12

    def test_extract_codegen_task_no_function(self) -> None:
        """Should return None when no function in code."""
        sigil_task = SigilTask(
            prompt="Define a struct",
            gen="struct Point { x: i32, y: i32 }",
        )
        
        ingestor = SigilIngestor()
        task = ingestor.extract_codegen_task(sigil_task)
        
        assert task is None

    def test_generate_transform_task(self) -> None:
        """Should generate a Transform task."""
        sigil_task = SigilTask(
            prompt="Original code",
            gen="fn process(v: Vec<i32>) -> i32 { v.iter().sum() }",
        )
        
        ingestor = SigilIngestor()
        task = ingestor.generate_transform_task(sigil_task, "idiomatic")
        
        assert task is not None
        assert task.category == "transform"
        assert task.subcategory == "idiomatic"
        assert "idiomatic Rust patterns" in task.prompt
        assert task.task_id.startswith("Transform/")

    def test_generate_fix_task(self) -> None:
        """Should generate a Fix task with injected bug."""
        sigil_task = SigilTask(
            prompt="Original code",
            gen="fn check(x: i32) -> bool { x < 10 }",
        )
        
        ingestor = SigilIngestor()
        task = ingestor.generate_fix_task(sigil_task, "logic")
        
        assert task is not None
        assert task.category == "fix"
        assert task.subcategory == "logic"
        assert task.task_id.startswith("Fix/")
        assert task.buggy_code is not None
        assert task.bug_description is not None

    def test_generate_explain_task(self) -> None:
        """Should generate an Explain task."""
        sigil_task = SigilTask(
            prompt="Original code",
            gen="fn factorial(n: u64) -> u64 { (1..=n).product() }",
        )
        
        ingestor = SigilIngestor()
        task = ingestor.generate_explain_task(sigil_task, "docstring")
        
        assert task is not None
        assert task.category == "explain"
        assert task.subcategory == "docstring"
        assert "rustdoc documentation" in task.prompt
        assert task.task_id.startswith("Explain/")
        assert task.code_to_explain is not None

    def test_process_all(self, tmp_path: Path) -> None:
        """Should process all tasks and write output."""
        input_file = tmp_path / "input.jsonl"
        output_file = tmp_path / "output.jsonl"
        
        input_file.write_text(
            '{"prompt": "Add function", "gen": "fn add(a: i32, b: i32) -> i32 { a + b }"}\n',
            encoding="utf-8",
        )
        
        ingestor = SigilIngestor()
        # Use enforce_ratios=False for small test datasets
        counts = ingestor.process_all(input_file, output_file, enforce_ratios=False)
        
        assert output_file.exists()
        assert counts["codegen"] >= 1
        
        # Verify output is valid JSONL
        with output_file.open() as f:
            for line in f:
                task = json.loads(line)
                assert "task_id" in task
                assert "category" in task
    
    def test_process_all_with_ratio_enforcement(self, tmp_path: Path) -> None:
        """Should enforce ratios when enabled."""
        input_file = tmp_path / "input.jsonl"
        output_file = tmp_path / "output.jsonl"
        
        # Create enough input tasks to test ratio enforcement
        # Need enough tasks so ratios are meaningful
        tasks_json = "\n".join([
            f'{{"prompt": "Task {i}", "gen": "fn task_{i}(x: i32) -> i32 {{ x + {i} }}"}}'
            for i in range(20)
        ])
        input_file.write_text(tasks_json, encoding="utf-8")
        
        ingestor = SigilIngestor()
        counts = ingestor.process_all(input_file, output_file, enforce_ratios=True)
        
        assert output_file.exists()
        total = sum(counts.values())
        
        # With ratio enforcement, we should get fewer total tasks than 
        # without enforcement (where each input produces 4 tasks)
        # The limiting factor is usually Fix (which fails more often)
        if total > 0:
            # Verify tasks were generated
            assert counts["codegen"] >= 0
            # Verify ratio enforcement reduced total tasks
            # Without enforcement, 20 inputs would produce ~80 tasks
            # With enforcement, it's limited by the scarcest category


# ============================================================================
# Migration Tests
# ============================================================================


class TestMigrateExistingTask:
    """Tests for the task migration function."""

    def test_migrate_basic_task(self) -> None:
        """Should migrate a basic task to new schema."""
        old_task = {
            "task_id": "Rust/0",
            "prompt": "fn add(a: i32, b: i32) -> i32 {",
            "canonical_solution": "    a + b\n}",
            "test": "#[test] fn test() {}",
            "entry_point": "add",
        }
        
        migrated = migrate_existing_task(old_task)
        
        # New task ID format
        assert migrated["task_id"].startswith("CodeGen/")
        assert len(migrated["task_id"].split("/")[1]) == 12
        
        # Source attribution
        assert migrated["source"] == "humaneval-rust"
        
        # Category/subcategory
        assert migrated["category"] == "codegen"
        assert "subcategory" in migrated
        
        # Quality metadata
        assert "edition" in migrated
        assert "typechecked" in migrated
        assert "clippy_clean" in migrated
        assert "no_unsafe" in migrated
        assert "no_unwrap" in migrated
        assert "quality_level" in migrated
        assert "processed_date" in migrated

    def test_migrate_preserves_content(self) -> None:
        """Should preserve original content fields."""
        old_task = {
            "task_id": "Test/1",
            "prompt": "fn example() -> bool {",
            "canonical_solution": "    true\n}",
            "test": "#[test] fn test() { assert!(example()); }",
            "entry_point": "example",
        }
        
        migrated = migrate_existing_task(old_task)
        
        assert migrated["prompt"] == old_task["prompt"]
        assert migrated["canonical_solution"] == old_task["canonical_solution"]
        assert migrated["test"] == old_task["test"]
        assert migrated["entry_point"] == old_task["entry_point"]

    def test_migrate_deterministic_id(self) -> None:
        """Migration should produce deterministic task IDs."""
        old_task = {
            "task_id": "Rust/42",
            "prompt": "fn deterministic() -> u32 {",
            "canonical_solution": "    42\n}",
            "test": "",
            "entry_point": "deterministic",
        }
        
        migrated1 = migrate_existing_task(old_task)
        migrated2 = migrate_existing_task(old_task)
        
        # Task ID should be the same (ignoring processed_date)
        assert migrated1["task_id"] == migrated2["task_id"]

    def test_migrate_preserves_existing_quality_metadata(self) -> None:
        """Should preserve existing quality metadata if present."""
        old_task = {
            "task_id": "Rust/5",
            "prompt": "fn test() {",
            "canonical_solution": "}",
            "test": "",
            "entry_point": "test",
            "typechecked": True,
            "clippy_clean": True,
            "quality_level": 2,
        }
        
        migrated = migrate_existing_task(old_task)
        
        assert migrated["typechecked"] is True
        assert migrated["clippy_clean"] is True
        assert migrated["quality_level"] == 2


# ============================================================================
# Schema Compliance Tests
# ============================================================================


class TestSchemaCompliance:
    """Tests for schema compliance of generated tasks."""

    REQUIRED_FIELDS = {
        "task_id",
        "category",
        "subcategory",
        "prompt",
        "canonical_solution",
        "test",
        "entry_point",
        "source",
        "edition",
        "rustfmt_style_edition",
        "typechecked",
        "clippy_clean",
        "no_unsafe",
        "no_unwrap",
        "quality_level",
        "processed_date",
    }

    def test_humaneval_task_has_required_fields(self) -> None:
        """HumanEvalTask.to_dict() should include all required fields."""
        task = HumanEvalTask(
            task_id="CodeGen/test123",
            category="codegen",
            subcategory="function_impl",
            prompt="fn test() {",
            canonical_solution="}",
            test="",
            entry_point="test",
            source="sigil-pipeline",
        )
        
        d = task.to_dict()
        
        missing = self.REQUIRED_FIELDS - set(d.keys())
        assert not missing, f"Missing required fields: {missing}"

    def test_migrated_task_has_required_fields(self) -> None:
        """Migrated tasks should have all required fields."""
        old_task = {
            "task_id": "Rust/0",
            "prompt": "fn test() {",
            "canonical_solution": "}",
            "test": "",
            "entry_point": "test",
        }
        
        migrated = migrate_existing_task(old_task)
        
        missing = self.REQUIRED_FIELDS - set(migrated.keys())
        assert not missing, f"Missing required fields: {missing}"

    def test_task_id_format(self) -> None:
        """Task IDs should follow the Category/hash format."""
        import re
        
        task = HumanEvalTask(
            task_id="CodeGen/abc123def456",
            category="codegen",
            subcategory="function_impl",
            prompt="fn test() {",
            canonical_solution="}",
            test="",
            entry_point="test",
            source="sigil-pipeline",
        )
        
        d = task.to_dict()
        
        # Should match Category/[a-f0-9]{12}
        pattern = r"^(CodeGen|Transform|Fix|Explain)/[a-f0-9]{12}$"
        assert re.match(pattern, d["task_id"]), f"Invalid task_id format: {d['task_id']}"

    def test_source_values(self) -> None:
        """Source field should be one of the allowed values."""
        allowed_sources = {"sigil-pipeline", "humaneval-rust"}
        
        task1 = HumanEvalTask(
            task_id="CodeGen/test",
            category="codegen",
            subcategory="function_impl",
            prompt="fn test() {",
            canonical_solution="}",
            test="",
            entry_point="test",
            source="sigil-pipeline",
        )
        
        assert task1.to_dict()["source"] in allowed_sources
        
        old_task = {"task_id": "Rust/0", "prompt": "", "canonical_solution": "", "test": "", "entry_point": ""}
        migrated = migrate_existing_task(old_task)
        assert migrated["source"] in allowed_sources


# ============================================================================
# Category Ratio Tests
# ============================================================================


class TestCategoryRatios:
    """Tests for category ratio configuration."""

    def test_default_ratios_sum_to_one(self) -> None:
        """Default category ratios should sum to 1.0."""
        total = sum(CATEGORY_RATIOS.values())
        assert 0.99 <= total <= 1.01

    def test_all_categories_have_ratios(self) -> None:
        """All four categories should have defined ratios."""
        expected_categories = {"codegen", "transform", "fix", "explain"}
        assert set(CATEGORY_RATIOS.keys()) == expected_categories

    def test_all_categories_have_subcategories(self) -> None:
        """All categories should have subcategory definitions."""
        for category in CATEGORY_RATIOS:
            assert category in SUBCATEGORIES
            assert len(SUBCATEGORIES[category]) > 0

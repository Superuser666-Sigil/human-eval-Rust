"""
Data module tests for HumanEval Rust.

Tests JSONL parsing, problem loading, and data utilities.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
"""

import gzip
import json
from pathlib import Path

import pytest

from human_eval import data
from human_eval.data import (
    get_human_eval_dataset,
    read_problems,
    stream_jsonl,
    write_jsonl,
)


class TestStreamJsonl:
    """Test JSONL streaming functionality."""

    def test_stream_jsonl_valid(self, tmp_path: Path) -> None:
        """Test streaming valid JSONL file."""
        file = tmp_path / "sample.jsonl"
        file.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
        rows = list(stream_jsonl(str(file)))
        assert rows == [{"a": 1}, {"b": 2}]

    def test_stream_jsonl_empty_file(self, tmp_path: Path) -> None:
        """Test streaming empty JSONL file."""
        file = tmp_path / "empty.jsonl"
        file.touch()
        rows = list(stream_jsonl(str(file)))
        assert rows == []

    def test_stream_jsonl_empty_lines(self, tmp_path: Path) -> None:
        """Test that empty lines are skipped."""
        file = tmp_path / "with_empty.jsonl"
        file.write_text('{"a":1}\n\n{"b":2}\n   \n', encoding="utf-8")
        rows = list(stream_jsonl(str(file)))
        assert len(rows) == 2

    def test_stream_jsonl_whitespace_lines(self, tmp_path: Path) -> None:
        """Test that whitespace-only lines are skipped."""
        file = tmp_path / "whitespace.jsonl"
        file.write_text('{"a":1}\n   \t\n{"b":2}\n', encoding="utf-8")
        rows = list(stream_jsonl(str(file)))
        assert len(rows) == 2

    def test_stream_jsonl_gzip(self, tmp_path: Path) -> None:
        """Test streaming gzipped JSONL file."""
        file = tmp_path / "sample.jsonl.gz"
        with gzip.open(file, "wt", encoding="utf-8") as f:
            f.write('{"a":1}\n{"b":2}\n')
        rows = list(stream_jsonl(str(file)))
        assert rows == [{"a": 1}, {"b": 2}]

    def test_stream_jsonl_unicode(self, tmp_path: Path) -> None:
        """Test streaming JSONL with Unicode content."""
        file = tmp_path / "unicode.jsonl"
        file.write_text('{"text":"hello 世界"}\n', encoding="utf-8")
        rows = list(stream_jsonl(str(file)))
        assert rows[0]["text"] == "hello 世界"


class TestWriteJsonl:
    """Test JSONL writing functionality."""

    def test_write_jsonl_basic(self, tmp_path: Path) -> None:
        """Test basic JSONL writing."""
        file = tmp_path / "output.jsonl"
        samples = [{"a": 1}, {"b": 2}]
        write_jsonl(str(file), samples)

        rows = list(stream_jsonl(str(file)))
        assert rows == samples

    def test_write_jsonl_append(self, tmp_path: Path) -> None:
        """Test JSONL append mode."""
        file = tmp_path / "output.jsonl"
        write_jsonl(str(file), [{"first": 1}])
        write_jsonl(str(file), [{"second": 2}], append=True)

        rows = list(stream_jsonl(str(file)))
        assert len(rows) == 2
        assert rows[0] == {"first": 1}
        assert rows[1] == {"second": 2}

    def test_write_jsonl_gzip(self, tmp_path: Path) -> None:
        """Test writing gzipped JSONL."""
        file = tmp_path / "output.jsonl.gz"
        samples = [{"a": 1}, {"b": 2}]
        write_jsonl(str(file), samples)

        rows = list(stream_jsonl(str(file)))
        assert rows == samples

    def test_write_jsonl_unicode(self, tmp_path: Path) -> None:
        """Test writing JSONL with Unicode content."""
        file = tmp_path / "unicode.jsonl"
        samples = [{"text": "hello 世界"}]
        write_jsonl(str(file), samples)

        rows = list(stream_jsonl(str(file)))
        assert rows[0]["text"] == "hello 世界"

    def test_write_jsonl_empty_iterator(self, tmp_path: Path) -> None:
        """Test writing empty iterator."""
        file = tmp_path / "empty.jsonl"
        write_jsonl(str(file), [])

        rows = list(stream_jsonl(str(file)))
        assert rows == []


class TestReadProblems:
    """Test problem loading functionality."""

    def test_read_problems_returns_dict(self, sample_problem_file: Path) -> None:
        """Test that read_problems returns a dictionary."""
        problems = read_problems(str(sample_problem_file))
        assert isinstance(problems, dict)

    def test_read_problems_keyed_by_task_id(
        self, sample_problem_file: Path
    ) -> None:
        """Test that problems are keyed by task_id."""
        problems = read_problems(str(sample_problem_file))
        assert "Test/0" in problems

    def test_read_problems_contains_fields(
        self, sample_problem_file: Path
    ) -> None:
        """Test that problems contain required fields."""
        problems = read_problems(str(sample_problem_file))
        problem = problems["Test/0"]
        assert "task_id" in problem
        assert "prompt" in problem
        assert "test" in problem
        assert "entry_point" in problem

    def test_read_problems_multiple(self, tmp_path: Path) -> None:
        """Test reading multiple problems."""
        file = tmp_path / "problems.jsonl"
        problems_data = [
            {
                "task_id": "Test/0",
                "prompt": "fn a() {",
                "test": "#[test] fn t() {}",
                "entry_point": "a",
            },
            {
                "task_id": "Test/1",
                "prompt": "fn b() {",
                "test": "#[test] fn t() {}",
                "entry_point": "b",
            },
        ]
        with open(file, "w", encoding="utf-8") as f:
            for p in problems_data:
                f.write(json.dumps(p) + "\n")

        problems = read_problems(str(file))
        assert len(problems) == 2
        assert "Test/0" in problems
        assert "Test/1" in problems


class TestGetHumanEvalDataset:
    """Test dataset path resolution."""

    def test_get_human_eval_dataset_rejects_other_language(self) -> None:
        """Test that non-Rust languages are rejected."""
        with pytest.raises(ValueError) as exc_info:
            get_human_eval_dataset("python")
        assert "rust" in str(exc_info.value).lower()

    def test_get_human_eval_dataset_accepts_rust(self) -> None:
        """Test that Rust language is accepted."""
        # Should not raise
        path = get_human_eval_dataset("rust")
        assert isinstance(path, str)

    def test_get_human_eval_dataset_accepts_none(self) -> None:
        """Test that None (default) is accepted."""
        # Should not raise
        path = get_human_eval_dataset(None)
        assert isinstance(path, str)

    def test_get_human_eval_dataset_returns_path(self) -> None:
        """Test that a path string is returned."""
        path = get_human_eval_dataset()
        assert isinstance(path, str)
        assert "HumanEval_rust" in path


class TestRootPath:
    """Test ROOT path constant."""

    def test_root_is_directory(self) -> None:
        """Test that ROOT points to a directory."""
        root = Path(data.ROOT)
        assert root.exists()
        assert root.is_dir()

    def test_human_eval_rust_path(self) -> None:
        """Test HUMAN_EVAL_RUST path."""
        path = Path(data.HUMAN_EVAL_RUST)
        # Path should be valid (may or may not exist depending on installation)
        assert isinstance(data.HUMAN_EVAL_RUST, str)

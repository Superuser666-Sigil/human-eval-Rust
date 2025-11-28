import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def sample_problem():
    return {
        "task_id": "Test/0",
        "prompt": "fn add(a: i32, b: i32) -> i32 {",
        "test": "#[test] fn test_add() { assert_eq!(add(1, 2), 3); }",
        "entry_point": "add",
    }

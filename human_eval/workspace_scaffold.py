"""
Workspace Scaffold Generator for Rust 2024 Benchmark Hardening.

This module generates a Cargo workspace structure for validating benchmark
tasks through the Rust 2024 hardening pipeline (cargo fmt, cargo check,
cargo clippy, cargo test).

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 2.4.0

See ADR-007 and the Rust 2024 Benchmark Hardening Pipeline document.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Workspace-level Cargo.toml template
WORKSPACE_CARGO_TOML = '''# Auto-generated workspace for benchmark hardening
# See: docs/adr/ADR-007-sigilderg-pipeline-integration.md

[workspace]
members = [
{members}
]
resolver = "2"

[workspace.lints.clippy]
unwrap_used = "deny"
expect_used = "deny"
panic = "deny"
'''

# Per-crate Cargo.toml template
CRATE_CARGO_TOML = '''# Auto-generated from benchmark task
# Task ID: {task_id}

[package]
name = "{crate_name}"
version = "0.1.0"
edition = "2024"

[lib]
name = "{crate_name}"
path = "src/lib.rs"

[lints]
workspace = true

[dev-dependencies]
proptest = {{ version = "1", default-features = false, features = ["std"] }}
'''

# .rustfmt.toml for workspace
RUSTFMT_TOML = '''# Rust 2024 style edition
style_edition = "2024"
'''

# clippy.toml for workspace
CLIPPY_TOML = '''# Clippy configuration for benchmark hardening
msrv = "1.80.0"

# Allow dbg! in tests only
allow-dbg-in-tests = true
'''

# lib.rs template with markers
LIB_RS_TEMPLATE = '''// AUTO-GENERATED FROM BENCHMARK DATASET
// DO NOT EDIT BY HAND
// Task ID: {task_id}
// Source: {source}

{imports}

// BEGIN_PROMPT
{prompt}
// END_PROMPT

// BEGIN_CANONICAL_SOLUTION
{canonical_solution}
// END_CANONICAL_SOLUTION

{test_module}
'''

# Test module template
TEST_MODULE_TEMPLATE = '''#[cfg(test)]
mod tests {{
    use super::*;

    // BEGIN_TESTS
{tests}
    // END_TESTS
}}
'''


def sanitize_crate_name(task_id: str) -> str:
    """
    Convert a task ID to a valid Rust crate name.
    
    Rules:
    - Must be lowercase
    - Must start with a letter
    - Only alphanumeric and underscores allowed
    - Replace '/' with '_'
    
    Args:
        task_id: Task ID like "CodeGen/a3f8c2e1b4d9"
    
    Returns:
        Valid crate name like "codegen_a3f8c2e1b4d9"
    """
    # Replace / with _
    name = task_id.replace("/", "_")
    # Lowercase
    name = name.lower()
    # Replace any non-alphanumeric (except underscore) with underscore
    name = re.sub(r"[^a-z0-9_]", "_", name)
    # Ensure starts with letter
    if name and not name[0].isalpha():
        name = "task_" + name
    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name)
    # Remove trailing underscores
    name = name.strip("_")
    
    return name or "unnamed_task"


def sanitize_dir_name(task_id: str) -> str:
    """
    Convert a task ID to a valid directory name.
    
    Args:
        task_id: Task ID like "CodeGen/a3f8c2e1b4d9"
    
    Returns:
        Valid directory name like "CodeGen_a3f8c2e1b4d9"
    """
    # Replace / with _
    name = task_id.replace("/", "_")
    # Replace any problematic characters
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    return name or "unnamed_task"


def extract_imports(code: str) -> list[str]:
    """
    Extract use statements from Rust code.
    
    Args:
        code: Rust source code
    
    Returns:
        List of use statements
    """
    imports = []
    for line in code.split("\n"):
        stripped = line.strip()
        if stripped.startswith("use "):
            imports.append(stripped)
    return imports


def generate_lib_rs(task: dict[str, Any]) -> str:
    """
    Generate lib.rs content for a task.
    
    Args:
        task: Task dictionary with prompt, canonical_solution, test, etc.
    
    Returns:
        Complete lib.rs file content
    """
    task_id = task.get("task_id", "Unknown")
    source = task.get("source", "unknown")
    prompt = task.get("prompt", "")
    canonical_solution = task.get("canonical_solution", "")
    test_code = task.get("test", "")
    
    # Extract imports from canonical solution
    imports = extract_imports(canonical_solution)
    
    # Also check for common imports needed
    if "HashMap" in canonical_solution and "use std::collections::HashMap" not in "\n".join(imports):
        imports.append("use std::collections::HashMap;")
    if "HashSet" in canonical_solution and "use std::collections::HashSet" not in "\n".join(imports):
        imports.append("use std::collections::HashSet;")
    if "BTreeMap" in canonical_solution and "use std::collections::BTreeMap" not in "\n".join(imports):
        imports.append("use std::collections::BTreeMap;")
    
    imports_str = "\n".join(imports) if imports else "// No additional imports"
    
    # Process test code
    if test_code:
        # Check if test_code already includes the mod tests wrapper
        if "#[cfg(test)]" in test_code and "mod tests" in test_code:
            test_module = test_code
        else:
            # Wrap in test module
            # Indent the test code
            indented_tests = "\n".join("    " + line for line in test_code.split("\n"))
            test_module = TEST_MODULE_TEMPLATE.format(tests=indented_tests)
    else:
        test_module = TEST_MODULE_TEMPLATE.format(
            tests="    #[test]\n    fn test_placeholder() {\n        todo!(\"Add tests\");\n    }"
        )
    
    return LIB_RS_TEMPLATE.format(
        task_id=task_id,
        source=source,
        imports=imports_str,
        prompt=prompt,
        canonical_solution=canonical_solution,
        test_module=test_module,
    )


def scaffold_workspace(
    tasks: list[dict[str, Any]],
    output_dir: Path | str,
    overwrite: bool = False,
) -> dict[str, Any]:
    """
    Generate a Cargo workspace for benchmark hardening.
    
    Creates the following structure:
        output_dir/
        ├── Cargo.toml
        ├── .rustfmt.toml
        ├── clippy.toml
        ├── CodeGen_abc123/
        │   ├── Cargo.toml
        │   └── src/lib.rs
        └── ...
    
    Args:
        tasks: List of task dictionaries
        output_dir: Directory to create workspace in
        overwrite: Whether to overwrite existing files
    
    Returns:
        Summary dict with counts and any errors
    """
    output_dir = Path(output_dir)
    
    results = {
        "workspace_dir": str(output_dir),
        "crates_created": 0,
        "crates_skipped": 0,
        "errors": [],
    }
    
    # Create workspace directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Track crate directories for workspace manifest
    crate_dirs: list[str] = []
    
    # Process each task
    for task in tasks:
        task_id = task.get("task_id", "")
        if not task_id:
            results["errors"].append("Task missing task_id")
            continue
        
        dir_name = sanitize_dir_name(task_id)
        crate_name = sanitize_crate_name(task_id)
        crate_dir = output_dir / dir_name
        
        # Check if crate already exists
        if crate_dir.exists() and not overwrite:
            results["crates_skipped"] += 1
            crate_dirs.append(dir_name)
            continue
        
        try:
            # Create crate directory structure
            crate_dir.mkdir(parents=True, exist_ok=True)
            src_dir = crate_dir / "src"
            src_dir.mkdir(exist_ok=True)
            
            # Write Cargo.toml
            cargo_toml = CRATE_CARGO_TOML.format(
                task_id=task_id,
                crate_name=crate_name,
            )
            (crate_dir / "Cargo.toml").write_text(cargo_toml, encoding="utf-8")
            
            # Write lib.rs
            lib_rs = generate_lib_rs(task)
            (src_dir / "lib.rs").write_text(lib_rs, encoding="utf-8")
            
            crate_dirs.append(dir_name)
            results["crates_created"] += 1
            
        except Exception as e:
            results["errors"].append(f"Failed to create {dir_name}: {e}")
    
    # Write workspace-level files
    try:
        # Workspace Cargo.toml
        members_str = ",\n".join(f'    "{d}"' for d in sorted(crate_dirs))
        workspace_toml = WORKSPACE_CARGO_TOML.format(members=members_str)
        (output_dir / "Cargo.toml").write_text(workspace_toml, encoding="utf-8")
        
        # .rustfmt.toml
        (output_dir / ".rustfmt.toml").write_text(RUSTFMT_TOML, encoding="utf-8")
        
        # clippy.toml
        (output_dir / "clippy.toml").write_text(CLIPPY_TOML, encoding="utf-8")
        
    except Exception as e:
        results["errors"].append(f"Failed to write workspace files: {e}")
    
    return results


def extract_from_workspace(
    workspace_dir: Path | str,
) -> list[dict[str, Any]]:
    """
    Extract tasks from a workspace after hardening.
    
    Reads the formatted, validated code from lib.rs files
    using the BEGIN_*/END_* markers.
    
    Args:
        workspace_dir: Path to the workspace
    
    Returns:
        List of updated task dictionaries
    """
    workspace_dir = Path(workspace_dir)
    tasks = []
    
    for crate_dir in workspace_dir.iterdir():
        if not crate_dir.is_dir():
            continue
        
        lib_rs = crate_dir / "src" / "lib.rs"
        if not lib_rs.exists():
            continue
        
        content = lib_rs.read_text(encoding="utf-8")
        
        # Extract task_id from comment
        task_id_match = re.search(r"// Task ID: (.+)", content)
        task_id = task_id_match.group(1) if task_id_match else crate_dir.name
        
        # Extract source
        source_match = re.search(r"// Source: (.+)", content)
        source = source_match.group(1) if source_match else "unknown"
        
        # Extract prompt
        prompt_match = re.search(
            r"// BEGIN_PROMPT\n(.*?)// END_PROMPT",
            content,
            re.DOTALL,
        )
        prompt = prompt_match.group(1).strip() if prompt_match else ""
        
        # Extract canonical solution
        solution_match = re.search(
            r"// BEGIN_CANONICAL_SOLUTION\n(.*?)// END_CANONICAL_SOLUTION",
            content,
            re.DOTALL,
        )
        canonical_solution = solution_match.group(1).strip() if solution_match else ""
        
        # Extract tests
        tests_match = re.search(
            r"// BEGIN_TESTS\n(.*?)// END_TESTS",
            content,
            re.DOTALL,
        )
        tests = tests_match.group(1).strip() if tests_match else ""
        
        # Extract entry point from prompt
        entry_point_match = re.search(r"fn\s+(\w+)", prompt)
        entry_point = entry_point_match.group(1) if entry_point_match else ""
        
        task = {
            "task_id": task_id,
            "prompt": prompt,
            "canonical_solution": canonical_solution,
            "test": tests,
            "entry_point": entry_point,
            "source": source,
            # Mark as hardened
            "typechecked": True,
            "rustfmt_style_edition": "2024",
        }
        
        tasks.append(task)
    
    return tasks

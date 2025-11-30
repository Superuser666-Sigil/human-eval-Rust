"""
Workspace Scaffold Generator for Rust 2024 Benchmark Hardening.

This module generates a Cargo workspace structure for validating benchmark
tasks through the Rust 2024 hardening pipeline (cargo fmt, cargo check,
cargo clippy, cargo test).

Features:
- Automatic external crate dependency detection
- Interactive dependency approval workflow
- Workspace-level dependency management
- Unified hardening runner (run_hardening)

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 2.5.0

See ADR-007 and the Rust 2024 Benchmark Hardening Pipeline document.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


# =============================================================================
# Dependency Detection & Registry
# =============================================================================

# Map of common Rust module paths to their crate names and versions
# Format: "module_path" -> ("crate_name", "version", "features" or None)
# Note: Module paths use underscores, crate names in Cargo.toml may use hyphens
KNOWN_CRATES_REGISTRY: dict[str, tuple[str, str, list[str] | None]] = {
    # Rocket framework
    "rocket": ("rocket", "0.5", ["secrets"]),
    "rocket_http": ("rocket", "0.5", None),
    "rocket_codegen": ("rocket", "0.5", None),
    # Async runtimes
    "tokio": ("tokio", "1", ["full"]),
    "async_trait": ("async-trait", "0.1", None),
    "futures": ("futures", "0.3", None),
    # Serialization
    "serde": ("serde", "1", ["derive"]),
    "serde_json": ("serde_json", "1", None),
    # Configuration
    "figment": ("figment", "0.10", ["toml", "env"]),
    # CLI/terminal
    "yansi": ("yansi", "1", None),
    # Time handling
    "time": ("time", "0.3", None),
    "chrono": ("chrono", "0.4", None),
    # Crypto
    "cookie": ("cookie", "0.18", ["signed", "private"]),
    # Networking
    "hyper": ("hyper", "1", None),
    "reqwest": ("reqwest", "0.12", None),
    # Utils
    "either": ("either", "1", None),
    "parking_lot": ("parking_lot", "0.12", None),
    "pin_project_lite": ("pin-project-lite", "0.2", None),
    "bytes": ("bytes", "1", None),
    "tokio_util": ("tokio-util", "0.7", ["io"]),
    # Testing
    "criterion": ("criterion", "0.5", None),
    "proptest": ("proptest", "1", None),
}


@dataclass
class DependencyAnalysis:
    """Results of analyzing code for external dependencies."""
    
    # Detected external crate imports (module_path -> count)
    detected_imports: Counter[str] = field(default_factory=Counter)
    
    # Resolved to known crates: crate_name -> (version, features, import_count)
    resolved_crates: dict[str, tuple[str, list[str] | None, int]] = field(
        default_factory=dict
    )
    
    # Unresolved imports (not in registry)
    unresolved_imports: Counter[str] = field(default_factory=Counter)
    
    # Tasks that will likely fail without dependencies
    affected_tasks: int = 0
    total_tasks: int = 0
    
    def add_import(self, module_path: str) -> None:
        """Register a detected import."""
        self.detected_imports[module_path] += 1
        
        # Try to resolve to known crate
        root_module = module_path.split("::")[0]
        if root_module in KNOWN_CRATES_REGISTRY:
            crate_name, version, features = KNOWN_CRATES_REGISTRY[root_module]
            if crate_name not in self.resolved_crates:
                self.resolved_crates[crate_name] = (version, features, 0)
            # Update count
            _, feat, count = self.resolved_crates[crate_name]
            self.resolved_crates[crate_name] = (version, feat, count + 1)
        elif root_module not in ("std", "core", "alloc", "self", "super", "crate"):
            self.unresolved_imports[root_module] += 1
    
    def has_external_deps(self) -> bool:
        """Check if any external dependencies were detected."""
        return bool(self.resolved_crates) or bool(self.unresolved_imports)
    
    def format_summary(self) -> str:
        """Format a human-readable summary."""
        lines = []
        lines.append(f"Dependency Analysis ({self.affected_tasks}/{self.total_tasks} tasks affected)")
        lines.append("=" * 60)
        
        if self.resolved_crates:
            lines.append("\n[+] Detected External Crates (can be auto-added):")
            for crate, (version, features, count) in sorted(
                self.resolved_crates.items(), key=lambda x: -x[1][2]
            ):
                feat_str = f' features={features}' if features else ''
                lines.append(f"    {crate} = \"{version}\"{feat_str}  ({count} imports)")
        
        if self.unresolved_imports:
            lines.append("\n[!] Unresolved Imports (manual resolution needed):")
            for module, count in self.unresolved_imports.most_common(10):
                lines.append(f"    {module}  ({count} imports)")
            if len(self.unresolved_imports) > 10:
                lines.append(f"    ... and {len(self.unresolved_imports) - 10} more")
        
        if not self.has_external_deps():
            lines.append("\n[OK] No external dependencies detected!")
        
        return "\n".join(lines)
    
    def format_consequences(self) -> str:
        """Format warning about consequences of not adding dependencies."""
        if not self.has_external_deps():
            return ""
        
        lines = []
        lines.append("\n[!] Consequences of skipping dependency installation:")
        lines.append(f"    - {self.affected_tasks} tasks will fail `cargo check`")
        lines.append("    - `cargo clippy` will report unresolved import errors")
        lines.append("    - `cargo test` will not run for affected crates")
        lines.append("    - Tasks will remain at quality_level=0 (unhardened)")
        return "\n".join(lines)


def analyze_dependencies(tasks: list[dict[str, Any]]) -> DependencyAnalysis:
    """
    Analyze tasks to detect external crate dependencies.
    
    Scans prompts and canonical solutions for:
    - `use crate_name::...` statements
    - `extern crate` declarations
    - Common framework patterns
    
    Args:
        tasks: List of task dictionaries
    
    Returns:
        DependencyAnalysis with detected dependencies
    """
    analysis = DependencyAnalysis()
    analysis.total_tasks = len(tasks)
    
    # Patterns to detect imports - require :: to avoid matching doc comment words
    use_pattern = re.compile(r"use\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:::|;)")
    extern_pattern = re.compile(r"extern\s+crate\s+([a-zA-Z_][a-zA-Z0-9_]*)")
    
    # Words to ignore (common English words that appear in doc comments)
    ignore_words = {
        "the", "of", "this", "a", "an", "is", "as", "to", "in", "for", "with",
        "that", "it", "be", "on", "or", "by", "from", "at", "which", "when",
        "if", "all", "are", "can", "has", "was", "were", "will", "would",
        "should", "could", "may", "might", "must", "shall", "not", "no",
        "implementation", "ref", "mut", "pub", "fn", "struct", "enum", "impl",
        "trait", "type", "where", "let", "const", "static", "mod", "match",
    }
    
    for task in tasks:
        task_has_external = False
        
        # Scan all code fields
        for code_field in ("prompt", "canonical_solution", "test"):
            code = task.get(code_field, "")
            if not code:
                continue
            
            # Find use statements
            for match in use_pattern.finditer(code):
                module_path = match.group(1)
                root = module_path.split("::")[0].lower()
                
                # Skip std library and common keywords
                if root in ("std", "core", "alloc", "self", "super", "crate"):
                    continue
                if root in ignore_words:
                    continue
                
                analysis.add_import(module_path)
                if module_path.lower() in KNOWN_CRATES_REGISTRY or module_path in KNOWN_CRATES_REGISTRY:
                    task_has_external = True
            
            # Find extern crate
            for match in extern_pattern.finditer(code):
                crate_name = match.group(1)
                if crate_name.lower() in ignore_words:
                    continue
                if crate_name not in ("std", "core", "alloc"):
                    analysis.add_import(crate_name)
                    task_has_external = True
        
        if task_has_external:
            analysis.affected_tasks += 1
    
    return analysis


def generate_workspace_dependencies(analysis: DependencyAnalysis) -> str:
    """
    Generate [workspace.dependencies] section for Cargo.toml.
    
    Args:
        analysis: DependencyAnalysis with resolved crates
    
    Returns:
        TOML string for workspace dependencies section
    """
    if not analysis.resolved_crates:
        return ""
    
    lines = ["[workspace.dependencies]"]
    
    for crate_name, (version, features, _) in sorted(analysis.resolved_crates.items()):
        if features:
            feat_str = ", ".join(f'"{f}"' for f in features)
            lines.append(f'{crate_name} = {{ version = "{version}", features = [{feat_str}] }}')
        else:
            lines.append(f'{crate_name} = "{version}"')
    
    return "\n".join(lines)


# =============================================================================
# Templates
# =============================================================================

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

{workspace_deps}
'''

# Per-crate Cargo.toml template (with workspace dependencies)
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

[dependencies]
{crate_deps}

[dev-dependencies]
proptest.workspace = true
'''

# Per-crate Cargo.toml template (without workspace dependencies)
CRATE_CARGO_TOML_MINIMAL = '''# Auto-generated from benchmark task
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
proptest = { version = "1", default-features = false, features = ["std"] }
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


@dataclass
class DependencyDecision:
    """User's decision about dependency handling."""
    
    install_deps: bool = False
    selected_crates: set[str] = field(default_factory=set)
    skipped_crates: set[str] = field(default_factory=set)


def prompt_for_dependencies(
    analysis: DependencyAnalysis,
    auto_approve: bool = False,
    auto_reject: bool = False,
    output_func: Callable[[str], None] | None = None,
    input_func: Callable[[str], str] | None = None,
) -> DependencyDecision:
    """
    Interactively prompt user for dependency installation decision.
    
    Args:
        analysis: DependencyAnalysis from analyze_dependencies()
        auto_approve: If True, automatically approve all dependencies
        auto_reject: If True, automatically reject all dependencies
        output_func: Function to print output (default: print)
        input_func: Function to get input (default: input)
    
    Returns:
        DependencyDecision with user's choices
    """
    output = output_func or print
    get_input = input_func or input
    
    decision = DependencyDecision()
    
    if not analysis.has_external_deps():
        decision.install_deps = False
        return decision
    
    # Show analysis summary
    output("\n" + analysis.format_summary())
    
    if auto_approve:
        output("\n[OK] Auto-approving all detected dependencies (--auto-deps)")
        decision.install_deps = True
        decision.selected_crates = set(analysis.resolved_crates.keys())
        return decision
    
    if auto_reject:
        output("\n[!] Skipping dependency installation (--no-deps)")
        output(analysis.format_consequences())
        decision.install_deps = False
        decision.skipped_crates = set(analysis.resolved_crates.keys())
        return decision
    
    # Interactive prompt
    output(analysis.format_consequences())
    output("\n" + "=" * 60)
    output("Options:")
    output("  [Y] Yes - Add all detected dependencies to workspace")
    output("  [N] No  - Skip dependencies (some tasks won't compile)")
    output("  [S] Select - Choose which dependencies to add")
    output("  [Q] Quit - Abort scaffolding")
    
    while True:
        try:
            choice = get_input("\nAdd dependencies? [Y/n/s/q]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = "q"
        
        if choice in ("", "y", "yes"):
            decision.install_deps = True
            decision.selected_crates = set(analysis.resolved_crates.keys())
            output("\n[OK] Will add all detected dependencies")
            break
        elif choice in ("n", "no"):
            decision.install_deps = False
            decision.skipped_crates = set(analysis.resolved_crates.keys())
            output("\n[!] Skipping dependencies - some tasks will not compile")
            break
        elif choice in ("s", "select"):
            # Individual selection
            output("\nSelect dependencies (y/n for each):")
            for crate, (version, features, count) in sorted(analysis.resolved_crates.items()):
                feat_str = f" (features: {features})" if features else ""
                try:
                    ans = get_input(f"  Add {crate}={version}{feat_str}? [{count} imports] [Y/n]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ans = "n"
                if ans in ("", "y", "yes"):
                    decision.selected_crates.add(crate)
                else:
                    decision.skipped_crates.add(crate)
            decision.install_deps = bool(decision.selected_crates)
            break
        elif choice in ("q", "quit"):
            raise KeyboardInterrupt("User aborted scaffolding")
        else:
            output("Invalid choice. Please enter Y, N, S, or Q.")
    
    return decision


def _get_task_dependencies(task: dict[str, Any], selected_crates: set[str]) -> set[str]:
    """Determine which workspace dependencies a task needs."""
    needed = set()
    
    use_pattern = re.compile(r"use\s+([a-zA-Z_][a-zA-Z0-9_]*)")
    
    for code_field in ("prompt", "canonical_solution", "test"):
        code = task.get(code_field, "")
        if not code:
            continue
        
        for match in use_pattern.finditer(code):
            root_module = match.group(1)
            if root_module in KNOWN_CRATES_REGISTRY:
                crate_name = KNOWN_CRATES_REGISTRY[root_module][0]
                if crate_name in selected_crates:
                    needed.add(crate_name)
    
    return needed


def scaffold_workspace(
    tasks: list[dict[str, Any]],
    output_dir: Path | str,
    overwrite: bool = False,
    dependency_decision: DependencyDecision | None = None,
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
        dependency_decision: Pre-made decision about dependencies (for non-interactive)
    
    Returns:
        Summary dict with counts, errors, and dependency info
    """
    output_dir = Path(output_dir)
    
    results: dict[str, Any] = {
        "workspace_dir": str(output_dir),
        "crates_created": 0,
        "crates_skipped": 0,
        "errors": [],
        "dependencies_added": [],
        "dependencies_skipped": [],
    }
    
    # Determine which dependencies to include
    selected_crates: set[str] = set()
    if dependency_decision and dependency_decision.install_deps:
        selected_crates = dependency_decision.selected_crates
        results["dependencies_added"] = list(selected_crates)
        results["dependencies_skipped"] = list(dependency_decision.skipped_crates)
    
    # Build workspace dependencies section
    workspace_deps_lines = []
    if selected_crates:
        workspace_deps_lines.append("[workspace.dependencies]")
        workspace_deps_lines.append('proptest = { version = "1", default-features = false, features = ["std"] }')
        
        # Build reverse lookup: crate_name -> (version, features)
        crate_versions: dict[str, tuple[str, list[str] | None]] = {}
        for module_name, (crate_name, version, features) in KNOWN_CRATES_REGISTRY.items():
            if crate_name not in crate_versions:
                crate_versions[crate_name] = (version, features)
        
        for crate_name in sorted(selected_crates):
            if crate_name in crate_versions:
                version, features = crate_versions[crate_name]
            else:
                # Fallback for crates resolved but not in registry
                version, features = "*", None
            
            if features:
                feat_str = ", ".join(f'"{f}"' for f in features)
                workspace_deps_lines.append(
                    f'{crate_name} = {{ version = "{version}", features = [{feat_str}] }}'
                )
            else:
                workspace_deps_lines.append(f'{crate_name} = "{version}"')
    
    workspace_deps_str = "\n".join(workspace_deps_lines) if workspace_deps_lines else ""
    
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
            
            # Determine this task's dependencies
            if selected_crates:
                task_deps = _get_task_dependencies(task, selected_crates)
                deps_lines = [f"{dep}.workspace = true" for dep in sorted(task_deps)]
                deps_str = "\n".join(deps_lines) if deps_lines else "# No dependencies"
                
                cargo_toml = CRATE_CARGO_TOML.format(
                    task_id=task_id,
                    crate_name=crate_name,
                    crate_deps=deps_str,
                )
            else:
                cargo_toml = CRATE_CARGO_TOML_MINIMAL.format(
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
        workspace_toml = WORKSPACE_CARGO_TOML.format(
            members=members_str,
            workspace_deps=workspace_deps_str,
        )
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


# =============================================================================
# Hardening Runner
# =============================================================================

@dataclass
class HardeningStepResult:
    """Result of a single hardening step."""
    name: str
    command: list[str]
    success: bool
    duration_ms: int
    stdout: str
    stderr: str
    return_code: int


@dataclass
class HardeningResult:
    """Result of the complete hardening pipeline."""
    workspace_dir: Path
    steps: list[HardeningStepResult] = field(default_factory=list)
    total_duration_ms: int = 0
    
    @property
    def all_passed(self) -> bool:
        """Check if all steps passed."""
        return all(step.success for step in self.steps)
    
    @property
    def fmt_passed(self) -> bool:
        """Check if cargo fmt passed."""
        return any(s.name == "fmt" and s.success for s in self.steps)
    
    @property
    def check_passed(self) -> bool:
        """Check if cargo check passed."""
        return any(s.name == "check" and s.success for s in self.steps)
    
    @property
    def clippy_passed(self) -> bool:
        """Check if cargo clippy passed."""
        return any(s.name == "clippy" and s.success for s in self.steps)
    
    @property
    def test_passed(self) -> bool:
        """Check if cargo test passed."""
        return any(s.name == "test" and s.success for s in self.steps)
    
    def format_report(self) -> str:
        """Format a human-readable report."""
        lines = []
        lines.append(f"Hardening Report for {self.workspace_dir}")
        lines.append("=" * 60)
        lines.append("")
        
        for step in self.steps:
            status = "[OK]" if step.success else "[FAIL]"
            lines.append(f"{status} {step.name}: {step.duration_ms}ms")
            if not step.success and step.stderr:
                # Show first few lines of error
                error_lines = step.stderr.strip().split("\n")[:5]
                for err in error_lines:
                    lines.append(f"     {err}")
                if len(step.stderr.strip().split("\n")) > 5:
                    lines.append("     ...")
        
        lines.append("")
        lines.append(f"Total time: {self.total_duration_ms}ms")
        lines.append(f"Result: {'ALL PASSED' if self.all_passed else 'FAILED'}")
        
        return "\n".join(lines)


def run_hardening(
    workspace_dir: Path | str,
    *,
    apply_fmt: bool = True,
    skip_clippy: bool = False,
    skip_tests: bool = False,
    clippy_flags: list[str] | None = None,
    timeout: float = 300.0,
    verbose: bool = False,
) -> HardeningResult:
    """
    Run the complete Rust 2024 hardening pipeline on a workspace.
    
    This executes the 4-step hardening process:
    1. cargo fmt (format code)
    2. cargo check --all --tests (type checking)
    3. cargo clippy --all --tests (linting with strict flags)
    4. cargo test --all (run tests)
    
    Args:
        workspace_dir: Path to the Cargo workspace
        apply_fmt: If True, apply formatting. If False, just check (--check)
        skip_clippy: Skip the clippy step
        skip_tests: Skip the test step
        clippy_flags: Custom clippy flags. Defaults to strict pedantic/nursery
        timeout: Timeout per step in seconds
        verbose: Print progress to stdout
    
    Returns:
        HardeningResult with details of each step
    """
    workspace_dir = Path(workspace_dir)
    
    if not workspace_dir.exists():
        raise FileNotFoundError(f"Workspace not found: {workspace_dir}")
    
    cargo_toml = workspace_dir / "Cargo.toml"
    if not cargo_toml.exists():
        raise FileNotFoundError(f"No Cargo.toml in workspace: {workspace_dir}")
    
    # Default strict clippy flags per Rust 2024 Benchmark Hardening Pipeline
    if clippy_flags is None:
        clippy_flags = ["-D", "warnings", "-W", "clippy::pedantic", "-W", "clippy::nursery"]
    
    result = HardeningResult(workspace_dir=workspace_dir)
    total_start = time.perf_counter()
    
    def run_step(name: str, cmd: list[str]) -> HardeningStepResult:
        """Run a single hardening step."""
        if verbose:
            print(f"Running: {' '.join(cmd)}")
        
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                cwd=workspace_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            
            step_result = HardeningStepResult(
                name=name,
                command=cmd,
                success=proc.returncode == 0,
                duration_ms=duration_ms,
                stdout=proc.stdout,
                stderr=proc.stderr,
                return_code=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            duration_ms = int((time.perf_counter() - start) * 1000)
            step_result = HardeningStepResult(
                name=name,
                command=cmd,
                success=False,
                duration_ms=duration_ms,
                stdout="",
                stderr=f"Timed out after {timeout}s",
                return_code=-1,
            )
        except FileNotFoundError as e:
            step_result = HardeningStepResult(
                name=name,
                command=cmd,
                success=False,
                duration_ms=0,
                stdout="",
                stderr=str(e),
                return_code=-1,
            )
        
        if verbose:
            status = "OK" if step_result.success else "FAILED"
            print(f"  {name}: {status} ({step_result.duration_ms}ms)")
        
        return step_result
    
    # Step 1: cargo fmt
    fmt_cmd = ["cargo", "fmt"]
    if not apply_fmt:
        fmt_cmd.append("--check")
    result.steps.append(run_step("fmt", fmt_cmd))
    
    # Step 2: cargo check
    check_cmd = ["cargo", "check", "--all", "--tests"]
    result.steps.append(run_step("check", check_cmd))
    
    # Step 3: cargo clippy (optional)
    if not skip_clippy:
        clippy_cmd = ["cargo", "clippy", "--all", "--tests", "--"] + clippy_flags
        result.steps.append(run_step("clippy", clippy_cmd))
    
    # Step 4: cargo test (optional)
    if not skip_tests:
        test_cmd = ["cargo", "test", "--all"]
        result.steps.append(run_step("test", test_cmd))
    
    result.total_duration_ms = int((time.perf_counter() - total_start) * 1000)
    
    return result

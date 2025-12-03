"""
SigilDERG Pipeline Integration Module.

This module provides functionality to ingest data from sigil-pipeline
(SigilDERG Data Production) and transform it into HumanEval-compatible
benchmark tasks across four categories: CodeGen, Transform, Fix, and Explain.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 3.0.0

See ADR-007 for architectural decisions.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

# Task categories and their target ratios
CATEGORY_RATIOS = {
    "codegen": 0.45,
    "transform": 0.25,
    "fix": 0.20,
    "explain": 0.10,
}

# Subcategories for each main category
SUBCATEGORIES = {
    "codegen": [
        "function_impl",
        "iterator_combinator",
        "error_handling",
        "lifetimes",
        "generics",
        "async_await",
        "collections",
    ],
    "transform": [
        "modernize",
        "refactor",
        "adapt",
        "generalize",
        "idiomatic",
    ],
    "fix": [
        "logic",
        "lifetime",
        "type_mismatch",
        "panic",
        "edge_case",
    ],
    "explain": [
        "docstring",
        "summary",
        "walkthrough",
        "complexity",
    ],
}

# Anti-patterns to detect in code
ANTI_PATTERNS = [
    r"\bunsafe\b",
    r"\.unwrap\s*\(",
    r"\.expect\s*\(",
    r"\bpanic!\s*\(",
    r"\btodo!\s*\(",
    r"\bdbg!\s*\(",
]


def compute_task_hash(prompt: str, category: str) -> str:
    """
    Generate a deterministic 12-character hash from prompt content.
    
    The hash is based on the category and prompt text, ensuring:
    - Same input always produces same output (deterministic)
    - Different inputs produce different outputs (collision-resistant)
    - IDs are reasonably short but unique enough for practical use
    
    Args:
        prompt: The task prompt text
        category: The task category (codegen, transform, fix, explain)
    
    Returns:
        12-character hexadecimal hash string
    
    Example:
        >>> compute_task_hash("fn add(a: i32, b: i32) -> i32 {", "codegen")
        'a3f8c2e1b4d9'
    """
    content = f"{category.lower()}:{prompt}".encode("utf-8")
    return hashlib.sha256(content).hexdigest()[:12]


def format_task_id(category: str, hash_id: str) -> str:
    """
    Format a task ID with category prefix and hash.
    
    Args:
        category: Task category (will be title-cased)
        hash_id: 12-character hash from compute_task_hash
    
    Returns:
        Formatted task ID like "CodeGen/a3f8c2e1b4d9"
    """
    category_map = {
        "codegen": "CodeGen",
        "transform": "Transform",
        "fix": "Fix",
        "explain": "Explain",
    }
    prefix = category_map.get(category.lower(), category.title())
    return f"{prefix}/{hash_id}"


def detect_anti_patterns(code: str) -> list[str]:
    """
    Detect anti-patterns in Rust code.
    
    Args:
        code: Rust source code to analyze
    
    Returns:
        List of detected anti-pattern names
    """
    detected = []
    pattern_names = ["unsafe", "unwrap", "expect", "panic", "todo", "dbg"]
    
    for pattern, name in zip(ANTI_PATTERNS, pattern_names):
        if re.search(pattern, code):
            detected.append(name)
    
    return detected


def extract_function_signature(code: str) -> str | None:
    """
    Extract the first public function signature from Rust code.
    
    Args:
        code: Rust source code
    
    Returns:
        Function signature ending with '{', or None if not found
    """
    # Match pub fn or fn declarations
    pattern = r"((?:pub\s+)?fn\s+\w+(?:<[^>]*>)?\s*\([^)]*\)(?:\s*->\s*[^{]+)?)\s*\{"
    match = re.search(pattern, code)
    if match:
        return match.group(1).strip() + " {"
    return None


def extract_entry_point(code: str) -> str | None:
    """
    Extract the function name (entry point) from Rust code.
    
    Args:
        code: Rust source code
    
    Returns:
        Function name, or None if not found
    """
    pattern = r"(?:pub\s+)?fn\s+(\w+)"
    match = re.search(pattern, code)
    if match:
        return match.group(1)
    return None


def extract_doc_comments(code: str) -> str:
    """
    Extract documentation comments from the beginning of Rust code.
    
    Args:
        code: Rust source code
    
    Returns:
        Concatenated doc comments, or empty string if none
    """
    lines = code.strip().split("\n")
    doc_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("///") or stripped.startswith("//!"):
            doc_lines.append(stripped)
        elif stripped.startswith("//"):
            # Regular comments at the start are also included
            doc_lines.append(stripped)
        elif stripped.startswith("#[") or stripped.startswith("pub ") or stripped.startswith("fn "):
            # Stop at attributes or function declarations
            break
        elif stripped == "":
            continue
        else:
            break
    
    return "\n".join(doc_lines)


@dataclass
class SigilTask:
    """Represents a single task from sigil-pipeline output."""
    
    prompt: str
    gen: str
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @property
    def has_function(self) -> bool:
        """Check if the generated code contains a function definition."""
        return bool(extract_function_signature(self.gen))
    
    @property
    def entry_point(self) -> str | None:
        """Extract the main function name."""
        return extract_entry_point(self.gen)
    
    @property
    def anti_patterns(self) -> list[str]:
        """Detect anti-patterns in the generated code."""
        return detect_anti_patterns(self.gen)


@dataclass
class HumanEvalTask:
    """Represents a HumanEval-compatible benchmark task."""
    
    task_id: str
    category: str
    subcategory: str
    prompt: str
    canonical_solution: str
    test: str
    entry_point: str
    source: Literal["sigil-pipeline", "humaneval-rust"]
    
    # Quality metadata
    edition: str = "2024"
    rustfmt_style_edition: str = "2024"
    typechecked: bool = False
    clippy_clean: bool = False
    no_unsafe: bool = True
    no_unwrap: bool = True
    quality_level: int = 0
    processed_date: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Optional fields for specific categories
    original_code: str | None = None  # For Transform tasks
    buggy_code: str | None = None     # For Fix tasks
    bug_description: str | None = None  # For Fix tasks
    code_to_explain: str | None = None  # For Explain tasks
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "task_id": self.task_id,
            "category": self.category,
            "subcategory": self.subcategory,
            "prompt": self.prompt,
            "canonical_solution": self.canonical_solution,
            "test": self.test,
            "entry_point": self.entry_point,
            "source": self.source,
            "edition": self.edition,
            "rustfmt_style_edition": self.rustfmt_style_edition,
            "typechecked": self.typechecked,
            "clippy_clean": self.clippy_clean,
            "no_unsafe": self.no_unsafe,
            "no_unwrap": self.no_unwrap,
            "quality_level": self.quality_level,
            "processed_date": self.processed_date,
        }
        
        # Add optional fields if present
        if self.original_code is not None:
            result["original_code"] = self.original_code
        if self.buggy_code is not None:
            result["buggy_code"] = self.buggy_code
        if self.bug_description is not None:
            result["bug_description"] = self.bug_description
        if self.code_to_explain is not None:
            result["code_to_explain"] = self.code_to_explain
        
        return result


class SigilIngestor:
    """
    Ingests sigil-pipeline output and transforms it into HumanEval tasks.
    
    The ingestor reads JSONL files in the format:
        {"prompt": "...", "gen": "..."}
    
    And produces HumanEval-compatible tasks across four categories.
    """
    
    def __init__(
        self,
        category_ratios: dict[str, float] | None = None,
        source: str = "sigil-pipeline",
    ):
        """
        Initialize the ingestor.
        
        Args:
            category_ratios: Override default category ratios (must sum to 1.0)
            source: Source identifier for provenance tracking
        """
        self.category_ratios = category_ratios or CATEGORY_RATIOS.copy()
        self.source = source
        self._validate_ratios()
    
    def _validate_ratios(self) -> None:
        """Validate that category ratios sum to approximately 1.0."""
        total = sum(self.category_ratios.values())
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Category ratios must sum to 1.0, got {total}")
    
    def load_sigil_jsonl(self, path: Path | str) -> Iterator[SigilTask]:
        """
        Load tasks from a sigil-pipeline JSONL file.
        
        Args:
            path: Path to the JSONL file
        
        Yields:
            SigilTask objects parsed from each line
        """
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    yield SigilTask(
                        prompt=data.get("prompt", ""),
                        gen=data.get("gen", ""),
                        metadata=data.get("metadata", {}),
                    )
                except json.JSONDecodeError as e:
                    print(f"Warning: Failed to parse line {line_num}: {e}")
    
    def extract_codegen_task(self, sigil_task: SigilTask) -> HumanEvalTask | None:
        """
        Extract a CodeGen task from sigil-pipeline output.
        
        Args:
            sigil_task: Raw task from sigil-pipeline
        
        Returns:
            HumanEvalTask if extraction succeeds, None otherwise
        """
        if not sigil_task.has_function:
            return None
        
        entry_point = sigil_task.entry_point
        if not entry_point:
            return None
        
        # Extract function signature as prompt
        signature = extract_function_signature(sigil_task.gen)
        if not signature:
            return None
        
        # Get doc comments to prepend to prompt
        doc_comments = extract_doc_comments(sigil_task.gen)
        if doc_comments:
            prompt = f"{doc_comments}\n{signature}"
        else:
            prompt = signature
        
        # Extract the function body as canonical solution
        # Find the opening brace and extract everything after it
        brace_pos = sigil_task.gen.find("{")
        if brace_pos == -1:
            return None
        
        # Get everything after the opening brace
        body_start = brace_pos + 1
        canonical_solution = sigil_task.gen[body_start:].strip()
        
        # Remove trailing closing brace if it's the last character
        if canonical_solution.endswith("}"):
            # Count braces to find the matching one
            depth = 1
            for i, char in enumerate(canonical_solution):
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                if depth == 0:
                    canonical_solution = canonical_solution[:i].strip()
                    break
        
        # Generate placeholder test
        test = self._generate_placeholder_test(entry_point)
        
        # Check for anti-patterns
        anti_patterns = sigil_task.anti_patterns
        no_unsafe = "unsafe" not in anti_patterns
        no_unwrap = "unwrap" not in anti_patterns and "expect" not in anti_patterns
        
        # Compute task ID
        hash_id = compute_task_hash(prompt, "codegen")
        task_id = format_task_id("codegen", hash_id)
        
        return HumanEvalTask(
            task_id=task_id,
            category="codegen",
            subcategory=self._infer_codegen_subcategory(sigil_task.gen),
            prompt=prompt,
            canonical_solution=canonical_solution,
            test=test,
            entry_point=entry_point,
            source=self.source,
            no_unsafe=no_unsafe,
            no_unwrap=no_unwrap,
        )
    
    def generate_transform_task(
        self,
        sigil_task: SigilTask,
        transform_type: str = "idiomatic",
    ) -> HumanEvalTask | None:
        """
        Generate a Transform task from sigil-pipeline output.
        
        Transform tasks ask the model to refactor or modernize existing code.
        
        Args:
            sigil_task: Raw task from sigil-pipeline
            transform_type: Type of transformation (modernize, refactor, etc.)
        
        Returns:
            HumanEvalTask if generation succeeds, None otherwise
        """
        if not sigil_task.has_function:
            return None
        
        entry_point = sigil_task.entry_point
        if not entry_point:
            return None
        
        # Create a transformation prompt
        transform_prompts = {
            "modernize": (
                "// Modernize this function to use Rust 2024 idioms.\n"
                "// Original:\n"
            ),
            "refactor": (
                "// Refactor this function to improve readability and "
                "maintainability.\n// Original:\n"
            ),
            "idiomatic": (
                "// Rewrite this function using idiomatic Rust patterns "
                "(iterators, combinators).\n// Original:\n"
            ),
            "generalize": "// Generalize this function to work with generic types.\n// Original:\n",
            "adapt": "// Adapt this function to use a different API signature.\n// Original:\n",
        }
        
        prompt_prefix = transform_prompts.get(transform_type, transform_prompts["idiomatic"])
        prompt = f"{prompt_prefix}{sigil_task.gen}"
        
        # The canonical solution is the same code (assuming it's already good)
        # In practice, this would need manual curation or a more sophisticated approach
        
        hash_id = compute_task_hash(prompt, "transform")
        task_id = format_task_id("transform", hash_id)
        
        test = self._generate_placeholder_test(entry_point)
        
        return HumanEvalTask(
            task_id=task_id,
            category="transform",
            subcategory=transform_type,
            prompt=prompt,
            canonical_solution=sigil_task.gen,
            test=test,
            entry_point=entry_point,
            source=self.source,
            original_code=sigil_task.gen,
        )
    
    def generate_fix_task(
        self,
        sigil_task: SigilTask,
        bug_type: str = "logic",
    ) -> HumanEvalTask | None:
        """
        Generate a Fix task by injecting a bug into working code.
        
        Args:
            sigil_task: Raw task from sigil-pipeline (assumed correct)
            bug_type: Type of bug to inject
        
        Returns:
            HumanEvalTask if generation succeeds, None otherwise
        """
        if not sigil_task.has_function:
            return None
        
        entry_point = sigil_task.entry_point
        if not entry_point:
            return None
        
        # Simple bug injection strategies
        buggy_code, bug_desc = self._inject_bug(sigil_task.gen, bug_type)
        if buggy_code is None:
            return None
        
        prompt = f"// This function has a bug. Fix it.\n// Bug type: {bug_type}\n{buggy_code}"
        
        hash_id = compute_task_hash(prompt, "fix")
        task_id = format_task_id("fix", hash_id)
        
        test = self._generate_placeholder_test(entry_point)
        
        return HumanEvalTask(
            task_id=task_id,
            category="fix",
            subcategory=bug_type,
            prompt=prompt,
            canonical_solution=sigil_task.gen,
            test=test,
            entry_point=entry_point,
            source=self.source,
            buggy_code=buggy_code,
            bug_description=bug_desc,
        )
    
    def generate_explain_task(
        self,
        sigil_task: SigilTask,
        explain_type: str = "docstring",
    ) -> HumanEvalTask | None:
        """
        Generate an Explain task asking for documentation or explanation.
        
        Args:
            sigil_task: Raw task from sigil-pipeline
            explain_type: Type of explanation requested
        
        Returns:
            HumanEvalTask if generation succeeds, None otherwise
        """
        if not sigil_task.has_function:
            return None
        
        entry_point = sigil_task.entry_point
        if not entry_point:
            return None
        
        explain_prompts = {
            "docstring": "// Generate comprehensive rustdoc documentation for this function.\n",
            "summary": "// Write a brief summary explaining what this function does.\n",
            "walkthrough": "// Provide a step-by-step walkthrough of this function's logic.\n",
            "complexity": "// Analyze the time and space complexity of this function.\n",
        }
        
        prompt_prefix = explain_prompts.get(explain_type, explain_prompts["docstring"])
        prompt = f"{prompt_prefix}{sigil_task.gen}"
        
        hash_id = compute_task_hash(prompt, "explain")
        task_id = format_task_id("explain", hash_id)
        
        # For explain tasks, the "solution" is example documentation
        canonical_solution = self._generate_example_docs(sigil_task.gen, explain_type)
        
        return HumanEvalTask(
            task_id=task_id,
            category="explain",
            subcategory=explain_type,
            prompt=prompt,
            canonical_solution=canonical_solution,
            test="",  # Explain tasks typically don't have automated tests
            entry_point=entry_point,
            source=self.source,
            code_to_explain=sigil_task.gen,
        )
    
    def _generate_placeholder_test(self, entry_point: str) -> str:
        """Generate a placeholder test module."""
        return f'''#[cfg(test)]
mod tests {{
    use super::*;

    #[test]
    fn test_{entry_point}() {{
        // TODO: Add test cases
        todo!("Add test implementation");
    }}
}}'''
    
    def _infer_codegen_subcategory(self, code: str) -> str:
        """Infer the subcategory based on code patterns."""
        if "async fn" in code or ".await" in code:
            return "async_await"
        if "impl Iterator" in code or ".iter()" in code or ".map(" in code:
            return "iterator_combinator"
        if "Result<" in code or "Option<" in code or "?" in code:
            return "error_handling"
        if "<'" in code or "lifetime" in code.lower():
            return "lifetimes"
        if "<T" in code or "impl<" in code or "where " in code:
            return "generics"
        if "HashMap" in code or "BTreeMap" in code or "Vec<" in code:
            return "collections"
        return "function_impl"
    
    def _inject_bug(self, code: str, bug_type: str) -> tuple[str | None, str | None]:
        """
        Inject a bug into working code.
        
        Returns:
            Tuple of (buggy_code, bug_description) or (None, None) if injection fails
        """
        if bug_type == "logic":
            # Try to flip a comparison operator
            if " < " in code:
                return code.replace(" < ", " <= ", 1), "Off-by-one: used <= instead of <"
            if " > " in code:
                return code.replace(" > ", " >= ", 1), "Off-by-one: used >= instead of >"
            if " == " in code:
                return code.replace(" == ", " != ", 1), "Inverted comparison: used != instead of =="
        
        elif bug_type == "edge_case":
            # Remove an empty check if present
            if "is_empty()" in code:
                return code.replace(".is_empty()", ".len() > 1", 1), "Missing empty check"
            if ".len() == 0" in code:
                return code.replace(".len() == 0", ".len() == 1", 1), "Wrong length check"
        
        elif bug_type == "panic":
            # Replace safe patterns with panicking ones
            if ".get(" in code:
                # Replace .get() with direct indexing (potential panic)
                return re.sub(
                    r"\.get\(([^)]+)\)",
                    r"[\1]",
                    code,
                    count=1,
                ), "Using direct indexing instead of .get() can panic"
        
        return None, None
    
    def _generate_example_docs(self, code: str, explain_type: str) -> str:
        """Generate example documentation as the canonical solution."""
        entry_point = extract_entry_point(code) or "function"
        
        if explain_type == "docstring":
            return f'''/// Brief description of what `{entry_point}` does.
///
/// # Arguments
///
/// * `arg` - Description of the argument
///
/// # Returns
///
/// Description of the return value
///
/// # Examples
///
/// ```
/// // Example usage
/// ```
///
/// # Panics
///
/// Conditions under which this function panics (if any)
'''
        elif explain_type == "complexity":
            return '''// Time Complexity: O(n) where n is the input size
// Space Complexity: O(1) auxiliary space
//
// Analysis:
// - The function iterates through the input once
// - No additional data structures are allocated
'''
        else:
            return f"// Explanation of {entry_point}"
    
    def process_all(
        self,
        input_path: Path | str,
        output_path: Path | str,
        enforce_ratios: bool = True,
    ) -> dict[str, int]:
        """
        Process all tasks from input and write to output.
        
        When enforce_ratios=True (default), the output will match the target
        category ratios by selectively including tasks. When False, all
        successfully generated tasks are included.
        
        Args:
            input_path: Path to sigil-pipeline JSONL
            output_path: Path for output HumanEval JSONL
            enforce_ratios: Whether to enforce target category ratios
        
        Returns:
            Dictionary with counts per category
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # First pass: collect all potential tasks by category
        potential_tasks: dict[str, list[HumanEvalTask]] = {
            "codegen": [],
            "transform": [],
            "fix": [],
            "explain": [],
        }
        
        for sigil_task in self.load_sigil_jsonl(input_path):
            # Generate CodeGen task (primary)
            codegen_task = self.extract_codegen_task(sigil_task)
            if codegen_task:
                potential_tasks["codegen"].append(codegen_task)
            
            # Generate Transform task
            transform_task = self.generate_transform_task(sigil_task)
            if transform_task:
                potential_tasks["transform"].append(transform_task)
            
            # Generate Fix task
            fix_task = self.generate_fix_task(sigil_task)
            if fix_task:
                potential_tasks["fix"].append(fix_task)
            
            # Generate Explain task
            explain_task = self.generate_explain_task(sigil_task)
            if explain_task:
                potential_tasks["explain"].append(explain_task)
        
        # Second pass: select tasks to match target ratios
        if enforce_ratios:
            tasks = self._select_tasks_by_ratio(potential_tasks)
        else:
            # Include all tasks
            tasks = []
            for category_tasks in potential_tasks.values():
                tasks.extend(category_tasks)
        
        # Count final tasks
        counts = {"codegen": 0, "transform": 0, "fix": 0, "explain": 0}
        for task in tasks:
            counts[task.category] += 1
        
        # Write output
        with output_path.open("w", encoding="utf-8") as f:
            for task in tasks:
                f.write(json.dumps(task.to_dict()) + "\n")
        
        return counts
    
    def _select_tasks_by_ratio(
        self,
        potential_tasks: dict[str, list[HumanEvalTask]],
    ) -> list[HumanEvalTask]:
        """
        Select tasks from each category to match target ratios.
        
        The algorithm:
        1. Find the limiting category (one with fewest tasks relative to target)
        2. Calculate total tasks based on that limit
        3. Select proportional tasks from each category
        
        Args:
            potential_tasks: Dictionary of category -> list of tasks
        
        Returns:
            List of selected tasks matching target ratios
        """
        # Calculate how many tasks we can include per category given available tasks
        # The limiting factor is the category with the smallest (available / ratio)
        available = {cat: len(tasks) for cat, tasks in potential_tasks.items()}
        
        # For each category, calculate max total if it were the limiting factor
        max_totals = {}
        for cat, ratio in self.category_ratios.items():
            if ratio > 0 and available.get(cat, 0) > 0:
                # If we use all available tasks from this category,
                # what's the max total we could have?
                max_totals[cat] = available[cat] / ratio
        
        if not max_totals:
            return []
        
        # The actual total is limited by the smallest max_total
        total_tasks = int(min(max_totals.values()))
        
        # Select tasks from each category
        selected: list[HumanEvalTask] = []
        for cat, ratio in self.category_ratios.items():
            target_count = int(total_tasks * ratio)
            category_tasks = potential_tasks.get(cat, [])
            # Take up to target_count tasks (they're already generated, just select)
            selected.extend(category_tasks[:target_count])
        
        return selected


def migrate_existing_task(task_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate an existing HumanEval task to the new schema.
    
    Updates:
    - task_id to content-hash format
    - Adds source field ("humaneval-rust")
    - Adds category/subcategory fields
    - Adds quality metadata fields
    
    Args:
        task_dict: Original task dictionary
    
    Returns:
        Updated task dictionary with new schema
    """
    prompt = task_dict.get("prompt", "")
    
    # Determine category from old task_id
    old_id = task_dict.get("task_id", "")
    if "/" in old_id:
        old_category = old_id.split("/")[0].lower()
    else:
        old_category = "codegen"
    
    # Normalize category
    category_map = {
        "codegen": "codegen",
        "transform": "transform",
        "fix": "fix",
        "explain": "explain",
    }
    category = category_map.get(old_category, "codegen")
    
    # Compute new hash-based ID
    hash_id = compute_task_hash(prompt, category)
    new_task_id = format_task_id(category, hash_id)
    
    # Build updated task
    updated = {
        "task_id": new_task_id,
        "category": category,
        "subcategory": task_dict.get("subcategory", "function_impl"),
        "prompt": prompt,
        "canonical_solution": task_dict.get("canonical_solution", ""),
        "test": task_dict.get("test", ""),
        "entry_point": task_dict.get("entry_point", ""),
        "source": "humaneval-rust",
        "edition": task_dict.get("edition", "2024"),
        "rustfmt_style_edition": task_dict.get("rustfmt_style_edition", "2024"),
        "typechecked": task_dict.get("typechecked", False),
        "clippy_clean": task_dict.get("clippy_clean", False),
        "no_unsafe": task_dict.get("no_unsafe", True),
        "no_unwrap": task_dict.get("no_unwrap", True),
        "quality_level": task_dict.get("quality_level", 0),
        "processed_date": datetime.now(timezone.utc).isoformat(),
    }
    
    # Preserve any additional fields
    for key in ["original_code", "buggy_code", "bug_description", "code_to_explain"]:
        if key in task_dict:
            updated[key] = task_dict[key]
    
    return updated

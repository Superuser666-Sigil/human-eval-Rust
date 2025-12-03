#!/usr/bin/env python3
"""
Migrate HumanEval Rust Task IDs to Content-Hash Format.

This script performs a one-time migration of existing HumanEval_rust.jsonl
to use content-hash based task IDs and adds the new schema fields.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 3.0.0

Usage:
    python scripts/migrate_task_ids.py
    python scripts/migrate_task_ids.py --input data/HumanEval_rust.jsonl
    python scripts/migrate_task_ids.py --dry-run

See ADR-007 for architectural decisions.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from human_eval.sigil_ingest import (  # noqa: E402
    compute_task_hash,
    format_task_id,
    detect_anti_patterns,
)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Migrate HumanEval Rust task IDs to content-hash format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script:
1. Reads the existing HumanEval_rust.jsonl
2. Computes content-hash based task IDs for each task
3. Adds source field ("humaneval-rust") for provenance
4. Adds category, subcategory, and quality metadata fields
5. Writes the updated file in-place (after creating backup)

The old sequential IDs (CodeGen/0, CodeGen/1, etc.) are permanently
replaced with hash-based IDs (CodeGen/a3f8c2e1b4d9, etc.).
        """,
    )
    
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=Path("data/HumanEval_rust.jsonl"),
        help="Path to HumanEval JSONL file to migrate (default: data/HumanEval_rust.jsonl)",
    )
    
    parser.add_argument(
        "--backup",
        type=Path,
        default=None,
        help="Path for backup file (default: <input>.backup.<timestamp>)",
    )
    
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating backup file",
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying files",
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed migration info for each task",
    )
    
    return parser.parse_args()


def infer_subcategory(task: dict) -> str:
    """Infer subcategory from task content."""
    prompt = task.get("prompt", "")
    solution = task.get("canonical_solution", "")
    code = prompt + "\n" + solution
    
    # Check for patterns
    if "async fn" in code or ".await" in code:
        return "async_await"
    if "impl Iterator" in code or ".iter()" in code or ".map(" in code:
        return "iterator_combinator"
    if "Result<" in code or "Option<" in code:
        return "error_handling"
    if "<'" in code:
        return "lifetimes"
    if "<T" in code or "impl<" in code or "where " in code:
        return "generics"
    if "HashMap" in code or "BTreeMap" in code:
        return "collections"
    
    return "function_impl"


def migrate_task(task: dict, verbose: bool = False) -> dict:
    """
    Migrate a single task to the new schema.
    
    Args:
        task: Original task dictionary
        verbose: Whether to print detailed info
    
    Returns:
        Updated task dictionary
    """
    old_id = task.get("task_id", "")
    prompt = task.get("prompt", "")
    solution = task.get("canonical_solution", "")
    
    # Determine category from old ID
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
    new_id = format_task_id(category, hash_id)
    
    # Infer subcategory
    subcategory = task.get("subcategory") or infer_subcategory(task)
    
    # Check for anti-patterns
    anti_patterns = detect_anti_patterns(solution)
    no_unsafe = "unsafe" not in anti_patterns
    no_unwrap = "unwrap" not in anti_patterns and "expect" not in anti_patterns
    
    # Determine quality level based on existing flags
    quality_level = 0
    if task.get("typechecked", False):
        quality_level = 1
    if task.get("clippy_clean", False) and no_unsafe and no_unwrap:
        quality_level = 2
    
    if verbose:
        print(f"  {old_id} -> {new_id}")
        if anti_patterns:
            print(f"    Anti-patterns: {anti_patterns}")
    
    # Build migrated task
    migrated = {
        "task_id": new_id,
        "category": category,
        "subcategory": subcategory,
        "prompt": prompt,
        "canonical_solution": solution,
        "test": task.get("test", ""),
        "entry_point": task.get("entry_point", ""),
        "source": "humaneval-rust",
        "edition": task.get("edition", "2024"),
        "rustfmt_style_edition": task.get("rustfmt_style_edition", "2024"),
        "typechecked": task.get("typechecked", False),
        "clippy_clean": task.get("clippy_clean", False),
        "no_unsafe": no_unsafe,
        "no_unwrap": no_unwrap,
        "quality_level": quality_level,
        "processed_date": datetime.now(timezone.utc).isoformat(),
    }
    
    # Preserve optional fields
    for key in ["original_code", "buggy_code", "bug_description", "code_to_explain"]:
        if key in task:
            migrated[key] = task[key]
    
    return migrated


def main() -> None:
    """Main entry point."""
    args = parse_args()
    
    # Validate input file exists
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
    
    print(f"Migrating: {args.input}")
    
    # Load existing tasks
    tasks = []
    with args.input.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                task = json.loads(line)
                tasks.append(task)
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse line {line_num}: {e}")
    
    print(f"Found {len(tasks)} tasks")
    
    # Track ID mappings for summary
    id_mapping = {}
    
    # Migrate tasks
    if args.verbose:
        print("\nMigrating task IDs:")
    
    migrated_tasks = []
    for task in tasks:
        old_id = task.get("task_id", "")
        migrated = migrate_task(task, verbose=args.verbose)
        migrated_tasks.append(migrated)
        id_mapping[old_id] = migrated["task_id"]
    
    if args.dry_run:
        print("\nDry run - not modifying files")
        print("\nID mapping preview:")
        for old_id, new_id in sorted(id_mapping.items())[:10]:
            print(f"  {old_id} -> {new_id}")
        if len(id_mapping) > 10:
            print(f"  ... and {len(id_mapping) - 10} more")
        
        # Count by category
        categories = {}
        for task in migrated_tasks:
            cat = task["category"]
            categories[cat] = categories.get(cat, 0) + 1
        
        print("\nCategory distribution:")
        for cat, count in sorted(categories.items()):
            print(f"  {cat}: {count}")
        
        # Count quality levels
        quality_levels = {}
        for task in migrated_tasks:
            level = task["quality_level"]
            quality_levels[level] = quality_levels.get(level, 0) + 1
        
        print("\nQuality level distribution:")
        for level in sorted(quality_levels.keys()):
            count = quality_levels[level]
            print(f"  Level {level}: {count}")
        
        return
    
    # Create backup unless disabled
    if not args.no_backup:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = args.backup or args.input.with_suffix(f".jsonl.backup.{timestamp}")
        print(f"\nCreating backup: {backup_path}")
        shutil.copy2(args.input, backup_path)
    
    # Write migrated tasks
    print(f"\nWriting migrated tasks to: {args.input}")
    with args.input.open("w", encoding="utf-8") as f:
        for task in migrated_tasks:
            f.write(json.dumps(task) + "\n")
    
    print("\nMigration complete!")
    print(f"  Tasks migrated: {len(migrated_tasks)}")
    
    # Summary by category
    categories = {}
    for task in migrated_tasks:
        cat = task["category"]
        categories[cat] = categories.get(cat, 0) + 1
    
    print("\nCategory distribution:")
    for cat, count in sorted(categories.items()):
        pct = count / len(migrated_tasks) * 100
        print(f"  {cat}: {count} ({pct:.1f}%)")


if __name__ == "__main__":
    main()

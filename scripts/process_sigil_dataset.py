#!/usr/bin/env python3
"""
Process SigilDERG Pipeline Dataset.

This script ingests data from sigil-pipeline output and transforms it into
HumanEval-compatible benchmark tasks.

Copyright (c) 2025 Dave Tofflemire, SigilDERG Project
Version: 2.4.0

Usage:
    python scripts/process_sigil_dataset.py --input data/sigil_phase2_dataset.jsonl
    python scripts/process_sigil_dataset.py --input data/sigil.jsonl --scaffold-workspace
    python scripts/process_sigil_dataset.py --help

See ADR-007 for architectural decisions.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from human_eval.sigil_ingest import SigilIngestor, CATEGORY_RATIOS
from human_eval.workspace_scaffold import scaffold_workspace


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Process SigilDERG pipeline output into HumanEval benchmark tasks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic ingestion
    python scripts/process_sigil_dataset.py \\
        --input data/sigil_phase2_dataset.jsonl \\
        --output data/HumanEval_rust_sigil.jsonl

    # With workspace scaffolding for hardening
    python scripts/process_sigil_dataset.py \\
        --input data/sigil_phase2_dataset.jsonl \\
        --output data/HumanEval_rust_sigil.jsonl \\
        --scaffold-workspace bench_workspace

    # Custom category ratios
    python scripts/process_sigil_dataset.py \\
        --input data/sigil.jsonl \\
        --category-ratios '{"codegen": 0.5, "transform": 0.2, "fix": 0.2, "explain": 0.1}'
        """,
    )
    
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=Path("data/sigil_phase2_dataset.jsonl"),
        help="Path to sigil-pipeline JSONL input file (default: data/sigil_phase2_dataset.jsonl)",
    )
    
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("data/HumanEval_rust_sigil.jsonl"),
        help="Path for output HumanEval JSONL file (default: data/HumanEval_rust_sigil.jsonl)",
    )
    
    parser.add_argument(
        "--scaffold-workspace",
        type=Path,
        default=None,
        metavar="DIR",
        help="Generate Cargo workspace for hardening validation at specified directory",
    )
    
    parser.add_argument(
        "--category-ratios",
        type=str,
        default=None,
        help="JSON string with category ratios, e.g., '{\"codegen\": 0.45, ...}'",
    )
    
    parser.add_argument(
        "--no-enforce-ratios",
        action="store_true",
        help="Include all generated tasks without enforcing target ratios",
    )
    
    parser.add_argument(
        "--codegen-only",
        action="store_true",
        help="Only generate CodeGen tasks (skip Transform, Fix, Explain)",
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate input without writing output",
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output",
    )
    
    return parser.parse_args()


def load_category_ratios(ratios_str: str | None) -> dict[str, float] | None:
    """Parse category ratios from JSON string."""
    if not ratios_str:
        return None
    
    try:
        ratios = json.loads(ratios_str)
        # Validate keys
        expected_keys = {"codegen", "transform", "fix", "explain"}
        if set(ratios.keys()) != expected_keys:
            print(f"Error: Category ratios must have keys: {expected_keys}")
            sys.exit(1)
        # Validate sum
        total = sum(ratios.values())
        if not (0.99 <= total <= 1.01):
            print(f"Error: Category ratios must sum to 1.0, got {total}")
            sys.exit(1)
        return ratios
    except json.JSONDecodeError as e:
        print(f"Error parsing category ratios: {e}")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    args = parse_args()
    
    # Validate input file exists
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
    
    # Parse category ratios if provided
    category_ratios = load_category_ratios(args.category_ratios)
    
    # Use codegen-only ratios if flag set
    if args.codegen_only:
        category_ratios = {"codegen": 1.0, "transform": 0.0, "fix": 0.0, "explain": 0.0}
    
    if args.verbose:
        print(f"Input file: {args.input}")
        print(f"Output file: {args.output}")
        print(f"Category ratios: {category_ratios or CATEGORY_RATIOS}")
        if args.scaffold_workspace:
            print(f"Workspace directory: {args.scaffold_workspace}")
        print()
    
    # Create ingestor
    ingestor = SigilIngestor(
        category_ratios=category_ratios,
        source="sigil-pipeline",
    )
    
    # Count input tasks
    input_count = 0
    for _ in ingestor.load_sigil_jsonl(args.input):
        input_count += 1
    
    if args.verbose:
        print(f"Found {input_count} tasks in input file")
        print()
    
    if args.dry_run:
        print("Dry run - not writing output")
        # Still process to validate
        counts = {"codegen": 0, "transform": 0, "fix": 0, "explain": 0}
        tasks = []
        
        for sigil_task in ingestor.load_sigil_jsonl(args.input):
            if args.codegen_only:
                task = ingestor.extract_codegen_task(sigil_task)
                if task:
                    counts["codegen"] += 1
                    tasks.append(task)
            else:
                for category, generator in [
                    ("codegen", ingestor.extract_codegen_task),
                    ("transform", ingestor.generate_transform_task),
                    ("fix", ingestor.generate_fix_task),
                    ("explain", ingestor.generate_explain_task),
                ]:
                    task = generator(sigil_task)
                    if task:
                        counts[category] += 1
                        tasks.append(task)
        
        print(f"Would generate {sum(counts.values())} tasks:")
        for cat, count in counts.items():
            pct = (count / sum(counts.values()) * 100) if sum(counts.values()) > 0 else 0
            print(f"  {cat}: {count} ({pct:.1f}%)")
        return
    
    # Process all tasks using ingestor (with ratio enforcement by default)
    print(f"Processing {args.input}...")
    
    enforce_ratios = not args.no_enforce_ratios and not args.codegen_only
    
    if args.codegen_only:
        # Manual processing for codegen-only mode
        tasks = []
        counts = {"codegen": 0, "transform": 0, "fix": 0, "explain": 0}
        
        for sigil_task in ingestor.load_sigil_jsonl(args.input):
            task = ingestor.extract_codegen_task(sigil_task)
            if task:
                counts["codegen"] += 1
                tasks.append(task)
        
        # Write output JSONL
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as f:
            for task in tasks:
                f.write(json.dumps(task.to_dict()) + "\n")
    else:
        # Use process_all with ratio enforcement
        counts = ingestor.process_all(
            args.input,
            args.output,
            enforce_ratios=enforce_ratios,
        )
        
        # Load tasks back for scaffolding if needed
        if args.scaffold_workspace:
            tasks = []
            with args.output.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        tasks.append(json.loads(line))
    
    total = sum(counts.values())
    print(f"\nGenerated {total} tasks:")
    for cat, count in counts.items():
        pct = (count / total * 100) if total > 0 else 0
        print(f"  {cat}: {count} ({pct:.1f}%)")
    
    if enforce_ratios:
        print(f"\nTarget ratios enforced: {category_ratios or CATEGORY_RATIOS}")
    else:
        print("\nRatio enforcement disabled - all generated tasks included")
    
    print(f"\nOutput written to: {args.output}")
    
    # Scaffold workspace if requested
    if args.scaffold_workspace:
        print(f"\nScaffolding workspace at: {args.scaffold_workspace}")
        
        # Load tasks from output file for scaffolding
        task_dicts = []
        with args.output.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    task_dicts.append(json.loads(line))
        
        result = scaffold_workspace(
            tasks=task_dicts,
            output_dir=args.scaffold_workspace,
            overwrite=False,
        )
        
        print(f"  Crates created: {result['crates_created']}")
        print(f"  Crates skipped: {result['crates_skipped']}")
        
        if result["errors"]:
            print(f"  Errors: {len(result['errors'])}")
            for error in result["errors"][:5]:
                print(f"    - {error}")
            if len(result["errors"]) > 5:
                print(f"    ... and {len(result['errors']) - 5} more")
        
        print("\nWorkspace created. Next steps:")
        print(f"  cd {args.scaffold_workspace}")
        print("  cargo fmt")
        print("  cargo check --all --tests")
        print("  cargo clippy --all --tests -- -D warnings -W clippy::pedantic -W clippy::nursery")
        print("  cargo test --all")


if __name__ == "__main__":
    main()

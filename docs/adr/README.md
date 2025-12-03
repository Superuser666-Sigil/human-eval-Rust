# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records (ADRs) for the HumanEval Rust evaluation harness.

## What is an ADR?

An Architecture Decision Record (ADR) is a document that captures an important architectural decision made along with its context and consequences.

## Project Background

HumanEval Rust began as a fork of the original [OpenAI HumanEval](https://github.com/openai/human-eval) benchmark, adapted for the Rust programming language. The project has evolved significantly to meet and exceed the analysis capabilities of the original, with specific enhancements for:

- **Security**: Running untrusted LLM-generated Rust code safely
- **Rust-specific analysis**: Compile rate, Clippy integration, Edition 2021 support
- **Ecosystem integration**: Seamless integration with SigilDERG Pipeline and Finetuner

## ADR Format

Each ADR follows this template:

```markdown
# ADR-NNN: Title

## Status
[Proposed | Accepted | Deprecated | Superseded by ADR-XXX]

## Context
What is the issue that we're seeing that is motivating this decision?

## Decision
What is the change that we're proposing/implementing?

## Consequences
What becomes easier or more difficult as a result of this decision?
```

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](ADR-001-firejail-first-sandboxing.md) | Firejail-First Sandboxing Architecture | Accepted |
| [ADR-002](ADR-002-pattern-based-security.md) | Pattern-Based Security Filtering | Superseded by ADR-011 |
| [ADR-003](ADR-003-thread-safe-timeout.md) | Thread-Safe Timeout Implementation | Accepted |
| [ADR-004](ADR-004-enhanced-result-schema.md) | Enhanced Result Schema for Auditability | Accepted |
| [ADR-005](ADR-005-deterministic-compilation.md) | Deterministic Compilation for Reproducibility | Accepted |
| [ADR-006](ADR-006-unicode-homoglyph-protection.md) | Unicode Homoglyph Attack Prevention | Accepted |
| [ADR-007](ADR-007-sigilderg-pipeline-integration.md) | SigilDERG Pipeline Integration | Accepted |
| [ADR-008](ADR-008-separate-timeout-budgets.md) | Separate Timeout Budgets per Phase | Accepted |
| [ADR-009](ADR-009-clippy-integration-enforcement.md) | Clippy Integration and Enforcement Modes | Accepted |
| [ADR-010](ADR-010-enhanced-dependency-detection.md) | Enhanced Dependency Detection for Workspace Scaffolding | Accepted |
| [ADR-011](ADR-011-context-aware-security-filtering.md) | Security Policy v2 - Context-Aware Filtering | Accepted |
| [ADR-012](ADR-012-windows-path-length-compatibility.md) | Windows Path Length Compatibility | Accepted |

## Creating a New ADR

1. Copy the template from `template.md`
2. Name the file `ADR-NNN-short-title.md`
3. Fill in all sections
4. Add to the index above
5. Submit a PR for review

## Version History Mapping

| Version | Key ADRs Introduced |
|---------|---------------------|
| 1.0.0 | Initial fork from OpenAI HumanEval |
| 1.3.x | ADR-004 (Enhanced Result Schema), ADR-003 (Thread-Safe Timeout) |
| 1.4.x | ADR-002 (Pattern-Based Security), ADR-006 (Unicode Protection) |
| 2.0.0 | ADR-001 (Firejail-First), ADR-005 (Deterministic Compilation) |
| 2.1.0 | Security hardening, comprehensive test suite |
| 2.5.0 | ADR-007 (SigilDERG Integration), ADR-008 (Separate Timeouts), ADR-009 (Clippy Enforcement), ADR-010 (Enhanced Dependencies), ADR-011 (Context-Aware Security), ADR-012 (Windows Path Limits) |


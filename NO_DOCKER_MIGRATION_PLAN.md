# Plan: Remove Docker Dependencies and Enforce Firejail-First Sandbox Flow

## Objectives
- Eliminate all Docker-based sandboxing code, configuration, and documentation from the repository.
- Provide a Firejail-first sandbox strategy with explicit user choice to install Firejail, stop, or proceed with no sandbox only after warnings and surfaced installation failures.
- Preserve functional parity for Rust compilation/execution flows while improving security messaging.

## Current Docker Usage Inventory
- `human_eval/sandbox.py`: Primary sandbox layer; builds Docker image, runs `rustc`/binaries in containers, and currently falls back to Firejail or none.
- `human_eval/evaluation.py`: Pre-builds Docker image when sandbox mode is Docker/auto before parallel workers start.
- `human_eval/rust_execution.py`: Validates `rustc` availability inside Docker and handles Docker-specific sandbox selection errors.
- `human_eval/evaluate_functional_correctness.py`: CLI messaging about Docker vs. Firejail and sandbox selection defaults.
- `Dockerfile.eval`: Docker image definition for evaluator runtime.
- `README.md`: Documents Docker setup, options, and configuration details.

## Target Sandbox Behavior
1. **Detection Order**: Check for Firejail availability first (with explicit version check and usable profile). Do not attempt Docker.
2. **Installation Flow**: If Firejail is missing, present an interactive choice surface (or CLI flag equivalent):
   - Option A: Attempt Firejail installation (shell out to package manager with structured logging of stdout/stderr).
   - Option B: Cancel/exit without evaluation.
   - Option C: Accept no-sandbox mode **only after** showing why Firejail installation is unavailable or failed.
3. **Post-Install Handling**: Re-check Firejail availability after attempted install; only proceed unsandboxed if user explicitly confirms.
4. **Error Reporting**: Capture and display install failure reason (exit code + stderr excerpt) before allowing no-sandbox fallback.
5. **Non-Interactive Mode**: Provide flags/env vars to pre-select behavior (e.g., `--sandbox=firejail|none` plus `--allow-no-sandbox`), failing fast when Firejail is absent and no explicit opt-in to unsafe mode is provided.

## Implementation Steps
1. **Remove Docker Artifacts**
   - Delete `Dockerfile.eval` and prune Docker-specific branches in `human_eval/sandbox.py`, `human_eval/evaluation.py`, and `human_eval/rust_execution.py`.
   - Remove Docker CLI flags/options and documentation references (README, help text in `evaluate_functional_correctness.py`).
2. **Refactor Sandbox Module** (`human_eval/sandbox.py`)
   - Simplify to a Firejail-first implementation: helper to detect Firejail binary/version; structured installer wrapper that returns status + logs; sandbox command builders for compile/run.
   - Add user-choice prompt function (reusable for CLI/non-interactive flag flows) that enforces showing install failure reason before offering no-sandbox.
   - Ensure Firejail parameterization (namespaces, seccomp, memory/CPU caps) mirrors prior security defaults where applicable.
3. **CLI Flow Update** (`human_eval/evaluate_functional_correctness.py`)
   - Replace Docker/auto options with `firejail` and `none` modes; add explicit `--allow-no-sandbox` guard.
   - On Firejail missing: prompt with three choices (install, stop, proceed unsafe) and surface installer errors; exit on cancel when no explicit unsafe opt-in.
4. **Evaluation Pipeline** (`human_eval/evaluation.py` & `human_eval/rust_execution.py`)
   - Remove Docker pre-build and readiness checks; ensure evaluation setup validates Firejail availability (or respects explicit unsafe opt-in) before spawning workers.
   - Update error messages and logging to reflect Firejail-only sandboxing and no-sandbox warnings.
5. **Documentation** (`README.md` and new `docs/sandboxing.md` or section)
   - Remove Docker setup instructions and mention Firejail-first requirement.
   - Document install flow, prompts, non-interactive flags, and security implications of no-sandbox mode.
6. **Testing & Tooling**
   - Add unit tests/mocks for Firejail detection, installer outcomes (success/fail), and user-choice branching.
   - Add integration test harness (if feasible) to simulate Firejail presence/absence via PATH shims.

## Rollout Notes
- Communicate breaking change: Docker support removed; Firejail required unless user explicitly accepts unsafe mode.
- Provide clear upgrade path in release notes and packaging metadata.

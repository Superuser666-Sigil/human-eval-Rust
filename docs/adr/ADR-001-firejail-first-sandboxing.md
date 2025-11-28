# ADR-001: Firejail-First Sandboxing Architecture

## Status

Accepted

## Context

HumanEval Rust executes untrusted, LLM-generated Rust code. The original implementation used Docker containers for sandboxing, which had several issues:

1. **Docker daemon dependency**: Required Docker to be installed and running
2. **Container overhead**: Each evaluation spawned a new container, adding ~2-5 seconds per sample
3. **Complex setup**: Docker-in-Docker for CI/CD was fragile
4. **Windows compatibility**: Limited support for Docker on Windows development environments
5. **Resource consumption**: Container images were large (1GB+) and consumed significant disk space

The evaluation harness needed a sandboxing solution that was:
- Lightweight and fast
- Easy to install across Linux distributions
- Secure enough for untrusted code execution
- Compatible with CI/CD pipelines

## Decision

Adopt **Firejail-first architecture** for sandboxing with explicit fallback modes:

1. **Primary mode**: Firejail with hardened security options
2. **Fallback mode**: No sandboxing (requires explicit user consent)
3. **Interactive flow**: When Firejail unavailable, prompt user to install or accept risk

Key implementation:
- Firejail security options defined in `FIREJAIL_SECURITY_OPTS`
- Auto-detection of Firejail availability via `check_firejail_available()`
- Interactive installation prompt via `prompt_sandbox_choice()`
- Non-interactive mode for CI/CD via `--allow-no-sandbox` flag

Firejail options include:
```
--seccomp              # Restrict syscalls
--caps.drop=all        # Drop all capabilities  
--noroot               # No root in sandbox
--rlimit-fsize=100MB   # File size limit
--rlimit-nproc=50      # Fork bomb prevention
--rlimit-cpu=120       # CPU time limit
--read-only=/          # Read-only root filesystem
--private-tmp          # Private /tmp
--nogroups             # No supplementary groups
--net=none             # No network access
--rlimit-as=4GB        # Memory limit
--whitelist=$HOME/.cargo   # Allow Rust toolchain access
--whitelist=$HOME/.rustup  # Allow rustup installation
```

**Rust Toolchain Access:**

The Firejail configuration uses `--whitelist` instead of `--private` to allow
access to the Rust toolchain while maintaining security. The `--private` flag
creates an isolated home directory, which blocks access to `~/.cargo/bin/rustc`.
The `--whitelist` approach grants read-only access only to the specific directories
required for Rust compilation:

- `$HOME/.cargo` - Cargo binaries, registry cache, and configuration
- `$HOME/.rustup` - Rust toolchain installations and components

Environment variables `CARGO_HOME` and `RUSTUP_HOME` are preserved to ensure
the sandbox can locate the toolchain correctly.

## Consequences

### Positive

- **10x faster startup**: No container overhead, evaluation begins immediately
- **Simpler installation**: Single package install vs Docker + image pulls
- **Smaller footprint**: ~10MB vs 1GB+ Docker images
- **Better CI/CD integration**: Works natively in GitHub Actions Linux runners
- **Interactive UX**: Users understand security implications before proceeding
- **Defense in depth**: Multiple security layers (seccomp, capabilities, resource limits)

### Negative

- **Linux-only sandboxing**: Firejail doesn't work on Windows/macOS
- **Requires sudo for install**: System package manager needed
- **Less isolation than containers**: Shares kernel with host
- **No Windows protection**: Windows users have only pattern-based filtering

### Neutral

- **Docker users must migrate**: `--sandbox-mode=docker` no longer supported
- **Explicit opt-out required**: Can't accidentally run unsandboxed

## Alternatives Considered

### Alternative 1: Keep Docker as Primary

Continue using Docker with performance optimizations.

**Rejected because:**
- Fundamental overhead is unavoidable (container creation)
- Docker daemon requirement is a significant barrier
- Performance improvements were marginal (still 2-3s overhead)

### Alternative 2: bubblewrap (bwrap)

Use bubblewrap for unprivileged sandboxing.

**Rejected because:**
- Less mature than Firejail
- Fewer pre-built security profiles
- Limited distribution availability
- More complex to configure correctly

### Alternative 3: gVisor/Kata Containers

Use lightweight VM-based isolation.

**Rejected because:**
- Overkill for evaluation use case
- Complex setup requirements
- Significant performance overhead
- Limited compatibility

## Related

- [docs/SECURITY.md](../SECURITY.md) - Security policy and threat model
- [human_eval/sandbox.py](../../human_eval/sandbox.py) - Implementation
- Version 2.0.0 release notes - Breaking change documentation


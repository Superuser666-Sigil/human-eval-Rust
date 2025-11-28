# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.1.x   | :white_check_mark: |
| 2.0.x   | :white_check_mark: |
| < 2.0   | :x:                |

We recommend always using the latest version for the best security.

---

## Reporting a Vulnerability

**⚠️ IMPORTANT: Do NOT create public GitHub issues for security vulnerabilities.**

### Preferred Method: GitHub Security Advisories

1. Go to the repository's **Security** tab
2. Click **"Report a vulnerability"**
3. Fill out the form with details about the vulnerability

This ensures the vulnerability is handled privately until a fix is released.

### Alternative: Email

If you cannot use GitHub Security Advisories, contact the maintainer directly. Include:

- **Subject**: `[SECURITY] Brief description`
- **Description**: Detailed explanation of the vulnerability
- **Steps to Reproduce**: How to trigger the vulnerability
- **Impact Assessment**: Potential impact and severity
- **Suggested Fix**: If you have one (optional)

### Response Timeline

| Stage | Timeframe |
|-------|-----------|
| Initial Response | Within 48 hours |
| Vulnerability Confirmation | Within 7 days |
| Patch Development | Varies by severity |
| Security Advisory Published | Upon fix release |

---

## What to Include in Your Report

### Required Information

1. **Vulnerability Type**: (e.g., sandbox escape, pattern bypass, code injection)
2. **Affected Component**: Which module/file is affected
3. **Affected Versions**: Which versions contain the vulnerability
4. **Steps to Reproduce**: Minimal steps to demonstrate the issue
5. **Proof of Concept**: Code or commands (if safe to share)

### Helpful Information

- CVSS score estimate
- CVE references (if known)
- Suggested mitigation
- Whether you want credit in the advisory

---

## Scope

### In Scope

The following are considered valid security concerns:

- **Sandbox escape attempts** (bypassing Firejail isolation)
- **Pattern blocklist bypass** (evading dangerous code detection)
- **Unicode homoglyph attacks** (bypassing pattern matching)
- **Raw string bypass attacks** (hiding patterns in raw strings)
- **Resource exhaustion** (DoS via memory/CPU/process limits)
- **Command injection** (via completion content)
- **Path traversal** (in file operations)
- **Arbitrary code execution** (outside sandbox)
- **Information disclosure** (reading sensitive files/env vars)

### Out of Scope

The following are NOT considered security vulnerabilities:

- Vulnerabilities in dependencies without proof of exploitation
- Issues requiring physical access to the machine
- Social engineering attacks
- Bugs that don't have security implications
- Issues only exploitable with `--sandbox-mode=none` (user accepts risk)
- Issues only exploitable with `--no-enforce-policy` (user accepts risk)

---

## Security Model

### Threat Model

HumanEval Rust executes **untrusted, LLM-generated Rust code**. The security model assumes:

1. **Completions are untrusted**: All model-generated code is potentially malicious
2. **Defense in depth**: Multiple layers of protection are employed
3. **Fail-safe defaults**: Sandboxing is enabled by default
4. **Explicit opt-out**: Users must explicitly disable security features

### Attack Vectors Addressed

| Attack Vector | Mitigation |
|---------------|------------|
| Filesystem access | Pattern blocklist + Firejail `--whitelist` (limited to Rust toolchain) |
| Network access | Pattern blocklist + Firejail `--net=none` |
| Process execution | Pattern blocklist + Firejail `--noroot` |
| Environment access | Pattern blocklist + Firejail isolation |
| Unsafe Rust code | Pattern blocklist for `unsafe` keyword |
| FFI/linking | Pattern blocklist for `extern`, `#[link]` |
| Compile-time execution | Pattern blocklist for `include!`, `env!`, `asm!` |
| Fork bombs | Firejail `--rlimit-nproc=50` |
| Memory exhaustion | Firejail `--rlimit-as=4GB` |
| CPU exhaustion | Firejail `--rlimit-cpu=120` |
| File size attacks | Firejail `--rlimit-fsize=100MB` |
| Unicode homoglyphs | NFKD normalization before matching |
| Raw string bypass | Regex detection of patterns in raw strings |

### Firejail Security Options

The following Firejail options are applied to all sandboxed executions:

```text
--seccomp              # Restrict syscalls
--caps.drop=all        # Drop all capabilities
--noroot               # No root in sandbox
--rlimit-fsize=100MB   # File size limit
--rlimit-nproc=50      # Process limit (fork bomb prevention)
--rlimit-cpu=120       # CPU time limit (seconds)
--read-only=/          # Read-only root filesystem
--private-tmp          # Private /tmp directory
--nogroups             # Disable supplementary groups
--net=none             # No network access
--rlimit-as=4GB        # Memory limit
--whitelist=$HOME/.cargo   # Allow Rust toolchain access
--whitelist=$HOME/.rustup  # Allow rustup installation
```

**Rust Toolchain Whitelisting:**

Instead of using `--private` (which creates an isolated home directory and blocks access to `~/.cargo/bin/rustc`), the sandbox uses `--whitelist` to grant read-only access to specific directories:

- `$HOME/.cargo` - Cargo binaries, registry cache, and configuration
- `$HOME/.rustup` - Rust toolchain installations and components

This approach maintains strong isolation while allowing the Rust compiler and related tools to function correctly within the sandbox. Environment variables `CARGO_HOME` and `RUSTUP_HOME` are preserved to ensure proper toolchain location.

### Pattern Blocklist

The following patterns are blocked in completions:

#### Filesystem Operations

- `std::fs`, `std::path`, file I/O operations

#### Process Operations

- `std::process`, `Command`, process spawning

#### Network Operations

- `std::net`, `tokio::net`, `reqwest`, `hyper`

#### Threading/Concurrency

- `std::thread`, `std::sync`, `tokio::spawn`

#### Unsafe Code

- `unsafe`, `std::ptr`, `std::mem::transmute`

#### FFI/External Code

- `extern`, `libc`, `winapi`, `#[link]`, `#[no_mangle]`

#### Compile-time Execution

- `include!`, `include_str!`, `include_bytes!`
- `env!`, `option_env!`
- `asm!`, `global_asm!`
- `proc_macro`, `#[derive(`

#### Intrinsics

- `std::intrinsics`, `core::intrinsics`

### Known Limitations

1. **Firejail availability**: Firejail must be installed for sandbox protection
2. **Linux-only sandbox**: Firejail is Linux-only; Windows users have reduced protection
3. **Pattern matching**: Substring matching may have false positives/negatives
4. **Compile-time attacks**: Some attacks may occur during `rustc` compilation
5. **Clippy execution**: Clippy runs outside the sandbox (requires cargo project)

---

## Security Best Practices

### For Users

1. **Always use Firejail** when evaluating untrusted code
2. **Never use `--sandbox-mode=none`** with untrusted completions
3. **Keep dependencies updated** for security patches
4. **Review completions** before evaluation if possible
5. **Use `--enforce-policy`** (default) for additional filtering

### For Contributors

1. **Never log secrets** - Avoid logging API keys, tokens, or credentials
2. **Validate all inputs** - Especially paths, completions, and configuration
3. **Avoid shell injection** - Use list-based subprocess calls
4. **Handle errors safely** - Don't expose internal details in error messages
5. **Add tests** - Include security-focused tests for new features

---

## Vulnerability Disclosure Process

### Timeline

1. **Day 0**: Vulnerability reported
2. **Day 1-2**: Initial triage and acknowledgment
3. **Day 3-7**: Vulnerability confirmed and assessed
4. **Day 7-30**: Patch developed and tested
5. **Day 30-45**: Coordinated disclosure with reporter
6. **Day 45+**: Public advisory and fix release

### Severity Classifications

| Severity | Response Time | Description |
|----------|---------------|-------------|
| Critical | 24-48 hours | Sandbox escape, arbitrary code execution |
| High | 72 hours | Pattern bypass, significant information disclosure |
| Medium | 7 days | Limited impact vulnerabilities |
| Low | 30 days | Minimal impact, defense in depth |

---

## Safe Harbor

We consider security research conducted in good faith to be authorized and will not pursue legal action against researchers who:

1. **Act in good faith** - Make reasonable efforts to avoid privacy violations, data destruction, and service disruption
2. **Report promptly** - Submit findings through the proper channels
3. **Allow reasonable time** - Give us time to respond before public disclosure
4. **Don't exploit** - Don't use the vulnerability beyond proof of concept

---

## Security Updates

Security advisories are published through:

1. **GitHub Security Advisories** - Primary notification channel
2. **Release Notes** - Mentioned in CHANGELOG
3. **PyPI** - New version with security fix

To receive notifications, **Watch** the repository and enable security alerts.

---

## Contact

- **GitHub Security Advisories**: Preferred method
- **Maintainer**: Dave Tofflemire (@Superuser666-Sigil)

---

## Acknowledgments

We appreciate responsible disclosure and will acknowledge security researchers in our advisories (unless they prefer to remain anonymous).

### Hall of Fame

*Contributors who have helped improve our security will be listed here.*

---

Thank you for helping keep HumanEval Rust secure! 🔒

# ADR-002: Pattern-Based Security Filtering

## Status

Superseded by [ADR-011](ADR-011-context-aware-security-filtering.md) (v2: context-aware filtering)

## Context

LLM-generated Rust code may contain dangerous patterns that could:

1. **Access filesystem**: Read sensitive files (`/etc/passwd`, SSH keys)
2. **Execute processes**: Run arbitrary commands (`rm -rf /`, crypto miners)
3. **Access network**: Exfiltrate data, connect to C&C servers
4. **Use unsafe code**: Exploit memory safety vulnerabilities
5. **Use FFI**: Call native libraries, bypass Rust safety

Even with Firejail sandboxing, defense-in-depth requires blocking dangerous code **before** it reaches the compiler. Compile-time macros like `include!()` and `env!()` execute during compilation, bypassing runtime sandboxing.

## Decision

Implement a **pattern-based security filter** that scans completions for dangerous patterns before compilation:

1. **Blocklist approach**: Define patterns that are always dangerous
2. **Pre-compilation filtering**: Block before `rustc` is invoked
3. **Optional enforcement**: `--enforce-policy` (default) vs `--no-enforce-policy`
4. **Informative errors**: Tell user which pattern was blocked

Blocked pattern categories:

**Filesystem Operations**
- `std::fs`, `std::path`, file I/O

**Process Operations**
- `std::process`, `Command`, process spawning

**Network Operations**  
- `std::net`, `tokio::net`, HTTP libraries

**Unsafe Code**
- `unsafe`, `std::ptr`, `std::mem::transmute`

**FFI/External Code**
- `extern`, `libc`, `#[link]`, `#[no_mangle]`

**Compile-time Execution**
- `include!`, `include_str!`, `include_bytes!`
- `env!`, `option_env!`
- `asm!`, `global_asm!`
- `proc_macro`

**Intrinsics**
- `std::intrinsics`, `core::intrinsics`

Implementation in `_sanitize_rust_completion()`:
```python
for pattern in DISALLOWED_COMPLETION_PATTERNS:
    if pattern.lower() in normalized:
        return f"disallowed usage of {pattern}"
```

## Consequences

### Positive

- **Defense in depth**: Catches dangerous code before it runs
- **Fast rejection**: Milliseconds vs seconds for compilation
- **Blocks compile-time attacks**: `include!()`, `env!()` can't run
- **Audit trail**: Results show exactly why code was blocked
- **HumanEval compatibility**: Can disable for research comparisons

### Negative

- **False positives possible**: Safe uses of patterns blocked
- **Not AST-aware**: Substring matching may have edge cases
- **Maintenance burden**: New patterns must be added manually
- **Bypassable**: Determined attackers may find gaps

### Neutral

- **Two modes available**: Security mode vs pure HumanEval mode
- **Pattern list is visible**: Users can review in `rust_execution.py`

## Alternatives Considered

### Alternative 1: AST-Based Filtering

Parse Rust code and analyze the AST for dangerous constructs.

**Rejected because:**
- Requires Rust parser in Python (tree-sitter-rust or syn binding)
- Significant complexity increase
- Performance overhead for parsing
- Pattern matching catches most cases adequately

### Alternative 2: Capability-Based Allow List

Only allow specific safe standard library functions.

**Rejected because:**
- Would break most legitimate HumanEval solutions
- Too restrictive for practical use
- Maintenance nightmare to keep updated

### Alternative 3: Sandbox-Only Security

Rely entirely on Firejail without pattern filtering.

**Rejected because:**
- Compile-time macros bypass runtime sandboxing
- More expensive to block at runtime vs pre-filter
- Less informative error messages

## Related

- [ADR-001](ADR-001-firejail-first-sandboxing.md) - Primary sandboxing mechanism
- [ADR-006](ADR-006-unicode-homoglyph-protection.md) - Unicode bypass prevention
- [ADR-011](ADR-011-context-aware-security-filtering.md) - **Successor: Context-aware filtering v2**
- [human_eval/rust_execution.py](../../human_eval/rust_execution.py) - Implementation


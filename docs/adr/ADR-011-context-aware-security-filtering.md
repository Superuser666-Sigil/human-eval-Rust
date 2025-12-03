# ADR-011: Security Policy v2 - Context-Aware Filtering

## Status

Accepted

## Context

The pattern-based security filter (ADR-002) uses regex to detect dangerous Rust patterns like raw pointers, inline assembly, and FFI:

```python
DISALLOWED_COMPLETION_PATTERNS = [
    r"\bunsafe\s+(fn|trait|impl)",
    r"\*\s*(const|mut)\s+[a-zA-Z_]",
    r"asm!",
    r"std::intrinsics",
    r"std::ptr::(read|write)",
    r"\bextern\s+\"C\"",
    # ... 20+ patterns
]
```

**Problem: False Positives from Documentation and Strings**

Code frequently contains these patterns in benign contexts:

```rust
/// This function is safe because it doesn't use `unsafe` blocks.
/// We avoid raw pointers like `*const T` by using references.
fn safe_sum(values: &[i32]) -> i32 {
    let warning = "Do not use asm! in production";
    values.iter().sum()
}
```

**Impact:**

- **Legitimate code rejected**: Doc comments trigger false positives
- **String literals flagged**: Error messages and logging rejected
- **Poor user experience**: "Why is my safe code blocked?"
- **Security theater**: Filter appears strict but doesn't understand context
- **Over-filtering**: `#[derive(Debug)]` originally blocked (way too strict)

Real examples that failed incorrectly:
- `/// Returns a pointer` in documentation → flagged by pointer pattern
- `log::warn!("unsafe operation detected")` → flagged by unsafe pattern
- Educational code explaining what NOT to do → flagged

## Decision

Implement **context-aware filtering** by stripping comments and strings before pattern matching:

### 1. Strip Comments and Strings

```python
def _strip_comments_and_strings(code: str) -> str:
    """Remove comments and string literals to avoid false positives."""
    result = []
    in_string = False
    in_comment = False
    escape_next = False
    i = 0
    
    while i < len(code):
        c = code[i]
        
        # Handle escape sequences in strings
        if in_string and escape_next:
            result.append(' ')  # Preserve position
            escape_next = False
            i += 1
            continue
        
        # String literals
        if c == '"' and not in_comment:
            if in_string:
                in_string = False
            else:
                in_string = True
            result.append(' ')
            i += 1
            continue
        
        if in_string:
            if c == '\\':
                escape_next = True
            result.append(' ')
            i += 1
            continue
        
        # Line comments
        if not in_comment and i + 1 < len(code) and code[i:i+2] == '//':
            in_comment = True
            result.append(' ')
            result.append(' ')
            i += 2
            continue
        
        if in_comment:
            if c == '\n':
                in_comment = False
                result.append('\n')  # Preserve line structure
            else:
                result.append(' ')
            i += 1
            continue
        
        # Keep actual code
        result.append(c)
        i += 1
    
    return ''.join(result)
```

**Key properties:**

- **Preserves structure**: Line numbers and column positions maintained
- **Simple state machine**: Handles strings, line comments, escapes
- **No block comments**: `/* ... */` not handled (rare in Rust 2024, complex to parse)
- **Whitespace replacement**: Stripped content becomes spaces (keeps positions)

### 2. Apply Patterns to Stripped Code

```python
def _sanitize_rust_completion(completion: str, ...) -> str:
    # Strip context before checking
    stripped = _strip_comments_and_strings(completion)
    
    for pattern in DISALLOWED_COMPLETION_PATTERNS:
        if re.search(pattern, stripped):
            raise ValueError(f"Disallowed pattern: {pattern}")
    
    # Check original code for derives (need attributes intact)
    if has_unsafe_derives(completion):
        raise ValueError("Unsafe derive macros detected")
    
    return completion
```

### 3. Relax Over-Strict Filters

**Allow safe derives:**
```python
SAFE_DERIVE_MACROS = {
    "Debug", "Clone", "Copy", "PartialEq", "Eq",
    "PartialOrd", "Ord", "Hash", "Default",
    "Serialize", "Deserialize"
}

def has_unsafe_derives(code: str) -> bool:
    derive_pattern = r'#\[derive\([^)]*\b(Arbitrary|Unaligned|TryFromPrimitive)\b'
    return re.search(derive_pattern, code) is not None
```

**Allow std::time::Instant:**
```python
# Remove overly restrictive std::time ban
# std::time::Instant is safe for benchmarking
DISALLOWED_COMPLETION_PATTERNS = [
    # r"std::time::",  # REMOVED - too strict
    r"std::time::SystemTime::now",  # Still block (side effect)
]
```

## Consequences

### Positive

- **Fewer false positives**: Doc comments and strings don't trigger filters
- **Better UX**: Safe code with explanatory comments allowed
- **More permissive**: std::time::Instant for benchmarking allowed
- **Still secure**: Actual code patterns still checked
- **Maintainable**: Stripping logic is simple, testable

### Negative

- **Not perfect**: Block comments `/* */` not handled (rare edge case)
- **Raw strings missed**: `r#"..."#` not fully handled (complex parsing)
- **Performance**: Extra pass over code (negligible in practice)

### Neutral

- **Conservative relaxation**: Only obviously-safe patterns allowed
- **Layered defense**: Security filter is one layer, sandboxing is primary
- **Evolving policy**: Can adjust SAFE_DERIVE_MACROS as needed

## Example Usage

**Before (false positive):**
```python
code = '''
/// This function avoids `unsafe` code by using safe abstractions.
/// We don't use raw pointers like `*const T`.
fn safe_process(data: &[u8]) -> Vec<u8> {
    data.to_vec()
}
'''
_sanitize_rust_completion(code)  # REJECTED: "unsafe" in comment
```

**After (correctly allowed):**
```python
code = '''
/// This function avoids `unsafe` code by using safe abstractions.
/// We don't use raw pointers like `*const T`.
fn safe_process(data: &[u8]) -> Vec<u8> {
    data.to_vec()
}
'''
stripped = _strip_comments_and_strings(code)
# stripped = "\n\n\nfn safe_process(data: &[u8]) -> Vec<u8> {\n    data.to_vec()\n}"
_sanitize_rust_completion(code)  # ALLOWED: no patterns in actual code
```

**Actual unsafe code still blocked:**
```python
code = '''
fn hack() {
    unsafe { std::ptr::write(ptr, value); }
}
'''
_sanitize_rust_completion(code)  # REJECTED: actual unsafe code
```

**Safe derives allowed:**
```python
code = '''
#[derive(Debug, Clone, Serialize)]
struct Point { x: i32, y: i32 }
'''
_sanitize_rust_completion(code)  # ALLOWED: safe derives
```

## Alternatives Considered

### Alternative 1: AST-Based Analysis

Parse Rust code with `syn` crate, analyze AST for unsafe constructs.

**Rejected because:**
- **Heavy dependency**: Requires Rust compiler/parser integration
- **Complexity**: Must handle all Rust syntax edge cases
- **Maintenance**: Must update with every Rust edition
- **Overkill**: Pattern matching is fast and good enough

### Alternative 2: Allowlist Known-Safe Patterns

Maintain list of approved code patterns, reject everything else.

**Rejected because:**
- **Impossible to maintain**: Infinite valid Rust code
- **Brittle**: Every new idiom requires allowlist update
- **User frustration**: "Why is my normal code blocked?"

### Alternative 3: Remove Security Filter

Rely solely on sandboxing (Firejail).

**Rejected because:**
- **Defense in depth**: Multiple layers better than one
- **Resource attacks**: Sandbox doesn't prevent infinite loops
- **Policy enforcement**: Some environments ban certain patterns
- **Visibility**: Security filter gives early feedback

### Alternative 4: Comment Annotations

Require users to annotate safe code: `// @safe-override: explaining unsafe`

**Rejected because:**
- **User burden**: Extra work for every false positive
- **Inconsistent**: Some users won't know about annotations
- **Fragile**: Typos in annotations cause rejections

## Migration Notes

**For researchers:**
- No action needed
- Code with explanatory comments now works
- Can use `#[derive(Debug)]` and similar safe derives
- Can use `std::time::Instant` for benchmarking

**For task authors:**
- Add documentation comments freely
- Use string literals with formerly-filtered words
- Test with sanitizer to verify

**For security teams:**
- Review SAFE_DERIVE_MACROS list if needed
- Consider adding more safe std::time patterns
- Block comment handling could be future enhancement

**For implementers:**
- `_strip_comments_and_strings()` called before pattern matching
- `has_unsafe_derives()` checks original code (needs attributes)
- Test coverage includes comment/string edge cases

## Related

- [ADR-002](ADR-002-pattern-based-security.md) - Original pattern-based filtering
- [ADR-001](ADR-001-firejail-first-sandboxing.md) - Sandboxing provides primary defense
- [rust_execution.py](../../human_eval/rust_execution.py) - Implementation
- [tests/test_security.py](../../tests/test_security.py) - Test coverage

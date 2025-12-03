# ADR-010: Enhanced Dependency Detection for Workspace Scaffolding

## Status

Accepted

## Context

The workspace scaffolding system (Rust 2024 hardening pipeline) generates proper `Cargo.toml` manifests with dependency declarations. It analyzes function bodies to detect which external crates are needed.

**Original detection logic:**

```python
def analyze_dependencies(code_completion: str) -> Set[str]:
    dependencies = set()
    
    # Use statements: "use serde_json::Value;"
    use_pattern = r'\buse\s+([a-z][a-z0-9_]*)::'
    for match in re.finditer(use_pattern, code_completion):
        dependencies.add(match.group(1))
    
    return dependencies
```

**Problem: Missed fully-qualified paths**

Code often uses crates without `use` statements:

```rust
fn parse_data(json_str: &str) -> Result<Value, Error> {
    // No "use serde_json;" anywhere!
    let data = serde_json::from_str(json_str)?;
    Ok(data)
}
```

**Impact:**

- **Compilation failures**: Missing `serde_json = "1.0"` in Cargo.toml
- **Silent degradation**: Tasks marked as failed due to infra issues
- **Poor user experience**: "Why doesn't my code work? It compiles locally!"
- **False negatives**: Dependency detection claimed 0 deps when code needed several

This was especially common in:
- JSON parsing: `serde_json::from_str`
- HTTP clients: `reqwest::get`
- Datetime: `chrono::Utc::now`
- Regular expressions: `regex::Regex::new`

## Decision

Add **qualified path detection** to complement use-statement detection:

```python
def analyze_dependencies(code_completion: str) -> Set[str]:
    dependencies = set()
    
    # Original: use statements
    use_pattern = r'\buse\s+([a-z][a-z0-9_]*)::'
    for match in re.finditer(use_pattern, code_completion):
        dependencies.add(match.group(1))
    
    # NEW: Fully-qualified paths
    qualified_path_pattern = r'\b([a-z][a-z0-9_]*)::[a-zA-Z_]'
    for match in re.finditer(qualified_path_pattern, code_completion):
        crate_name = match.group(1)
        # Exclude std library (always available)
        if crate_name not in ('std', 'core', 'alloc'):
            dependencies.add(crate_name)
    
    return dependencies
```

**Pattern breakdown:**

- `\b([a-z][a-z0-9_]*)` - Crate name (lowercase start, alphanumeric/underscore)
- `::` - Path separator
- `[a-zA-Z_]` - Start of next segment (module, type, or function)

**Example matches:**

| Code | Detected Crate |
|------|---------------|
| `serde_json::from_str(s)` | `serde_json` |
| `reqwest::get(url).await` | `reqwest` |
| `chrono::Utc::now()` | `chrono` |
| `regex::Regex::new(r"\d+")` | `regex` |
| `std::time::Instant::now()` | *(excluded - std lib)* |

## Consequences

### Positive

- **Catches common pattern**: Fully-qualified calls now detected
- **Fewer infra failures**: Cargo.toml more likely to be complete
- **Better scaffolding**: Generated workspaces closer to what users expect
- **Complementary**: Works alongside use-statement detection
- **Low false positives**: Pattern is conservative (crate names must start lowercase)

### Negative

- **Not exhaustive**: Doesn't catch `use crate_name;` (aliasing)
- **Macro edge cases**: May miss procedural macros or derive macros
- **False positives possible**: Custom module paths like `my_mod::Type` detected (rare)

### Neutral

- **Regex-based**: Simple, fast, no parsing required
- **Order independent**: Both patterns checked, order doesn't matter
- **Duplicates handled**: Returns `Set[str]`, natural deduplication

## Example Usage

**Before (missed qualified paths):**
```python
code = 'let v = serde_json::from_str(s)?;'
deps = analyze_dependencies(code)  # => set()  (MISSED!)
```

**After (caught by qualified path pattern):**
```python
code = 'let v = serde_json::from_str(s)?;'
deps = analyze_dependencies(code)  # => {'serde_json'}
```

**Combined detection:**
```python
code = '''
use chrono::DateTime;

fn parse() {
    let now = chrono::Utc::now();  // Qualified path
    let dt: DateTime<Utc> = ...;    // From use statement
    let val = serde_json::from_str(s)?;  // No use statement
}
'''
deps = analyze_dependencies(code)  # => {'chrono', 'serde_json'}
```

**Std library correctly excluded:**
```python
code = 'let now = std::time::Instant::now();'
deps = analyze_dependencies(code)  # => set()  (std is built-in)
```

## Alternatives Considered

### Alternative 1: Full Rust Parser

Use `syn` crate or `tree-sitter-rust` to parse AST.

**Rejected because:**
- **Heavy dependency**: Requires Rust toolchain or complex bindings
- **Compilation overhead**: Must compile/invoke external tool
- **Overkill**: We only need crate names, not full semantic analysis
- **Fragile**: Parser must match exact Rust version/edition

### Alternative 2: Manifest Querying

Parse existing Cargo.toml for dependencies, don't analyze code.

**Rejected because:**
- **Circular logic**: We're generating the Cargo.toml!
- **Manual curation**: Tasks would need pre-specified dependencies
- **Less flexible**: Can't handle new/unknown crates

### Alternative 3: Heuristic Lists

Maintain allowlist of common crates (serde, tokio, etc.).

**Rejected because:**
- **High maintenance**: Must update as ecosystem evolves
- **Brittle**: Misses legitimate new crates
- **False sense of security**: Code using unlisted crates still fails

### Alternative 4: Runtime Detection

Attempt compilation, parse error messages for missing crates.

**Rejected because:**
- **Slow**: Multiple compile attempts per task
- **Unreliable**: Error messages vary by Rust version
- **Wastes timeout budget**: Uses precious compilation time

## Migration Notes

**For task authors:**
- No action needed
- Both use-statements and qualified paths detected automatically
- Can use either style (or both) freely

**For evaluators:**
- Update task dependency metadata if relying on old detection
- Check if previously-failed tasks now succeed (better scaffolding)

**For implementers:**
- `analyze_dependencies()` in workspace_scaffold.py enhanced
- `_get_task_dependencies()` also uses both patterns
- Test coverage includes qualified path examples

## Related

- [ADR-001](ADR-001-firejail-first-sandboxing.md) - Workspace scaffolding security context
- [ADR-005](ADR-005-deterministic-compilation.md) - Cargo.toml generation process
- [workspace_scaffold.py](../../human_eval/workspace_scaffold.py) - Implementation
- Rust 2024 Edition: https://doc.rust-lang.org/edition-guide/rust-2024/

# ADR-012: Windows Path Length Compatibility

## Status

Accepted

## Context

Windows has a historical path length limit (MAX_PATH) of 260 characters. While modern Windows 10+ can handle longer paths with registry changes, the default remains 260.

**Problem: Task IDs Can Be Very Long**

HumanEval task IDs and crate names can be verbose:

```python
task_id = "HumanEval_rust/123_advanced_tokenization_with_unicode_normalization"
crate_name = "humaneval_rust_123_advanced_tokenization_with_unicode_normalization"

workspace_path = "/tmp/eval/humaneval_rust_123_advanced_tokenization_with_unicode_normalization/src/main.rs"
# Total: 100+ chars just for the crate name portion
```

When combined with:
- Temp directory prefix: `/tmp/eval_1234567890/`
- Nested structure: `/src/`, `/target/debug/`, `/deps/`
- Build artifacts: `libhumaneval_rust_123_advanced_tokenization_with_unicode_normalization.rlib`

**Actual failures observed:**

- Cargo build errors: "filename too long"
- File creation failures on Windows CI
- Intermittent issues in Docker (depends on mount path)
- User reports from Windows developers

**Example overflow:**

```
C:\Users\researcher\Documents\Projects\human-eval-rust\temp\
  humaneval_rust_123_advanced_tokenization_with_unicode_normalization\
  target\debug\deps\
  humaneval_rust_123_advanced_tokenization_with_unicode_normalization-abc123def456.exe
                                                                                      ^^^^ OVERFLOW
```

Total: 280+ characters → exceeds MAX_PATH

## Decision

Implement **path length limits** with **hash-based uniqueness guarantees**:

### 1. Limit Generated Names to 240 Characters

```python
def sanitize_crate_name(task_id: str) -> str:
    # Convert to valid crate name
    crate_name = re.sub(r'[^a-z0-9_]', '_', task_id.lower())
    crate_name = re.sub(r'_+', '_', crate_name).strip('_')
    
    # NEW: Enforce length limit with hash suffix
    if len(crate_name) > 240:
        # Hash full name for uniqueness
        full_hash = hashlib.sha256(task_id.encode()).hexdigest()[:16]
        # Truncate + append hash
        crate_name = f"{crate_name[:223]}_{full_hash}"
    
    return crate_name
```

**Why 240 chars?**

- Windows MAX_PATH: 260 chars
- Reserve 20 chars for:
  - Path separators: `/`, `\`
  - File extensions: `.rs`, `.rlib`, `.exe`
  - Cargo suffixes: `-abc123def456`
  - Buffer for nested paths: `/src/`, `/target/debug/deps/`

**Hash suffix ensures:**
- **Uniqueness**: Different task IDs → different hashes
- **Collision resistance**: SHA256 → negligible collision probability
- **Debuggability**: First 223 chars still human-readable
- **Determinism**: Same task ID → same crate name

### 2. Apply to Directory Names

```python
def sanitize_dir_name(name: str) -> str:
    # Same logic as crate names
    dir_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
    
    if len(dir_name) > 240:
        full_hash = hashlib.sha256(name.encode()).hexdigest()[:16]
        dir_name = f"{dir_name[:223]}_{full_hash}"
    
    return dir_name
```

### 3. Example Transformations

| Original Task ID | Length | Sanitized Crate Name | Length |
|-----------------|--------|---------------------|--------|
| `HumanEval_rust/1` | 17 | `humaneval_rust_1` | 17 |
| `HumanEval_rust/123_tokenization` | 33 | `humaneval_rust_123_tokenization` | 33 |
| `HumanEval_rust/999_extremely_long_task_name_that_describes_complex_unicode_normalization_with_nfc_nfd_nfkc_nfkd_forms_and_grapheme_cluster_segmentation_plus_bidirectional_text_handling_and_emoji_variation_selectors_and_zero_width_joiners` | 250 | `humaneval_rust_999_extremely_long_task_name_that_describes_complex_unicode_normalization_with_nfc_nfd_nfkc_nfkd_forms_and_grapheme_cluster_segmentation_plus_bidirectional_text_handling_and_emoji_variation_selectors_and_zero_width_j_a1b2c3d4e5f6g7h8` | 240 |

## Consequences

### Positive

- **Windows compatible**: Works on default Windows configurations
- **No user action required**: Automatically handled during scaffolding
- **Unique names preserved**: Hash suffix prevents collisions
- **Debuggable**: Human-readable prefix retained
- **Cross-platform**: Works on Linux, macOS, Windows, Docker

### Negative

- **Less readable for very long names**: Truncated + hash less intuitive
- **Hash adds complexity**: Debugging requires understanding hash suffix
- **Not reversible**: Can't reconstruct original task ID from sanitized name alone

### Neutral

- **Conservative limit**: 240 chars leaves plenty of room for paths
- **Could be configurable**: Environment variable for custom limit (future)
- **Applies at generation time**: Existing workspaces unaffected

## Example Usage

**Short task ID (no change):**
```python
task_id = "HumanEval_rust/1"
crate_name = sanitize_crate_name(task_id)
# => "humaneval_rust_1" (17 chars)
```

**Long task ID (truncated + hash):**
```python
task_id = "HumanEval_rust/999_extremely_long_task_name_that_describes_complex_unicode_normalization_with_nfc_nfd_nfkc_nfkd_forms_and_grapheme_cluster_segmentation_plus_bidirectional_text_handling"
crate_name = sanitize_crate_name(task_id)
# => "humaneval_rust_999_extremely_long_task_name_that_describes_complex_unicode_normalization_with_nfc_nfd_nfkc_nfkd_forms_and_grapheme_cluster_segmentation_plus_bidirectional_text_handling_and_e_a1b2c3d4e5f6g7h8"
# (240 chars: 223 prefix + 1 underscore + 16 hex hash)
```

**Uniqueness guaranteed:**
```python
task_id_1 = "A" * 300
task_id_2 = "B" * 300

crate_1 = sanitize_crate_name(task_id_1)
crate_2 = sanitize_crate_name(task_id_2)

assert crate_1 != crate_2  # Different hashes ensure uniqueness
```

## Alternatives Considered

### Alternative 1: Enable Long Paths on Windows

Require users to enable long path support via registry/Group Policy.

**Rejected because:**
- **User burden**: Requires admin privileges and system changes
- **Inconsistent**: Not enabled by default, varies by environment
- **Enterprise blockers**: Many corporate Windows environments lock settings
- **CI/CD pain**: Each Windows runner needs configuration

### Alternative 2: Flat Directory Structure

Don't nest by task ID, use flat temp directory with random IDs.

**Rejected because:**
- **Loss of context**: Can't identify workspace from task ID
- **Debugging harder**: Random IDs don't map to tasks
- **Cleanup complexity**: Can't easily find workspaces for specific tasks

### Alternative 3: Compress Task IDs

Use URL-safe base64 encoding to compress task IDs.

**Rejected because:**
- **Not human-readable**: `SGVsbG9Xb3JsZA==` vs `hello_world`
- **Debugging nightmare**: Must decode to understand
- **Character issues**: Base64 has special chars (`+`, `/`, `=`)
- **Not much shorter**: Only ~25% compression for ASCII

### Alternative 4: UUID-Only Names

Generate random UUIDs for all workspaces, store mapping separately.

**Rejected because:**
- **Requires state**: Mapping file or database needed
- **Cleanup complexity**: Orphaned workspaces harder to identify
- **No context in logs**: `workspace_a1b2c3d4` tells you nothing
- **Distributed evaluation**: Mapping must be shared across workers

## Migration Notes

**For users:**
- No action needed
- Workspaces with long names automatically truncated
- Hash suffixes appear in paths for very long task IDs
- Logs may show truncated names (first 223 chars + hash)

**For CI/CD:**
- Windows builds now succeed with long task IDs
- No special configuration required
- Paths under 260 chars guaranteed

**For implementers:**
- `sanitize_crate_name()` in workspace_scaffold.py enforces limit
- `sanitize_dir_name()` applies same logic to directories
- SHA256 hash provides uniqueness guarantee
- Import `hashlib` module required

**For debuggers:**
- Truncated names: look at first 223 chars + 16-char hex hash
- Find original task ID in logs or dataset (hash not reversible)
- Consider adding `task_id` to result metadata for traceability

## Related

- [ADR-005](ADR-005-deterministic-compilation.md) - Workspace scaffolding process
- [workspace_scaffold.py](../../human_eval/workspace_scaffold.py) - Implementation
- Windows MAX_PATH documentation: https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation
- Python pathlib: https://docs.python.org/3/library/pathlib.html

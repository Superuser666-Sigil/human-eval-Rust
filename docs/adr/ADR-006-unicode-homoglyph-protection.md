# ADR-006: Unicode Homoglyph Attack Prevention

## Status

Accepted

## Context

Unicode contains characters that visually resemble ASCII characters but have different code points. Attackers can use these "homoglyphs" to bypass pattern-based security filters:

**Examples:**
- `stᴅ::fs` (ᴅ = Latin Small Letter D, U+1D05)
- `unsaꜰe` (ꜰ = Latin Letter Small Capital F, U+A730)
- `stᴅ::ᴘrocess` (ᴅ = U+1D05, ᴘ = U+1D18)

When pattern matching against ASCII strings like "std::fs", Unicode homoglyphs bypass the check because the byte sequences differ.

This attack vector was particularly relevant because:
1. LLMs trained on mixed Unicode text may generate homoglyphs
2. Malicious fine-tuning could introduce intentional bypasses
3. Pattern matching is case-insensitive but not Unicode-aware by default

## Decision

Implement **NFKD Unicode normalization** before pattern matching:

```python
import unicodedata

def _normalize_unicode(text: str) -> str:
    """Normalize Unicode to ASCII to prevent homoglyph attacks."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

def _sanitize_rust_completion(completion: str) -> str | None:
    """Check for disallowed patterns with Unicode normalization."""
    normalized = _normalize_unicode(completion.lower())
    
    for pattern in DISALLOWED_COMPLETION_PATTERNS:
        if pattern.lower() in normalized:
            return f"disallowed usage of {pattern}"
```

**NFKD normalization:**
- **N**ormal **F**orm **K**ompatibility **D**ecomposition
- Decomposes characters to base forms
- `ᴅ` (U+1D05) → `D` (U+0044)
- `ꜰ` (U+A730) → `F` (U+0046)
- Non-ASCII characters that don't normalize are dropped

## Consequences

### Positive

- **Blocks homoglyph attacks**: Unicode lookalikes normalized to ASCII
- **Minimal performance impact**: NFKD normalization is fast
- **Comprehensive coverage**: Works for any Unicode normalization case
- **No false positives**: Only affects actual lookalike characters
- **Defense in depth**: Adds layer on top of pattern matching

### Negative

- **May affect non-English identifiers**: Rust allows Unicode identifiers
- **Information loss**: Some Unicode is dropped, not just normalized
- **Not language-aware**: Doesn't understand Rust syntax

### Neutral

- **HumanEval uses ASCII**: Standard problems don't use Unicode identifiers
- **Models typically generate ASCII**: Homoglyphs are rare in practice

## Alternatives Considered

### Alternative 1: Confusables Database

Use Unicode Consortium's confusables.txt to detect lookalikes.

**Rejected because:**
- Requires maintaining/updating external database
- More complex implementation
- NFKD handles the common cases adequately

### Alternative 2: Reject All Non-ASCII

Block any completion containing non-ASCII characters.

**Rejected because:**
- Legitimate Rust code may use Unicode in strings
- Too restrictive for practical use
- Comments may contain Unicode

### Alternative 3: Visual Rendering Check

Render text and compare visually.

**Rejected because:**
- Extremely complex to implement
- Font-dependent results
- Overkill for this use case

## Related

- [ADR-002](ADR-002-pattern-based-security.md) - Pattern matching system this protects
- [human_eval/rust_execution.py](../../human_eval/rust_execution.py) - Implementation
- Unicode NFKD: https://unicode.org/reports/tr15/
- Confusables: https://www.unicode.org/Public/security/latest/confusables.txt


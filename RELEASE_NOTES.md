# v1.2.0 - Emphasis syntax, massively expanded data, and studio-quality polish

A major upgrade to all three nodes. Every tag list has been expanded by 3-5x, emphasis syntax is now fully supported, and the codebase has been refactored for production quality.

---

## Highlights

### Emphasis syntax support across all nodes

A1111/Forge emphasis syntax - `(tag:1.3)`, `((tag))`, `[tag]` - is now correctly parsed, filtered, and re-wrapped with the original emphasis intact. Previously, emphasis-wrapped tags could bypass filtering entirely.

LoRA (`<lora:name:weight>`), hypernetwork, LyCORIS, and embedding syntax are detected and passed through untouched. The `BREAK` keyword is also preserved.

This applies to all three nodes: Gender Tag Filter, Gender NL Filter, and Dedupe Tags.

### 3-5x larger tag coverage

The tag and word lists that power the filtering have been massively expanded:

| Data set | v1.1.0 | v1.2.0 |
| --- | --- | --- |
| Female anatomy tags | ~40 | **145** |
| Male anatomy tags | ~25 | **118** |
| Female presentation tags | ~50 | **152** |
| Male presentation tags | ~15 | **43** |
| F→M clothing swaps | ~30 | **112** |
| M→F clothing swaps | ~15 | **56** |
| F→M NL word swaps | ~40 | **128** |
| M→F NL word swaps | ~35 | **118** |
| NL clothing patterns | ~20 | **111** |
| Anatomy root words | ~15 | **69** |
| Neopronoun entries | ~10 | **35** |

New coverage includes exposure/situational tags (`pantyshot`, `upskirt`, `zettai_ryouiki`, `no_bra`, `no_panties`), furry-specific gendered terms (`vixen`, `doe`, `mare`, `tigress`, `stallion`, `buck`), cross-gender anatomy NL pairings (`pussy` ↔ `cock`, `vagina` ↔ `penis`), and comprehensive makeup, lingerie, swimwear, and formalwear mappings.

### Smarter pronoun handling

The NL Filter now disambiguates `her` between possessive (`her coat` → `his coat`) and object (`gave her` → `gave him`) using spaCy dependency and morphology analysis. Previously both were mapped to the same replacement.

### Negation detection fix

Phrases like `the character has no breasts` were not being detected as negated because spaCy labels `no` before a noun as a determiner (`det`), not a negation (`neg`). The negation detector now also checks for negation determiners and walks up to the head verb, correctly preserving these phrases.

### Performance

All 10 NL regex pattern sets are now precompiled at module load rather than recompiled on every call. All constant data sets use `frozenset` for immutability and faster lookups.

---

## Upgrading

Drop-in replacement. No workflow changes needed - all node inputs and outputs are unchanged. Just update and restart ComfyUI.

If you are using Dedupe Tags in your workflow, emphasis-wrapped duplicates like `(large_breasts:1.3)` and `large_breasts` are now correctly caught. Previously both would survive.

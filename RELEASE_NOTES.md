# v1.2.0 - SpaCy Model Loader, emphasis syntax, massively expanded data, and studio-quality polish

A major upgrade. Four nodes now instead of three. Every tag list has been expanded by 3-5x, emphasis syntax is now fully supported, spaCy is wired in as a proper typed graph connection, and the codebase has been refactored for production quality.

---

## Highlights

### SpaCy Model Loader — a proper typed node for spaCy

spaCy is no longer a hidden string input buried at the bottom of each filter node. A new **SpaCy Model Loader** node loads a model from `ComfyUI/models/spacy/` and outputs a typed `SPACY_NLP` object. Wire it into either filter node to enable spaCy-backed processing; leave it disconnected to use the built-in fallback.

The `SPACY_NLP` custom type means the ComfyUI graph enforces the connection — only the loader can feed those inputs. The presence or absence of the loader node in your graph is itself the signal for whether spaCy is active, replacing the old `backend_used` output.

The loader also detects the most common setup mistake: accidentally placing the outer pip package wrapper folder instead of the inner versioned model folder. It appears in the dropdown, and selecting it produces a clear error with the exact paths to fix.

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

**Existing workflows will need minor updates** due to the spaCy refactor:

- The `spacy_model` string input is gone from both filter nodes. Add a **SpaCy Model Loader** node and wire it in if you want spaCy-backed processing, or leave the `spacy_nlp` input disconnected to keep using the fallback.
- The `backend_used` output is gone. The loader node in the graph is the signal that spaCy is active.
- The `delimiter` input is gone from both filter nodes and Dedupe Tags — input is always split on commas with whitespace stripped, output always uses `, `.
- `tag_format` on the Gender Tag Filter is now `use_underscores` (boolean). Re-connect the widget if you had it set to `spaces`.

If you were using Dedupe Tags, emphasis-wrapped duplicates like `(large_breasts:1.3)` and `large_breasts` are now correctly caught. Previously both would survive.

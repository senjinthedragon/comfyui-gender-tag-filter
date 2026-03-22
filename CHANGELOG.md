# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.1] - 2026-03-23

### Changed

- **Source layout restored** (`gender_shared.py`): the Ruff formatter had collapsed the aligned, human-readable column layout of all data maps and replacement tables into dense single-line style. The maps are now protected with `# fmt: off` / `# fmt: on` markers so the aligned layout is preserved exactly as authored — easier to read, easier to extend.

### Other

- Updated screenshot to reflect the current node layout

---

## [1.2.0] - 2026-03-22

### Added

#### SpaCy Model Loader node (`SpaCyModelLoader`)

- New `SpaCyModelLoader` node that loads a spaCy language model and outputs it as a typed `SPACY_NLP` object
- Model dropdown is populated automatically via `spacy.util.get_installed_models()` — install a model with `python -m spacy download <model>` and it appears in the dropdown after a ComfyUI restart, no folder management needed
- `SPACY_NLP` is a custom ComfyUI type: only `SpaCyModelLoader` outputs can wire into the `spacy_nlp` inputs on the filter nodes, enforced by the ComfyUI type system
- Raises a clear error if spaCy is not installed or no models are downloaded yet, with the exact commands to fix it

#### Gender Tag Filter (`GenderTagFilter`)

- `format_only` mode: applies `use_underscores` formatting with no filtering — useful for normalising tag spacing without any gender processing. Special syntax and NL fragments pass through untouched as in the filter modes.

#### Gender Tag Filter (`GenderTagFilter`) and Gender NL Filter (`GenderNLFilter`)

- `spacy_nlp` optional input (`SPACY_NLP` type): wire a `SpaCyModelLoader` node here to enable spaCy-backed processing; leave disconnected to use the built-in heuristic/regex fallback
- `rewrite_references` toggle added to Gender Tag Filter: swaps standalone gendered noun tags (`woman` → `male`, `girl` → `boy`, `vixen` → `fox`, `doe` → `buck` etc.) — covers the same word set as the NL Filter for consistent behaviour across both nodes

### Removed

- `spacy_model` string input removed from both filter nodes (replaced by the `spacy_nlp` typed connection from `SpaCyModelLoader`)
- `backend_used` second output removed from both filter nodes (the presence or absence of a wired `SpaCyModelLoader` node is visible directly in the graph)
- `delimiter` input removed from both filter nodes and `DedupeTags`: input is always split on commas with whitespace stripped, output always uses `, `

### Changed

- `tag_format` dropdown (Gender Tag Filter) replaced by `use_underscores` boolean toggle so both filter nodes use only boolean widgets from input 3 onward, keeping node heights visually aligned
- Input order aligned across both filter nodes: `text`, `mode`, `filter_anatomy`, `replace_anatomy`, `filter_presentation`, `swap_clothing`, node-specific input, `rewrite_references`, `map_neopronouns`, `handle_negations`
- All data sets converted from `set` to `frozenset` for immutability and slight hash-lookup performance improvement
- `gender_shared.py` expanded from ~760 lines to ~1600 lines - all data maps, utilities, and precompiled patterns centralised in a single shared module

#### Emphasis syntax support (all nodes)

- Full A1111/Forge emphasis syntax support: `(tag:1.3)`, `((tag))`, `[tag]` are now correctly parsed, filtered, and re-wrapped with their original emphasis intact across all three nodes
- LoRA (`<lora:name:weight>`), hypernetwork, LyCORIS, and embedding syntax are detected and passed through untouched - they are never filtered or modified
- The `BREAK` keyword used in SDXL prompts is preserved untouched

#### Gender Tag Filter (`GenderTagFilter`)

- NL fragment detection: natural language fragments mixed into tag lists by TIPO are detected via spaCy dependency parsing (stop-word heuristic fallback) and passed through untouched so the NL Filter can handle them
- Neopronoun tag mapping: `map_neopronouns` toggle maps neopronoun tags (`shi`, `hir`, `they`, `xe`, `ze`, `ey`, `fae` etc.) to binary equivalents - covers the same set as the NL Filter for consistent standalone behaviour
- Negation guard: protects tags that appear in a negated context in mixed prompts (e.g. `no breasts`) from removal using a 4-token proximity heuristic
- Newline-aware input splitting: newlines are treated as hard boundaries between tag and prose sections

#### Gender NL Filter (`GenderNLFilter`)

- `her` pronoun disambiguation: spaCy dependency and morphology analysis distinguishes possessive `her` (→ `his`) from object `her` (→ `him`) for accurate pronoun swaps
- Cross-gender NL anatomy pairings: `pussy` ↔ `cock`, `vagina` ↔ `penis`, `pecs` ↔ `breasts` and more
- Precompiled swap patterns: all 10 regex pattern sets are compiled at module load rather than per-call, significantly improving performance on large prompts

#### Dedupe Tags (`DedupeTags`)

- Emphasis-aware deduplication: `(large_breasts:1.3)` and `large_breasts` are correctly identified as the same tag (first occurrence wins)
- LoRA syntax and `BREAK` keywords always pass through without deduplication

#### Data expansion (`gender_shared.py`)

- **145** female anatomy tags (up from ~40)
- **118** male anatomy tags (up from ~25)
- **152** female presentation tags (up from ~50) - now includes exposure/situational tags: `pantyshot`, `upskirt`, `no_bra`, `no_panties`, `visible_bra`, `bra_strap`, `panty_pull`, `skirt_lift`, `dress_lift`, `zettai_ryouiki`, `absolute_territory`
- **43** male presentation tags (up from ~15)
- **43** female→male anatomy replacement pairs
- **29** male→female anatomy replacement pairs
- **112** female→male clothing tag swaps
- **56** male→female clothing tag swaps
- **128** female→male NL word/noun swaps (includes furry terms: `vixen`, `doe`, `mare`, `tigress` etc.)
- **118** male→female NL word/noun swaps
- **71** female→male NL clothing patterns
- **40** male→female NL clothing patterns
- **36** female anatomy root words for compound tag scanning
- **33** male anatomy root words for compound tag scanning
- **35** neopronoun entries covering `shi/hir`, `they/them`, `xe/xem`, `ze/zir`, `ey/em`, `fae/faer`, `ve/ver`, `per`

### Fixed

- **Negation detection for "no + noun" pattern** (`gender_shared.py`): spaCy labels `no` before a noun as `dep_="det"` (determiner), not `dep_="neg"`, so phrases like `the character has no breasts` were not being detected as negated. `has_negation_ancestor()` now also checks for negation determiners (`no`, `none`, `neither`, `never`) and walks up to the head verb to catch negation on auxiliary/verb nodes
- **Invalid mode silent fallback** (`gender_tag_filter.py`, `gender_nl_filter.py`): bare `else` blocks on mode selection in all three processing paths (`filter_gender_tags`, `_process_regex`, `_process_spacy`) would silently treat any unrecognised mode string as `strip_male`. Changed to explicit `elif` with a final `else: return text` so unrecognised modes pass through safely
- **`flat_chest: flat_chest` no-op replacement** (`gender_shared.py`): `flat_chest` was mapped to itself in `MALE_TO_FEMALE_REPLACEMENTS`. The tag is not in `MALE_ANATOMY` so it would never reach the anatomy blocklist anyway, making the replacement doubly unreachable. Entry removed.
- **Dead `NEOPRONOUN_TAG_FORMS` constant** (`gender_shared.py`): the constant was defined but never used anywhere in the codebase — the import had been removed from `gender_tag_filter.py` in an earlier pass but the definition itself remained. Removed.
- Date for last release in the CHANGELOG.md is now correct
- Removed unused `import logging` and `log = logging.getLogger(__name__)` from `gender_tag_filter.py` and `gender_nl_filter.py`

## [1.1.0] - 2026-03-16

### Added

#### Dedupe Tags node (`DedupeTags`)

- Moved into the node pack from a standalone file so users get the full pipeline in a single install
- Removes duplicate tags from a comma-separated tag string, keeping the first occurrence of each
- Underscore/space normalisation: `big_breasts` and `big breasts` are now correctly treated as the same tag regardless of which form upstream nodes produce - previously these would both survive deduplication
- Case-insensitive comparison by default; `case_sensitive` toggle available for edge cases
- Empty tags and double-comma artefacts are stripped automatically
- Moved from `utils/text` to `utils/tags` category to sit alongside the gender filter nodes

## [1.0.2] - 2026-03-16

### Fixed

- `pyproject.toml` was including with wildcards which doesn't work for the registry. This is now fixed.

## [1.0.1] - 2026-03-15

### Fixed

- **Negation guard false positive on standalone tags** (`gender_tag_filter.py`): when a tag list contained both `no_breasts` and `breasts` as separate tags, the negation guard was scanning the entire input string for negation context. It found `no` near `breasts` earlier in the string and incorrectly preserved the standalone `breasts` tag. The guard now only applies to multi-word chunks - a single-word tag cannot be negated within itself, and a `no_breasts` compound tag elsewhere in the list has no grammatical relationship to a standalone `breasts` tag.

- **`NL_STOP_WORDS` false positives on common Danbooru compound tags** (`gender_shared.py`): words like `with`, `and`, `in`, `on`, `of`, `at`, `from`, `by`, `up`, `down`, `out`, `off`, `away`, `over`, `under`, `around` were in the stop word list used to detect natural language fragments. These are extremely common in Danbooru compound tags - `furry with non-furry`, `tongue out`, `from behind`, `looking at viewer`, `thumbs up`, `bent over` etc. - causing them to be misidentified as natural language and have their spaces incorrectly preserved rather than converted to underscores. The stop word list has been trimmed to only words that genuinely never appear in tag lists: articles, copulas, personal pronouns, and a small set of verb forms.

- **Backslash-escaped parentheses corrupted by tag formatter** (`gender_shared.py`): Danbooru tags containing backslash-escaped parentheses (e.g. `lizardman \(warcraft\)`) had their backslashes stripped during space-to-underscore conversion, producing malformed output. `normalise_tag` and `format_tag` now use a protect-convert-restore pattern to preserve all backslash-escaped sequences intact.

## [1.0.0] - 2026-03-14

### Added

#### Shared module (`gender_shared.py`)

- All data maps and utilities live in a single shared module imported by both nodes, so adding a new tag or swap pair in one place applies everywhere automatically
- Shared content includes: spaCy loader, case preservation, pattern builder, tag normaliser, NL/tag detection helpers, negation helpers, plural `they/them` detection, all pronoun maps, all word maps, all anatomy sets and replacement maps (tag and NL format), all clothing maps (underscore and space format), `NEGATION_WORDS`, `DANGLING_ADJ_PATTERN`, `NEOPRONOUN_MAP`

#### Gender Tag Filter node (`GenderTagFilter`)

- Tag-list filtering for Danbooru and e621 style prompts
- `mode` dropdown: `strip_female_tags`, `strip_male_tags`, `off`
- `filter_anatomy` toggle: removes explicit anatomical tags for the unwanted gender; also scans compound tags for anatomy root words so unlisted tags like `huge_breasts`, `breast_grab`, `hanging_breasts` are caught automatically
- `filter_presentation` toggle: also removes gendered clothing and accessory tags - disabled by default so crossdressing characters keep their outfit tags
- `apply_replacements` toggle: substitutes gender-appropriate counterparts for removed anatomy tags rather than deleting them (e.g. `large_breasts` -> `muscular_chest`, `breasts` -> `pecs`)
- `swap_clothing_tags` toggle: when `filter_presentation` is on, replaces clothing tags with gender-appropriate equivalents instead of removing them (e.g. `skirt` -> `trousers`, `bikini` -> `swim_trunks`, `bra` -> removed) - full `FEMALE_TO_MALE_CLOTHING` and `MALE_TO_FEMALE_CLOTHING` maps cover the entire presentation tag set
- `map_neopronouns` toggle: maps neopronoun tags (`shi`, `hir`, `they`, `xe`, `ze`, `ey`, `fae` etc.) to binary equivalents image models recognise - same neopronoun set as the NL Filter for consistent behaviour when used standalone
- `handle_negations` toggle: protects tags that appear in a negated context in mixed prompts from removal, using a 4-token proximity heuristic
- `tag_format` dropdown: normalises output to `underscores` or `spaces` to match the expectations of different model families - input tags are always accepted in either style; natural language fragments bypass this entirely
- `spacy_model` input: selects the spaCy model used for NL fragment detection (`en_core_web_sm` default)
- Forgiving delimiter handling: leading and trailing whitespace around tags is stripped on input, so `tag1,tag2` and `tag1, tag2` parse identically
- Newline-aware input splitting: newlines are treated as hard boundaries between the tag section and NL prose, preventing TIPO's occasional NL fragments from escaping the root scan by being merged with adjacent tags
- NL fragment detection: natural language fragments mixed into the tag list by TIPO are detected via spaCy dependency parsing (stop-word heuristic fallback) and passed through untouched to the NL Filter with their spacing preserved
- Full female and male anatomy blocklists and root sets
- Full female and male presentation blocklists (clothing, makeup, accessories)
- Female-to-male and male-to-female anatomy replacement maps
- Female-to-male and male-to-female clothing replacement maps (tag format)

#### Gender NL Filter node (`GenderNLFilter`)

- Natural language filtering for prose prompts and mixed tag+NL prompts
- Designed to chain directly after Gender Tag Filter for full pipeline coverage
- `mode` dropdown: `strip_female_language`, `strip_male_language`, `off`
- `filter_anatomy` toggle: enables or disables anatomy processing entirely - turn off to leave all anatomy language completely untouched
- `replace_anatomy` toggle: when `filter_anatomy` is on, replaces anatomy words with gender-appropriate NL counterparts rather than removing them (e.g. `Her breasts bounced` -> `His pecs bounced`) - words with no clean NL equivalent are still removed
- `handle_negations` toggle: protects negated anatomy terms from removal or replacement (e.g. `no breasts`, `without a vagina`) - uses spaCy dependency parsing for accuracy, 4-token proximity heuristic as fallback
- `handle_pronouns` toggle: swaps binary gendered pronouns and possessives (`she/her/hers/herself` <-> `he/him/his/himself`)
- `rewrite_references` toggle: swaps gendered nouns and adjectives (`woman/girl/lady` <-> `man/boy/guy` and equivalents), including furry-specific terms (`vixen/doe/mare/tigress` etc.)
- `filter_presentation` toggle: enables or disables clothing and accessory processing entirely - mirrors the tag filter's `filter_presentation` for consistent crossdressing support across both nodes
- `swap_clothing` toggle: when `filter_presentation` is on, replaces clothing terms with gender-appropriate equivalents rather than removing them (e.g. `dress` -> `suit`, `skirt` -> `trousers`, `bra` -> removed, `bikini` -> `swim trunks`)
- `map_neopronouns` toggle: maps neopronouns and gender-neutral pronouns to binary equivalents image models recognise - covers `shi/hir` (Chakat/furry), singular `they/them`, `xe/xem`, `ze/zir`, `ey/em` (Spivak), `fae/faer`; spaCy detects and preserves plural `they/them` (regex fallback is approximate); when off all neopronouns pass through unchanged
- `spacy_model` input: selects the spaCy language model (`en_core_web_sm` default)
- `backend_used` second output: returns `spacy`, `regex`, or `off` - wire to a ShowText node to confirm which backend is active without digging through the console
- Standalone tag detection: comma-split chunks that look like tags rather than sentences are skipped to prevent double-processing of content already handled by the tag filter
- Chunk-level spaCy processing: each comma-separated chunk is parsed independently, improving accuracy on mixed tag+NL strings
- spaCy lazy loader: model is loaded on first use rather than at import time, so a missing spaCy installation does not prevent ComfyUI from starting
- Automatic fallback to regex processing if spaCy or the requested model is not installed, with clear console instructions for how to install them
- spaCy model caching: model is keyed by name so switching the `spacy_model` input in the UI correctly loads the new model rather than returning the previously cached one
- Capitalisation preservation on all swaps: `She` -> `He`, `SHE` -> `HE`, `she` -> `he`
- Multi-word clothing term matching (e.g. `evening gown`, `swim trunks`, `high heels`) handled correctly in both spaCy and regex backends
- Chained dangling adjective cleanup: adjectives that modify a removed anatomy word are removed along with their noun - handles multiple chained adjectives (e.g. `huge, perky breasts` removes both)
- Female-to-male and male-to-female NL anatomy replacement maps
- Female-to-male and male-to-female NL clothing swap maps (space format)

#### Node pack infrastructure

- Both nodes registered under `utils/tags` category in ComfyUI
- Single-folder installation: drop into `ComfyUI/custom_nodes/` and restart
- `__init__.py` registers both nodes from one import
- No required dependencies beyond ComfyUI itself (spaCy is optional but recommended for both nodes)

#### Known Issues

- spaCy cannot currently be installed on Python 3.13 or 3.14 due to incompatibilities in its `pydantic v1` and `blis` dependencies. On Python 3.14, `blis` additionally fails to compile because gcc 14 dropped support for the `-mavx512pf` flag that the bundled `blis 0.7.x` source requires. Both nodes automatically fall back to regex mode on affected systems. Workaround: create your ComfyUI venv under Python 3.12.

[1.2.0]: https://github.com/senjinthedragon/comfyui-gender-tag-filter/releases/tag/v1.2.0
[1.1.0]: https://github.com/senjinthedragon/comfyui-gender-tag-filter/releases/tag/v1.1.0
[1.0.1]: https://github.com/senjinthedragon/comfyui-gender-tag-filter/releases/tag/v1.0.1
[1.0.0]: https://github.com/senjinthedragon/comfyui-gender-tag-filter/releases/tag/v1.0.0

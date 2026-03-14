# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.1.0] - 2026-03-14

### Added

#### Gender Tag Filter node

- `swap_clothing_tags` toggle: when `filter_presentation` is on, replace clothing tags with gender-appropriate equivalents instead of removing them (e.g. `skirt` → `trousers`, `bikini` → `swim_trunks`, `bra` → removed) — new `FEMALE_TO_MALE_CLOTHING` and `MALE_TO_FEMALE_CLOTHING` maps cover the full presentation tag set
- `map_neopronouns` toggle: maps neopronoun tags (`shi`, `hir`, `they`, `xe`, `ze`, `ey`, `fae` etc.) to binary equivalents image models recognise — same neopronoun set as the NL Filter for consistent behaviour when used standalone
- `handle_negations` toggle: protects tags that appear in a negated context in mixed prompts from removal, using the same 4-token proximity heuristic as the NL Filter
- `spacy_model` input: exposes the spaCy model name used for NL fragment detection (previously hardcoded to `en_core_web_sm`)
- Compound anatomy root word scanning: catches unlisted compound tags like `huge_breasts`, `breast_grab`, `hanging_breasts` by checking each underscore-separated component against an anatomy root set
- Newline-aware input splitting: newlines are treated as hard boundaries between the tag section and NL prose, preventing TIPO's occasional NL fragments from being merged with adjacent tags and escaping the root scan

#### Gender NL Filter node

- `filter_anatomy` toggle: allows anatomy processing to be skipped entirely without disabling other filters
- `filter_presentation` toggle: allows clothing/accessory processing to be skipped entirely — mirrors the tag filter's `filter_presentation` for consistent crossdressing support across both nodes
- `replace_anatomy` toggle: replaces anatomy words with gender-appropriate NL counterparts rather than removing them (e.g. `Her breasts bounced` → `His pecs bounced`) — words with no clean NL equivalent are still removed
- Standalone tag detection: comma-split chunks that look like tags rather than sentences are now skipped by the NL filter to prevent double-processing of tags already handled by the tag filter
- Chunk-level spaCy processing: each comma-separated chunk is now parsed independently, improving accuracy on mixed tag+NL strings

#### Shared module (`gender_shared.py`)

- Extracted all shared data and utilities into a single importable module to eliminate code duplication between the two nodes
- Shared content: `load_spacy`, `preserve_case`, `make_swap_pattern`, `apply_swap_patterns`, `normalise_tag`, `format_tag`, `is_natural_language`, `chunk_is_tag`, `is_negated_regex`, `has_negation_ancestor`, `is_plural_they`, all pronoun maps, all word maps, all anatomy sets and replacement maps (both tag and NL format), all clothing maps (both underscore and space format), `NEGATION_WORDS`, `DANGLING_ADJ_PATTERN`, `NEOPRONOUN_MAP`
- Both nodes now import from `gender_shared` — adding a new tag or swap pair in one place applies to both nodes automatically

### Fixed

- `word_map` double-assignment bug in `_process_spacy`: the initial reversed assignment was removed; `word_map` is now assigned once correctly
- Multi-word clothing span skip bug: the spaCy processing loop now uses an index-based `while` loop instead of `for i, token in enumerate`, so after matching a multi-word span (e.g. `evening gown`) the index advances past all consumed tokens and the second word is no longer processed again as an independent token
- Chained dangling adjective removal: `DANGLING_ADJ_PATTERN` now uses a repeating group so `huge, perky breasts` correctly removes both adjectives rather than leaving one behind
- spaCy cache invalidation: the cache now keys on model name, so changing the `spacy_model` input in the UI correctly loads the new model rather than returning the first cached one

### Changed

- `map_neopronouns_to_binary` renamed to `map_neopronouns` on both nodes for consistency and brevity
- `swap_clothing` on the NL Filter is now gated by a separate `filter_presentation` toggle, matching the tag filter's pattern
- All data maps and utilities moved from individual node files into `gender_shared.py` — the node files are now thin wrappers

---

## [1.0.0] - 2026-03-14

### Added

#### Gender Tag Filter node (`GenderTagFilter`)

- Tag-list filtering for Danbooru and e621 style prompts
- `mode` dropdown: `strip_female_tags`, `strip_male_tags`, `off`
- `filter_anatomy` toggle: removes explicit anatomical tags for the unwanted gender (breasts, genitalia, etc.)
- `filter_presentation` toggle: optionally removes gendered clothing and accessory tags — disabled by default so crossdressing characters keep their outfit tags
- `apply_replacements` toggle: substitutes gender-appropriate counterparts for removed tags rather than simply deleting them (e.g. `large_breasts` → `muscular_chest`, `wide_hips` → `narrow_hips`)
- `tag_format` dropdown: normalises output to `underscores` or `spaces` to match the expectations of different model families — input tags are always accepted in either style regardless of this setting
- Forgiving delimiter handling: leading and trailing whitespace around tags is stripped on input, so `tag1,tag2` and `tag1, tag2` parse identically
- Furry and e621 specific anatomy and presentation tags included in all blocklists
- Full female and male anatomy blocklists
- Full female and male presentation blocklists (clothing, makeup, accessories)
- Female-to-male and male-to-female replacement maps

#### Gender NL Filter node (`GenderNLFilter`)

- Natural language filtering for prose prompts and mixed tag+NL prompts
- Designed to chain directly after Gender Tag Filter for full pipeline coverage
- `mode` dropdown: `strip_female_language`, `strip_male_language`, `off`
- `handle_negations` toggle: protects negated anatomy terms from removal (e.g. `no breasts`, `without a vagina`) — uses spaCy dependency parsing for accuracy, 4-token proximity heuristic as fallback
- `handle_pronouns` toggle: swaps binary gendered pronouns and possessives (`she/her/hers/herself` ↔ `he/him/his/himself`)
- `rewrite_references` toggle: swaps gendered nouns and adjectives (`woman/girl/lady` ↔ `man/boy/guy` and equivalents), including furry-specific terms (`vixen/doe/mare/tigress` etc.)
- `swap_clothing` toggle: replaces gendered clothing terms with model-recognisable equivalents, or removes them where no clean equivalent exists (`dress` → `suit`, `skirt` → `trousers`, `bra` → removed, `bikini` → `swim trunks`)
- `map_neopronouns_to_binary` toggle: maps neopronouns and gender-neutral pronouns to binary equivalents that image generation models are likely to recognise from their training data
  - Covers `shi/hir` (Chakat/furry), singular `they/them`, `xe/xem`, `ze/zir`, `ey/em` (Spivak), `fae/faer`
  - spaCy detects and preserves plural `they/them` (regex fallback is approximate for this case)
  - When off, all neopronouns pass through unchanged
- `spacy_model` input: selects the spaCy language model (`en_core_web_sm` default)
- `backend_used` second output: returns `spacy`, `regex`, or `off` for debugging — wire to a ShowText node to confirm which backend is active
- spaCy lazy loader: model is loaded on first use rather than at import time, so a missing spaCy installation does not prevent ComfyUI from starting
- Automatic fallback to regex processing if spaCy or the requested model is not installed, with clear console instructions for how to install them
- spaCy model caching: model loads once per ComfyUI session regardless of how many times the node runs
- Capitalisation preservation on all swaps: `She` → `He`, `SHE` → `HE`, `she` → `he`
- Multi-word clothing term matching (e.g. `evening gown`, `swim trunks`, `high heels`) handled correctly in both spaCy and regex backends
- Dangling adjective cleanup: adjectives that modify a removed anatomy word (e.g. `large` in `large breasts`) are removed along with their noun to avoid malformed output

#### Known Issues

- spaCy cannot currently be installed on Python 3.13 or 3.14 due to incompatibilities in its `pydantic v1` and `blis` dependencies. On Python 3.14, `blis` additionally fails to compile because gcc 14 dropped support for the `-mavx512pf` flag that the bundled `blis 0.7.x` source requires. The Gender NL Filter node automatically falls back to regex mode on affected systems. Workaround: create your ComfyUI venv under Python 3.12.

#### Node pack infrastructure

- Both nodes registered under `utils/tags` category in ComfyUI
- Single-folder installation: drop into `ComfyUI/custom_nodes/` and restart
- `__init__.py` registers both nodes from one import
- No required dependencies beyond ComfyUI itself (spaCy is optional but recommended)

---

[1.1.0]: https://github.com/senjinthedragon/comfyui-gender-tag-filter/releases/tag/v1.1.0
[1.0.0]: https://github.com/senjinthedragon/comfyui-gender-tag-filter/releases/tag/v1.0.0

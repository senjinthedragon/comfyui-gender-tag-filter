# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

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

---

[1.0.0]: https://github.com/senjinthedragon/comfyui-gender-tag-filter/releases/tag/v1.0.0

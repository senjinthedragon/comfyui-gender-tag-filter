# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.0.0]: https://github.com/senjinthedragon/comfyui-gender-tag-filter/releases/tag/v1.0.0

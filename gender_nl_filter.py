"""
gender_nl_filter.py - comfyui-gender-tag-filter: Gender NL Filter Node
Copyright (c) 2026 Senjin the Dragon.
https://github.com/senjinthedragon/comfyui-gender-tag-filter
Licensed under the MIT License.
See LICENSE for full license information.

==========================================================================
IMPORTANT NOTE
==========================================================================
This node is a prompt engineering utility for AI image generation models.
Its sole purpose is to help these models produce output that matches the
user's intended scene by adjusting the vocabulary in the prompt string.

It makes no claims about gender identity, linguistics, or real people.
Pronoun and word mappings are chosen purely on the basis of what AI image
generation models have been trained to recognise.
==========================================================================

ComfyUI node (GenderNLFilter) that filters and rewrites gendered vocabulary
in natural language prompts or mixed tag+NL prompts.

Designed to chain directly after GenderTagFilter. Input is split on commas
and each chunk is checked against chunk_is_tag() before processing - chunks
that look like standalone tags are passed through untouched to avoid
double-processing content already handled by GenderTagFilter.
Both nodes accept and output STRING, so they wire together naturally.

Uses spaCy for accurate negation detection (dependency tree neg relation),
plural they/them disambiguation (morphology + subject count heuristic),
pronoun case disambiguation (possessive vs object "her"), and multi-word
clothing span matching (token-index lookahead). Falls back to regex
processing automatically if spaCy is not installed, with a warning logged to
the ComfyUI console.

All data maps and utility functions are imported from gender_shared.py.
Precompiled swap patterns from gender_shared.py are used by the regex
fallback, avoiding repeated recompilation on every call.

Controls
--------
mode                    : "off" | "strip_female_language" | "strip_male_language"

filter_anatomy          : bool (default True)
                          Process anatomy words at all. Turn off to leave all
                          anatomy language completely untouched.

replace_anatomy         : bool (default True)
                          When filter_anatomy is on, replace anatomy words with
                          gender-appropriate counterparts rather than removing.
                          e.g. "Her breasts bounced" -> "His pecs bounced"
                          Words with no clean equivalent are still removed.

handle_negations        : bool (default True)
                          Protect negated anatomy terms from removal/replacement.
                          e.g. "no breasts", "without a vagina" left untouched.
                          Uses spaCy dependency parsing; regex fallback uses
                          a 4-token proximity heuristic.

handle_pronouns         : bool (default True)
                          Swap binary pronouns.
                          she/her/hers/herself  <->  he/him/his/himself

rewrite_references      : bool (default True)
                          Swap gendered nouns and adjectives.
                          woman/girl/lady <-> man/boy/guy etc.
                          Also covers furry-specific terms.

filter_presentation     : bool (default True)
                          Process clothing/accessory language at all.
                          Turn off to leave all clothing language untouched.

swap_clothing           : bool (default True)
                          When filter_presentation is on, replace clothing terms
                          with gender-appropriate equivalents rather than removing.
                          e.g. dress -> suit, skirt -> trousers,
                               bra -> removed, bikini -> swim trunks

map_neopronouns         : bool (default True)
                          Map neopronouns to binary equivalents image models
                          recognise. Covers shi/hir, they/them, xe/xem, ze/zir,
                          ey/em, fae/faer, ve/ver, per. Plural they/them
                          preserved by spaCy (regex fallback is approximate).

spacy_model             : str (default "en_core_web_sm")
                          Falls back to regex if spaCy is not installed.
"""

import re

from .gender_shared import (
    CLOTHING_FEMALE_TO_MALE_NL,
    CLOTHING_MALE_TO_FEMALE_NL,
    DANGLING_ADJ_PATTERN,
    FEMALE_ANATOMY_NL,
    FEMALE_ANATOMY_NL_REPLACEMENTS,
    FEMALE_TO_MALE_PRONOUNS,
    FEMALE_TO_MALE_WORDS,
    MALE_ANATOMY_NL,
    MALE_ANATOMY_NL_REPLACEMENTS,
    MALE_TO_FEMALE_PRONOUNS,
    MALE_TO_FEMALE_WORDS,
    NEOPRONOUN_MAP,
    # Precompiled swap patterns
    FEMALE_PRONOUN_PATTERNS,
    MALE_PRONOUN_PATTERNS,
    FEMALE_WORD_PATTERNS,
    MALE_WORD_PATTERNS,
    FEMALE_CLOTHING_NL_PATTERNS,
    MALE_CLOTHING_NL_PATTERNS,
    FEMALE_CLOTHING_NL_REMOVE_PATTERNS,
    MALE_CLOTHING_NL_REMOVE_PATTERNS,
    NEO_TO_MALE_PATTERNS,
    NEO_TO_FEMALE_PATTERNS,
    apply_swap_patterns,
    chunk_is_tag,
    disambiguate_her_spacy,
    has_negation_ancestor,
    is_negated_regex,
    is_plural_they,
    load_spacy,
    preserve_case,
)

# ---------------------------------------------------------------------------
# Regex fallback
# ---------------------------------------------------------------------------

def _handle_anatomy_regex(text, anatomy_set, anatomy_replacements,
                           handle_negations, replace_anatomy):
    for word in sorted(anatomy_set, key=len, reverse=True):
        pat = re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE)
        if not pat.search(text):
            continue
        if handle_negations and is_negated_regex(text, word):
            continue
        replacement = anatomy_replacements.get(word) if replace_anatomy else None
        if replacement:
            text = pat.sub(
                lambda m, r=replacement: preserve_case(m.group(0), r), text
            )
        else:
            text = re.sub(
                DANGLING_ADJ_PATTERN.pattern + r'\b' + re.escape(word) + r'\b',
                '', text, flags=re.IGNORECASE
            )
            text = pat.sub('', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\s+([,.])', r'\1', text)
    text = re.sub(r',\s*,', ',', text)
    return text.strip()


def _process_regex(text, mode, filter_anatomy, replace_anatomy, handle_negations,
                   handle_pronouns, rewrite_references, filter_presentation,
                   swap_clothing, map_neopronouns):
    if mode == "strip_female_language":
        pronoun_patterns     = FEMALE_PRONOUN_PATTERNS
        word_patterns        = FEMALE_WORD_PATTERNS
        anatomy_set          = FEMALE_ANATOMY_NL
        anatomy_replacements = FEMALE_ANATOMY_NL_REPLACEMENTS
        clothing_patterns    = FEMALE_CLOTHING_NL_PATTERNS
        clothing_rm_patterns = FEMALE_CLOTHING_NL_REMOVE_PATTERNS
        neo_patterns         = NEO_TO_MALE_PATTERNS
    else:
        pronoun_patterns     = MALE_PRONOUN_PATTERNS
        word_patterns        = MALE_WORD_PATTERNS
        anatomy_set          = MALE_ANATOMY_NL
        anatomy_replacements = MALE_ANATOMY_NL_REPLACEMENTS
        clothing_patterns    = MALE_CLOTHING_NL_PATTERNS
        clothing_rm_patterns = MALE_CLOTHING_NL_REMOVE_PATTERNS
        neo_patterns         = NEO_TO_FEMALE_PATTERNS

    # Split on commas, skip standalone tags, process NL chunks
    chunks = [c.strip() for c in text.split(",")]
    processed = []

    for chunk in chunks:
        if not chunk:
            continue
        if chunk_is_tag(chunk):
            processed.append(chunk)
            continue

        if filter_anatomy:
            chunk = _handle_anatomy_regex(
                chunk, anatomy_set, anatomy_replacements,
                handle_negations, replace_anatomy
            )
        if filter_presentation:
            if swap_clothing:
                chunk = apply_swap_patterns(chunk, clothing_patterns)
            else:
                chunk = apply_swap_patterns(chunk, clothing_rm_patterns)

        if map_neopronouns:
            chunk = apply_swap_patterns(chunk, neo_patterns)
        if handle_pronouns:
            chunk = apply_swap_patterns(chunk, pronoun_patterns)
        if rewrite_references:
            chunk = apply_swap_patterns(chunk, word_patterns)

        processed.append(chunk)

    return ", ".join(c for c in processed if c)


# ---------------------------------------------------------------------------
# spaCy processing
# ---------------------------------------------------------------------------

def _process_spacy(text, nlp, mode, filter_anatomy, replace_anatomy,
                   handle_negations, handle_pronouns, rewrite_references,
                   filter_presentation, swap_clothing, map_neopronouns):
    if mode == "strip_female_language":
        pronoun_map          = FEMALE_TO_MALE_PRONOUNS
        word_map             = FEMALE_TO_MALE_WORDS
        anatomy_set          = FEMALE_ANATOMY_NL
        anatomy_replacements = FEMALE_ANATOMY_NL_REPLACEMENTS
        clothing_map         = CLOTHING_FEMALE_TO_MALE_NL
        neo_index            = 0
    else:
        pronoun_map          = MALE_TO_FEMALE_PRONOUNS
        word_map             = MALE_TO_FEMALE_WORDS
        anatomy_set          = MALE_ANATOMY_NL
        anatomy_replacements = MALE_ANATOMY_NL_REPLACEMENTS
        clothing_map         = CLOTHING_MALE_TO_FEMALE_NL
        neo_index            = 1

    neo_swap = {k: v[neo_index] for k, v in NEOPRONOUN_MAP.items()}
    clothing_sorted = sorted(clothing_map.items(), key=lambda x: -len(x[0]))

    chunks = [c.strip() for c in text.split(",")]
    processed = []

    for chunk in chunks:
        if not chunk:
            continue
        if chunk_is_tag(chunk, nlp):
            processed.append(chunk)
            continue

        doc = nlp(chunk)
        result_tokens = []
        i = 0

        while i < len(doc):
            token = doc[i]
            token_lower = token.text.lower()
            ws = token.whitespace_

            # ── Anatomy ──────────────────────────────────────────────────
            if filter_anatomy and token_lower in anatomy_set:
                if handle_negations and has_negation_ancestor(token):
                    result_tokens.append(token.text_with_ws)
                    i += 1
                    continue
                replacement = anatomy_replacements.get(token_lower) if replace_anatomy else None
                if replacement:
                    result_tokens.append(preserve_case(token.text, replacement) + ws)
                else:
                    # Walk back to remove chained dangling adjectives
                    while result_tokens and i > 0:
                        last = result_tokens[-1]
                        if last.strip() == '':
                            result_tokens.pop()
                            continue
                        prev_idx = i - 1
                        while prev_idx >= 0 and doc[prev_idx].text_with_ws.strip() == '':
                            prev_idx -= 1
                        if prev_idx >= 0:
                            prev_tok = doc[prev_idx]
                            if prev_tok.pos_ == "ADJ" and prev_tok.head.i == token.i:
                                result_tokens.pop()
                                while result_tokens and result_tokens[-1].strip() in ('', ','):
                                    result_tokens.pop()
                                i = prev_idx
                                token = doc[i]
                                continue
                        break
                    result_tokens.append(ws)
                i += 1
                continue

            # ── Clothing ─────────────────────────────────────────────────
            if filter_presentation:
                matched = False
                for src, dst in clothing_sorted:
                    src_tokens = src.split()
                    span_end = i + len(src_tokens)
                    if span_end <= len(doc):
                        span = ' '.join(t.text.lower() for t in doc[i:span_end])
                        if span == src:
                            trail_ws = doc[span_end - 1].whitespace_
                            if swap_clothing and dst:
                                result_tokens.append(preserve_case(token.text, dst) + trail_ws)
                            else:
                                result_tokens.append(trail_ws)
                            i = span_end
                            matched = True
                            break
                if matched:
                    continue

            # ── Neopronouns ───────────────────────────────────────────────
            if map_neopronouns and token_lower in neo_swap:
                if token_lower in {"they","them","their","theirs","themselves","themself"}:
                    if is_plural_they(token):
                        result_tokens.append(token.text_with_ws)
                        i += 1
                        continue
                result_tokens.append(preserve_case(token.text, neo_swap[token_lower]) + ws)
                i += 1
                continue

            # ── Binary pronouns ───────────────────────────────────────────
            if handle_pronouns and token_lower in pronoun_map:
                # Disambiguate "her" between possessive (-> his) and
                # object (-> him) using spaCy dependency parsing.
                if token_lower == "her" and mode == "strip_female_language":
                    replacement = disambiguate_her_spacy(token)
                    result_tokens.append(preserve_case(token.text, replacement) + ws)
                else:
                    result_tokens.append(preserve_case(token.text, pronoun_map[token_lower]) + ws)
                i += 1
                continue

            # ── Gendered nouns / adjectives ───────────────────────────────
            if rewrite_references and token_lower in word_map:
                result_tokens.append(preserve_case(token.text, word_map[token_lower]) + ws)
                i += 1
                continue

            result_tokens.append(token.text_with_ws)
            i += 1

        chunk_out = ''.join(result_tokens)
        chunk_out = re.sub(r'[ \t]{2,}', ' ', chunk_out)
        chunk_out = re.sub(r'\s+([,.])', r'\1', chunk_out)
        processed.append(chunk_out.strip())

    return ", ".join(c for c in processed if c)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def filter_nl_gender(
    text: str,
    mode: str = "off",
    filter_anatomy: bool = True,
    replace_anatomy: bool = True,
    filter_presentation: bool = True,
    swap_clothing: bool = True,
    handle_pronouns: bool = True,
    rewrite_references: bool = True,
    map_neopronouns: bool = True,
    handle_negations: bool = True,
    spacy_model: str = "en_core_web_sm",
) -> tuple:
    if mode == "off" or not text.strip():
        return text, "off"

    nlp = load_spacy(spacy_model)

    kwargs = dict(
        mode=mode,
        filter_anatomy=filter_anatomy,
        replace_anatomy=replace_anatomy,
        handle_negations=handle_negations,
        handle_pronouns=handle_pronouns,
        rewrite_references=rewrite_references,
        filter_presentation=filter_presentation,
        swap_clothing=swap_clothing,
        map_neopronouns=map_neopronouns,
    )

    if nlp is not None:
        return _process_spacy(text=text, nlp=nlp, **kwargs), "spacy"
    else:
        return _process_regex(text=text, **kwargs), "regex"


# ---------------------------------------------------------------------------
# ComfyUI node definition
# ---------------------------------------------------------------------------

class GenderNLFilter:
    CATEGORY = "utils/tags"
    FUNCTION = "run"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("filtered_text", "backend_used")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # ── Core ──────────────────────────────────────────────────────
                "text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "tooltip": (
                        "Natural language prompt, tag list, or mixed content.\n"
                        "Chain after GenderTagFilter for full tag+NL coverage.\n"
                        "Standalone tags are detected and skipped automatically."
                    ),
                }),
                "mode": (["off", "strip_female_language", "strip_male_language"], {
                    "default": "strip_female_language",
                    "tooltip": (
                        "'strip_female_language' -> rewrite female-coded vocabulary\n"
                        "'strip_male_language'   -> rewrite male-coded vocabulary\n"
                        "'off'                   -> pass through unchanged"
                    ),
                }),
                # ── Anatomy ───────────────────────────────────────────────────
                "filter_anatomy": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Process anatomy words at all.\n"
                        "Turn off to leave all anatomy language completely untouched."
                    ),
                }),
                "replace_anatomy": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Replace anatomy words with gender-appropriate counterparts\n"
                        "rather than removing them entirely.\n"
                        "e.g. 'Her breasts bounced' -> 'His pecs bounced'\n"
                        "     'His cock throbbed' -> 'Her pussy throbbed'\n"
                        "Words with no clean equivalent are still removed.\n"
                        "Has no effect when filter_anatomy is off."
                    ),
                }),
                # ── Clothing / Presentation ───────────────────────────────────
                "filter_presentation": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Process clothing and accessory language at all.\n"
                        "Turn off to leave all clothing language completely untouched.\n"
                        "Useful for crossdressing characters."
                    ),
                }),
                "swap_clothing": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Replace clothing terms with gender-appropriate equivalents\n"
                        "rather than removing them.\n"
                        "e.g. dress -> suit, skirt -> trousers,\n"
                        "     bra -> removed, bikini -> swim trunks\n"
                        "Has no effect when filter_presentation is off."
                    ),
                }),
                # ── Pronouns / References ─────────────────────────────────────
                "handle_pronouns": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Swap binary gendered pronouns.\n"
                        "she/her/hers/herself  <->  he/him/his/himself\n"
                        "spaCy correctly disambiguates 'her' between\n"
                        "possessive (-> his) and object (-> him)."
                    ),
                }),
                "rewrite_references": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Swap gendered nouns and adjectives.\n"
                        "woman/girl/lady/feminine  <->  man/boy/guy/masculine\n"
                        "Also covers furry terms: vixen/doe/mare/tigress etc.\n"
                        "Plus titles, family terms, and mythological figures."
                    ),
                }),
                "map_neopronouns": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Map neopronouns to binary equivalents image models recognise.\n"
                        "Covers: shi/hir (Chakat/furry), they/them, xe/xem,\n"
                        "ze/zir, ey/em (Spivak), fae/faer, ve/ver, per.\n"
                        "Plural they/them preserved by spaCy (regex is approximate).\n"
                        "When off, all neopronouns pass through unchanged."
                    ),
                }),
                # ── Safety ────────────────────────────────────────────────────
                "handle_negations": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Protect negated anatomy terms from removal or replacement.\n"
                        "e.g. 'no breasts' and 'without a vagina' are left untouched.\n"
                        "spaCy uses dependency parsing; regex uses 4-token heuristic."
                    ),
                }),
                # ── Backend ───────────────────────────────────────────────────
                "spacy_model": ("STRING", {
                    "default": "en_core_web_sm",
                    "tooltip": (
                        "spaCy model for NLP processing.\n"
                        "en_core_web_sm  ~12MB  - good for most cases (recommended)\n"
                        "en_core_web_md  ~43MB  - better word vectors\n"
                        "en_core_web_lg  ~560MB - best accuracy\n"
                        "Falls back to regex automatically if spaCy is not installed."
                    ),
                }),
            }
        }

    def run(self, text, mode, filter_anatomy, replace_anatomy,
            filter_presentation, swap_clothing, handle_pronouns,
            rewrite_references, map_neopronouns, handle_negations, spacy_model):
        filtered, backend = filter_nl_gender(
            text=text, mode=mode,
            filter_anatomy=filter_anatomy,
            replace_anatomy=replace_anatomy,
            filter_presentation=filter_presentation,
            swap_clothing=swap_clothing,
            handle_pronouns=handle_pronouns,
            rewrite_references=rewrite_references,
            map_neopronouns=map_neopronouns,
            handle_negations=handle_negations,
            spacy_model=spacy_model,
        )
        return (filtered, backend)


NODE_CLASS_MAPPINGS        = {"GenderNLFilter": GenderNLFilter}
NODE_DISPLAY_NAME_MAPPINGS = {"GenderNLFilter": "Gender NL Filter 🏳️‍🌈"}

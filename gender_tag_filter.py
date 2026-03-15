"""
gender_tag_filter.py - comfyui-gender-tag-filter: Gender Tag Filter Node
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

ComfyUI node (GenderTagFilter) that filters and replaces gendered vocabulary
in Danbooru and e621 style tag lists.

Designed to sit between a prompt expander (e.g. TIPO) and the CLIP encoder,
or as the first stage in a chained tag+NL pipeline followed by GenderNLFilter.

Tag processing runs in priority order: NL fragment detection, negation guard,
neopronoun mapping, anatomy replacement, exact blocklist match (with optional
clothing swap), compound root scan. Natural language fragments mixed into the
tag list by TIPO are detected via spaCy dependency parsing (stop-word heuristic
fallback) and passed through untouched so GenderNLFilter can handle them.

All data maps and utility functions are imported from gender_shared.py.

Controls
--------
mode                    : "off" | "strip_female_tags" | "strip_male_tags"

filter_anatomy          : bool (default True)
                          Remove anatomical tags. Also scans compound tags
                          for anatomy root words - huge_breasts, breast_grab
                          etc. are all caught even if not individually listed.

filter_presentation     : bool (default False)
                          Also remove gendered clothing/accessory tags.
                          Disable for crossdressing characters.

apply_replacements      : bool (default False)
                          Replace removed anatomy tags with gender-appropriate
                          counterparts. e.g. large_breasts -> muscular_chest

swap_clothing_tags      : bool (default True)
                          When filter_presentation is on, replace clothing tags
                          with equivalents rather than removing.
                          e.g. skirt -> trousers, bikini -> swim_trunks
                          Has no effect when filter_presentation is off.

map_neopronouns         : bool (default True)
                          Map neopronoun tags (shi, hir, they, xe, ze, ey, fae)
                          to binary equivalents that image models recognise.
                          Covers the same set as the NL filter so both nodes
                          behave consistently when used standalone.

handle_negations        : bool (default True)
                          Skip tags preceded by negation context.
                          e.g. a tag appearing after 'no' or 'without' in a
                          mixed prompt is left untouched.

tag_format              : "underscores" | "spaces"
                          Output word separator style.
                          NL fragments bypass this and keep original spacing.

delimiter               : str (default ", ")
                          Tag separator. Input is parsed forgivingly.

spacy_model             : str (default "en_core_web_sm")
                          Used for NL fragment detection.
                          Falls back to stop-word heuristic if not installed.
"""

import re
import logging

from .gender_shared import (
    load_spacy,
    preserve_case,
    make_swap_pattern,
    apply_swap_patterns,
    normalise_tag,
    format_tag,
    is_natural_language,
    is_negated_regex,
    NEGATION_WORDS,
    NEOPRONOUN_MAP,
    NEOPRONOUN_TAG_FORMS,
    FEMALE_ANATOMY_ROOTS,
    MALE_ANATOMY_ROOTS,
    FEMALE_ANATOMY,
    MALE_ANATOMY,
    FEMALE_PRESENTATION,
    MALE_PRESENTATION,
    FEMALE_TO_MALE_REPLACEMENTS,
    MALE_TO_FEMALE_REPLACEMENTS,
    FEMALE_TO_MALE_CLOTHING,
    MALE_TO_FEMALE_CLOTHING,
)

log = logging.getLogger(__name__)


def _tag_contains_root(tag_norm: str, root_set: set) -> bool:
    """
    Check whether any anatomy root word appears as a component of a
    compound tag. Splits on underscores to examine each part.
    e.g. huge_breasts -> "breasts" in roots -> True
    """
    return bool(set(tag_norm.split("_")) & root_set)


def filter_gender_tags(
    text: str,
    mode: str = "off",
    filter_anatomy: bool = True,
    filter_presentation: bool = False,
    apply_replacements: bool = False,
    swap_clothing_tags: bool = True,
    map_neopronouns: bool = True,
    handle_negations: bool = True,
    tag_format: str = "underscores",
    delimiter: str = ", ",
    spacy_model: str = "en_core_web_sm",
) -> str:
    if mode == "off" or not text.strip():
        return text

    split_char = delimiter.strip() or delimiter

    # Split on newlines first (hard boundary between tag section and NL prose),
    # then on the delimiter within each line.
    raw_chunks = re.split(r'\n+', text)
    raw_tags = []
    for chunk in raw_chunks:
        raw_tags.extend(t.strip() for t in chunk.split(split_char) if t.strip())

    if mode == "strip_female_tags":
        anatomy_blocklist    = FEMALE_ANATOMY
        presentation_blocklist = FEMALE_PRESENTATION
        replacement_map      = FEMALE_TO_MALE_REPLACEMENTS
        clothing_replacement = FEMALE_TO_MALE_CLOTHING
        anatomy_roots        = FEMALE_ANATOMY_ROOTS
        neo_index            = 0   # male target
    else:
        anatomy_blocklist    = MALE_ANATOMY
        presentation_blocklist = MALE_PRESENTATION
        replacement_map      = MALE_TO_FEMALE_REPLACEMENTS
        clothing_replacement = MALE_TO_FEMALE_CLOTHING
        anatomy_roots        = MALE_ANATOMY_ROOTS
        neo_index            = 1   # female target

    blocklist = set()
    if filter_anatomy:
        blocklist |= anatomy_blocklist
    if filter_presentation:
        blocklist |= presentation_blocklist

    # Build neopronoun swap map for this mode
    neo_swap = {k: v[neo_index] for k, v in NEOPRONOUN_MAP.items()}

    # Load spaCy for NL detection (silent fallback to heuristic on failure)
    nlp = load_spacy(spacy_model)

    def _format(tag: str) -> str:
        return format_tag(tag, tag_format)

    output_tags = []
    for tag in raw_tags:

        # ── NL detection ─────────────────────────────────────────────────
        # Natural language fragments pass through untouched for the NL filter.
        if is_natural_language(tag, nlp):
            output_tags.append(tag)
            continue

        tag_norm = normalise_tag(tag)

        # ── Negation guard ────────────────────────────────────────────────
        # Only applies to NL fragments - for standalone tags, a "no_breasts"
        # tag elsewhere in the list is an independent model instruction with
        # no grammatical relationship to a standalone "breasts" tag.
        # We detect NL context by checking if the tag itself contains a
        # negation word as a compound component (e.g. "no_breasts" starts
        # with "no") - those are Danbooru negation tags and won't be in the
        # blocklist anyway, so the guard only matters for mixed NL prompts
        # where a sentence like "without breasts" appears as a chunk.
        # We therefore only run the negation guard on multi-word chunks that
        # look like they could be part of a sentence rather than a pure tag.
        tag_words = tag_norm.replace("_", " ").split()
        if handle_negations and len(tag_words) > 1:
            if is_negated_regex(tag, tag_norm.replace("_", " ")):
                output_tags.append(_format(tag))
                continue

        # ── Neopronoun mapping ────────────────────────────────────────────
        if map_neopronouns and tag_norm in neo_swap:
            replacement = neo_swap[tag_norm]
            if replacement:
                output_tags.append(_format(replacement))
            continue

        # ── Anatomy replacement pass ──────────────────────────────────────
        if apply_replacements and tag_norm in replacement_map:
            replacement = replacement_map[tag_norm]
            if replacement:
                output_tags.append(_format(replacement))
            continue

        # ── Exact blocklist match ─────────────────────────────────────────
        if tag_norm in blocklist:
            if swap_clothing_tags and filter_presentation and tag_norm in clothing_replacement:
                replacement = clothing_replacement[tag_norm]
                if replacement:
                    output_tags.append(_format(replacement))
            continue

        # ── Compound tag root scan ────────────────────────────────────────
        if filter_anatomy and _tag_contains_root(tag_norm, anatomy_roots):
            continue

        # ── Tag survived ──────────────────────────────────────────────────
        output_tags.append(_format(tag))

    return delimiter.join(output_tags)


# ---------------------------------------------------------------------------
# ComfyUI node definition
# ---------------------------------------------------------------------------

class GenderTagFilter:
    CATEGORY = "utils/tags"
    FUNCTION = "run"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("filtered_tags",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "tooltip": "Tag string to filter. NL fragments are detected and preserved automatically.",
                }),
                "mode": (["off", "strip_female_tags", "strip_male_tags"], {
                    "default": "strip_female_tags",
                    "tooltip": (
                        "'strip_female_tags' -> remove female anatomy/presentation tags\n"
                        "'strip_male_tags'   -> remove male anatomy/presentation tags\n"
                        "'off'               -> pass through unchanged"
                    ),
                }),
                "filter_anatomy": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Remove explicit anatomical tags for the unwanted gender.\n"
                        "Also scans compound tags for anatomy root words, so\n"
                        "huge_breasts, breast_grab, hanging_breasts etc. are all\n"
                        "caught even if not individually listed."
                    ),
                }),
                "filter_presentation": ("BOOLEAN", {
                    "default": False,
                    "tooltip": (
                        "Also remove gendered clothing/accessory/makeup tags.\n"
                        "Disable for crossdressing characters."
                    ),
                }),
                "apply_replacements": ("BOOLEAN", {
                    "default": False,
                    "tooltip": (
                        "Replace removed anatomy tags with gender-appropriate\n"
                        "counterparts instead of just deleting them.\n"
                        "e.g. large_breasts -> muscular_chest, breasts -> pecs"
                    ),
                }),
                "swap_clothing_tags": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "When filter_presentation is on, replace clothing tags\n"
                        "with gender-appropriate equivalents instead of just removing.\n"
                        "e.g. skirt -> trousers, bikini -> swim_trunks,\n"
                        "     evening_gown -> tuxedo, bra -> removed (no equivalent)\n"
                        "Has no effect when filter_presentation is off."
                    ),
                }),
                "map_neopronouns": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Map neopronoun tags to binary equivalents that image\n"
                        "models are likely to recognise from their training data.\n"
                        "Covers: shi/hir (Chakat/furry), they/them, xe/xem,\n"
                        "ze/zir, ey/em (Spivak), fae/faer.\n"
                        "When off, neopronoun tags pass through unchanged."
                    ),
                }),
                "handle_negations": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Protect tags that appear in a negated context from removal.\n"
                        "e.g. in a mixed prompt, 'no breasts' will leave the tag\n"
                        "untouched rather than removing it.\n"
                        "Uses a 4-token proximity heuristic."
                    ),
                }),
                "tag_format": (["underscores", "spaces"], {
                    "default": "underscores",
                    "tooltip": (
                        "Word separator style expected by your model.\n"
                        "'underscores' -> big_breasts  (Danbooru/e621, most SDXL models)\n"
                        "'spaces'      -> big breasts  (some fine-tuned models)\n"
                        "Input tags are always accepted in either style.\n"
                        "Natural language fragments bypass this setting entirely."
                    ),
                }),
                "delimiter": ("STRING", {
                    "default": ", ",
                    "tooltip": (
                        "Separator used between output tags.\n"
                        "Input is parsed forgivingly - whitespace around tags\n"
                        "is stripped automatically."
                    ),
                }),
                "spacy_model": ("STRING", {
                    "default": "en_core_web_sm",
                    "tooltip": (
                        "spaCy model for NL fragment detection.\n"
                        "Falls back to stop-word heuristic if spaCy is not installed.\n"
                        "en_core_web_sm (~12MB) is sufficient for this purpose."
                    ),
                }),
            }
        }

    def run(self, text, mode, filter_anatomy, filter_presentation,
            apply_replacements, swap_clothing_tags, map_neopronouns,
            handle_negations, tag_format, delimiter, spacy_model):
        return (filter_gender_tags(
            text=text, mode=mode,
            filter_anatomy=filter_anatomy,
            filter_presentation=filter_presentation,
            apply_replacements=apply_replacements,
            swap_clothing_tags=swap_clothing_tags,
            map_neopronouns=map_neopronouns,
            handle_negations=handle_negations,
            tag_format=tag_format,
            delimiter=delimiter,
            spacy_model=spacy_model,
        ),)


NODE_CLASS_MAPPINGS      = {"GenderTagFilter": GenderTagFilter}
NODE_DISPLAY_NAME_MAPPINGS = {"GenderTagFilter": "Gender Tag Filter 🏳️‍🌈"}

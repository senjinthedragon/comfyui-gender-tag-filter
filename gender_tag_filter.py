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

Supports A1111/Forge emphasis syntax: (tag:1.3), ((tag)), [tag] are all
correctly parsed, filtered, and re-wrapped. LoRA syntax (<lora:name:weight>),
hypernetwork syntax, and the BREAK keyword are passed through untouched.

Tag processing runs in priority order: special syntax passthrough, NL fragment
detection, negation guard, neopronoun mapping, anatomy replacement, exact
blocklist match (with optional clothing swap), compound root scan. Natural
language fragments mixed into the tag list by TIPO are detected via spaCy
dependency parsing (stop-word heuristic fallback) and passed through untouched
so GenderNLFilter can handle them.

All data maps and utility functions are imported from gender_shared.py.

Controls
--------
mode                    : "off" | "strip_female_tags" | "strip_male_tags"

filter_anatomy          : bool (default True)
                          Remove anatomical tags. Also scans compound tags
                          for anatomy root words - huge_breasts, breast_grab
                          etc. are all caught even if not individually listed.

replace_anatomy         : bool (default False)
                          Replace removed anatomy tags with gender-appropriate
                          counterparts. e.g. large_breasts -> muscular_chest
                          Has no effect when filter_anatomy is off.

filter_presentation     : bool (default False)
                          Remove gendered clothing/accessory/makeup tags.
                          Disable for crossdressing characters.

swap_clothing           : bool (default True)
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

use_underscores         : bool (default True)
                          Output word separator style.
                          True -> underscores, False -> spaces.
                          NL fragments bypass this and keep original spacing.

spacy_nlp               : SPACY_NLP (optional)
                          Connect a SpaCy Model Loader node to enable spaCy-backed
                          NL fragment detection. Leave disconnected to use the
                          stop-word heuristic fallback instead.
"""

import re

from .gender_shared import (
    normalise_tag,
    format_tag,
    is_natural_language,
    is_negated_regex,
    is_special_syntax,
    is_break_keyword,
    unwrap_emphasis,
    rewrap_emphasis,
    NEOPRONOUN_MAP,
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
    FEMALE_TO_MALE_WORDS,
    MALE_TO_FEMALE_WORDS,
)

def _tag_contains_root(tag_norm: str, root_set: frozenset) -> bool:
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
    replace_anatomy: bool = False,
    filter_presentation: bool = False,
    swap_clothing: bool = True,
    use_underscores: bool = True,
    rewrite_references: bool = True,
    map_neopronouns: bool = True,
    handle_negations: bool = True,
    nlp=None,
) -> str:
    if mode == "off" or not text.strip():
        return text

    # Split on commas, strip surrounding whitespace from each tag.
    # Handles any spacing variant: "a, b", "a,b", "a ,  b" etc.
    raw_chunks = re.split(r'\n+', text)
    raw_tags = []
    for chunk in raw_chunks:
        raw_tags.extend(t.strip() for t in chunk.split(",") if t.strip())

    if mode == "strip_female_tags":
        anatomy_blocklist      = FEMALE_ANATOMY
        presentation_blocklist = FEMALE_PRESENTATION
        replacement_map        = FEMALE_TO_MALE_REPLACEMENTS
        clothing_replacement   = FEMALE_TO_MALE_CLOTHING
        anatomy_roots          = FEMALE_ANATOMY_ROOTS
        word_map               = FEMALE_TO_MALE_WORDS
        neo_index              = 0   # male target
    else:
        anatomy_blocklist      = MALE_ANATOMY
        presentation_blocklist = MALE_PRESENTATION
        replacement_map        = MALE_TO_FEMALE_REPLACEMENTS
        clothing_replacement   = MALE_TO_FEMALE_CLOTHING
        anatomy_roots          = MALE_ANATOMY_ROOTS
        word_map               = MALE_TO_FEMALE_WORDS
        neo_index              = 1   # female target

    blocklist = set()
    if filter_anatomy:
        blocklist |= anatomy_blocklist
    if filter_presentation:
        blocklist |= presentation_blocklist

    # Build neopronoun swap map for this mode
    neo_swap = {k: v[neo_index] for k, v in NEOPRONOUN_MAP.items()}

    def _format(tag: str) -> str:
        return format_tag(tag, "underscores" if use_underscores else "spaces")

    output_tags = []
    for tag in raw_tags:

        # ── Special syntax passthrough ────────────────────────────────
        # LoRA, hypernetwork, LyCORIS, embedding syntax and the BREAK
        # keyword are never filtered.
        if is_special_syntax(tag) or is_break_keyword(tag):
            output_tags.append(tag)
            continue

        # ── Emphasis unwrapping ───────────────────────────────────────
        # Strip (tag:1.3), ((tag)), [tag] etc. to get the inner tag for
        # matching, then re-wrap the result with the original emphasis.
        inner_tag, emph_prefix, emph_suffix = unwrap_emphasis(tag)

        # ── NL detection ─────────────────────────────────────────────
        # Natural language fragments pass through untouched for the NL filter.
        if is_natural_language(inner_tag, nlp):
            output_tags.append(tag)
            continue

        tag_norm = normalise_tag(inner_tag)

        # ── Negation guard ────────────────────────────────────────────
        # Only applies to multi-word chunks that could be part of a
        # sentence rather than a pure tag.
        tag_words = tag_norm.replace("_", " ").split()
        if handle_negations and len(tag_words) > 1:
            if is_negated_regex(inner_tag, tag_norm.replace("_", " ")):
                output_tags.append(rewrap_emphasis(_format(inner_tag), emph_prefix, emph_suffix))
                continue

        # ── Neopronoun mapping ────────────────────────────────────────
        if map_neopronouns and tag_norm in neo_swap:
            replacement = neo_swap[tag_norm]
            if replacement:
                output_tags.append(rewrap_emphasis(_format(replacement), emph_prefix, emph_suffix))
            continue

        # ── Anatomy replacement pass ──────────────────────────────────
        if replace_anatomy and tag_norm in replacement_map:
            replacement = replacement_map[tag_norm]
            if replacement:
                output_tags.append(rewrap_emphasis(_format(replacement), emph_prefix, emph_suffix))
            continue

        # ── Gendered word/reference replacement ───────────────────────
        # Catches standalone gendered noun tags: woman, girl, vixen, doe...
        if rewrite_references and tag_norm in word_map:
            replacement = word_map[tag_norm]
            if replacement:
                output_tags.append(rewrap_emphasis(_format(replacement), emph_prefix, emph_suffix))
            continue

        # ── Exact blocklist match ─────────────────────────────────────
        if tag_norm in blocklist:
            if swap_clothing and filter_presentation and tag_norm in clothing_replacement:
                replacement = clothing_replacement[tag_norm]
                if replacement:
                    output_tags.append(rewrap_emphasis(_format(replacement), emph_prefix, emph_suffix))
            continue

        # ── Compound tag root scan ────────────────────────────────────
        if filter_anatomy and _tag_contains_root(tag_norm, anatomy_roots):
            continue

        # ── Tag survived ──────────────────────────────────────────────
        output_tags.append(rewrap_emphasis(_format(inner_tag), emph_prefix, emph_suffix))

    return ", ".join(output_tags)


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
            "optional": {
                "spacy_nlp": ("SPACY_NLP", {
                    "tooltip": (
                        "Connect a SpaCy Model Loader node to enable spaCy-backed\n"
                        "NL fragment detection. Leave disconnected to use the\n"
                        "stop-word heuristic fallback instead."
                    ),
                }),
            },
            "required": {
                # ── Core ──────────────────────────────────────────────────────
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
                # ── Anatomy ───────────────────────────────────────────────────
                "filter_anatomy": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Remove explicit anatomical tags for the unwanted gender.\n"
                        "Also scans compound tags for anatomy root words, so\n"
                        "huge_breasts, breast_grab, hanging_breasts etc. are all\n"
                        "caught even if not individually listed."
                    ),
                }),
                "replace_anatomy": ("BOOLEAN", {
                    "default": False,
                    "tooltip": (
                        "Replace removed anatomy tags with gender-appropriate\n"
                        "counterparts instead of just deleting them.\n"
                        "e.g. large_breasts -> muscular_chest, breasts -> pecs\n"
                        "     1girl -> 1boy, yuri -> yaoi, cameltoe -> bulge\n"
                        "Has no effect when filter_anatomy is off."
                    ),
                }),
                # ── Clothing / Presentation ───────────────────────────────────
                "filter_presentation": ("BOOLEAN", {
                    "default": False,
                    "tooltip": (
                        "Remove gendered clothing, accessory, and makeup tags.\n"
                        "Disable for crossdressing characters."
                    ),
                }),
                "swap_clothing": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "When filter_presentation is on, replace clothing tags\n"
                        "with gender-appropriate equivalents instead of just removing.\n"
                        "e.g. skirt -> trousers, bikini -> swim_trunks,\n"
                        "     evening_gown -> tuxedo, bra -> removed (no equivalent)\n"
                        "Has no effect when filter_presentation is off."
                    ),
                }),
                # ── Output format ─────────────────────────────────────────────
                "use_underscores": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Output word separator style.\n"
                        "On  -> big_breasts  (Danbooru/e621, most SDXL models)\n"
                        "Off -> big breasts  (some fine-tuned models)\n"
                        "Input tags are always accepted in either style.\n"
                        "Natural language fragments bypass this setting entirely."
                    ),
                }),
                # ── References ────────────────────────────────────────────────
                "rewrite_references": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Swap standalone gendered noun tags.\n"
                        "woman -> man, girl -> boy, vixen -> fox, doe -> buck etc.\n"
                        "Covers the same word set as the NL Filter's rewrite_references\n"
                        "for consistent behaviour across both nodes."
                    ),
                }),
                # ── Pronouns ──────────────────────────────────────────────────
                "map_neopronouns": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Map neopronoun tags to binary equivalents that image\n"
                        "models are likely to recognise from their training data.\n"
                        "Covers: shi/hir (Chakat/furry), they/them, xe/xem,\n"
                        "ze/zir, ey/em (Spivak), fae/faer, ve/ver, per.\n"
                        "When off, neopronoun tags pass through unchanged."
                    ),
                }),
                # ── Safety ────────────────────────────────────────────────────
                "handle_negations": ("BOOLEAN", {
                    "default": True,
                    "tooltip": (
                        "Protect tags that appear in a negated context from removal.\n"
                        "e.g. in a mixed prompt, 'no breasts' will leave the tag\n"
                        "untouched rather than removing it.\n"
                        "Uses a 4-token proximity heuristic."
                    ),
                }),
            }
        }

    def run(self, text, mode, filter_anatomy, replace_anatomy,
            filter_presentation, swap_clothing, use_underscores, rewrite_references,
            map_neopronouns, handle_negations, spacy_nlp=None):
        filtered = filter_gender_tags(
            text=text, mode=mode,
            filter_anatomy=filter_anatomy,
            replace_anatomy=replace_anatomy,
            filter_presentation=filter_presentation,
            swap_clothing=swap_clothing,
            use_underscores=use_underscores,
            rewrite_references=rewrite_references,
            map_neopronouns=map_neopronouns,
            handle_negations=handle_negations,
            nlp=spacy_nlp,
        )
        return (filtered,)


NODE_CLASS_MAPPINGS      = {"GenderTagFilter": GenderTagFilter}
NODE_DISPLAY_NAME_MAPPINGS = {"GenderTagFilter": "Gender Tag Filter 🏳️‍🌈"}

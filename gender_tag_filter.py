"""
GenderTagFilter - ComfyUI Custom Node
======================================
Filters and/or replaces gendered Danbooru/e621 tags in a prompt string.

Controls
--------
mode                : "off" | "strip_female_tags" | "strip_male_tags"
                      Which tag category to filter out.
                      "strip_female_tags" → remove female anatomy/presentation tags
                      "strip_male_tags"   → remove male anatomy/presentation tags
                      "off"               → pass through unchanged

filter_anatomy      : bool  (default True)
                      Remove explicit anatomical tags for the filtered gender.
                      e.g. in male-mode: breasts, vagina, pussy, etc.

filter_presentation : bool  (default False)
                      Also remove gendered presentation/clothing/accessory tags.
                      e.g. in male-mode: lipstick, dress, bra, high_heels, etc.
                      Disable this if you want crossdressing characters to keep
                      their clothing tags.

apply_replacements  : bool  (default False)
                      Where a sensible opposite-gender counterpart exists,
                      substitute rather than just delete.
                      e.g. in male-mode: large_breasts -> muscular_chest,
                                         wide_hips     -> narrow_hips

tag_format          : "underscores" | "spaces"
                      The word separator style used by your model.
                      "underscores" -> big_breasts   (Danbooru/e621 default)
                      "spaces"      -> big breasts   (some fine-tuned models)
                      Affects both matching and output. Input tags are
                      normalised internally so either style is accepted
                      regardless of this setting.

delimiter           : str   (default ", ")
                      The separator used to rejoin output tags.
                      Input is split on the bare separator character(s)
                      with surrounding whitespace stripped automatically,
                      so "tag1,tag2" and "tag1, tag2" both parse correctly.

Installation
------------
Place this file in:
    ComfyUI/custom_nodes/gender_tag_filter/gender_tag_filter.py

And add an __init__.py next to it:
    from .gender_tag_filter import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

Then restart ComfyUI. The node will appear under "utils/tags" as
"Gender Tag Filter 🏳️‍🌈".
"""

# ---------------------------------------------------------------------------
# Tag lists
# ---------------------------------------------------------------------------

# --- Female anatomy tags (removed in male-mode) ---
FEMALE_ANATOMY = {
    "female",
    "girl",
    "woman",
    "breasts",
    "breast",
    "small_breasts",
    "medium_breasts",
    "large_breasts",
    "huge_breasts",
    "gigantic_breasts",
    "flat_chest",
    "flat_chested",
    "micro_breasts",
    "saggy_breasts",
    "perky_breasts",
    "breast_grab",
    "breast_squeeze",
    "breast_press",
    "breast_expansion",
    "breast_hold",
    "breast_lift",
    "bouncing_breasts",
    "jiggling_breasts",
    "topless_female",
    "nude_female",
    "nipples",  # kept separate - could be desired for male chest too; see note below
    "pussy",
    "vagina",
    "vulva",
    "labia",
    "clitoris",
    "clit",
    "female_pubic_hair",
    "female_genitalia",
    "uterus",
    "womb",
    "cervix",
    "ovaries",
    "vaginal",
    "vaginal_penetration",
    "vaginal_sex",
    "vaginal_insertion",
    "vaginal_fluid",
    "vaginal_juice",
    "femdom",
    "pregnant",
    "pregnancy",
    "pregnant_belly",  # biologically female in most contexts
    "lactation",
    "lactating",
    "milk",
    "breastfeeding",
    "nursing",
    "menstruation",
    "girl_on_top",
    "cowgirl_position",
    "reverse_cowgirl_position",  # female-implied positions
    "yuri",  # female/female
}

# --- Male anatomy tags (removed in female-mode) ---
MALE_ANATOMY = {
    "male",
    "boy",
    "man",
    "penis",
    "cock",
    "dick",
    "phallus",
    "erection",
    "boner",
    "balls",
    "testicles",
    "testes",
    "scrotum",
    "ballsack",
    "foreskin",
    "glans",
    "shaft",
    "male_genitalia",
    "male_pubic_hair",
    "cum",
    "cumshot",
    "ejaculation",
    "orgasm",
    "cum_on_body",
    "cum_inside",
    "cum_in_mouth",
    "cum_drip",
    "cum_string",
    "creampie",
    "internal_cumshot",
    "sheath",
    "knot",
    "knotted_penis",  # furry-specific
    "penile",
    "penile_penetration",
    "yaoi",  # male/male
    "bulge",
    "bulge_outline",
    "topless_male",
    "nude_male",
    "pecs",
    "muscular_chest",  # contextually male, but see note
    "bara",
    "maledom",
}

# --- Female presentation tags (removed in male-mode when filter_presentation=True) ---
FEMALE_PRESENTATION = {
    "lipstick",
    "lip_gloss",
    "makeup",
    "mascara",
    "eyeshadow",
    "blush",
    "foundation",
    "rouge",
    "beauty_mark",
    "mole_on_breast",
    "nail_polish",
    "painted_nails",
    "long_nails",
    "bra",
    "brassiere",
    "sports_bra",
    "bikini_top",
    "strapless_bra",
    "panties",
    "thong",
    "g-string",
    "lingerie",
    "underwear_female",
    "garter_belt",
    "garter",
    "stockings",
    "pantyhose",
    "nylons",
    "dress",
    "skirt",
    "miniskirt",
    "sundress",
    "evening_gown",
    "frilled_skirt",
    "pleated_skirt",
    "short_skirt",
    "high_heels",
    "heels",
    "stilettos",
    "wedge_heels",
    "feminine",
    "effeminate",
    "hair_bow",
    "hair_ribbon",
    "scrunchie",
    "female_swimwear",
    "bikini",
    "one-piece_swimsuit",
    "corset",
    "bustier",
    "chemise",
    "nightgown",
    "babydoll",
    "female_focus",
}

# --- Male presentation tags (removed in female-mode when filter_presentation=True) ---
MALE_PRESENTATION = {
    "tie",
    "necktie",
    "business_suit",
    "suit_and_tie",
    "masculine",
    "macho",
    "boxer_briefs",
    "jockstrap",
    "male_underwear",
    "chest_hair",
    "body_hair",
    "male_focus",
}

# --- Replacement maps (applied when apply_replacements=True) ---
# Format: { tag_to_replace: replacement_tag_or_None }
# None means "just remove, no replacement"

FEMALE_TO_MALE_REPLACEMENTS = {
    "large_breasts": "muscular_chest",
    "huge_breasts": "muscular_chest",
    "breasts": "pecs",
    "wide_hips": "narrow_hips",
    "hourglass_figure": "athletic_build",
    "slender": "lean",
    "feminine": "masculine",
    "girl": "male",
    "woman": "male",
    "female": "male",
    "yuri": "yaoi",
    "femdom": "maledom",
}

MALE_TO_FEMALE_REPLACEMENTS = {
    "pecs": "breasts",
    "muscular_chest": "large_breasts",
    "narrow_hips": "wide_hips",
    "athletic_build": "hourglass_figure",
    "masculine": "feminine",
    "boy": "female",
    "man": "female",
    "male": "female",
    "yaoi": "yuri",
    "maledom": "femdom",
}

# ---------------------------------------------------------------------------
# Core filtering function (importable / testable independently)
# ---------------------------------------------------------------------------


def filter_gender_tags(
    text: str,
    mode: str = "off",
    filter_anatomy: bool = True,
    filter_presentation: bool = False,
    apply_replacements: bool = False,
    tag_format: str = "underscores",
    delimiter: str = ", ",
) -> str:
    """
    Filter and/or replace gendered tags in a delimiter-separated tag string.

    Parameters
    ----------
    text               : Input tag string.
    mode               : "off", "strip_female_tags", or "strip_male_tags".
    filter_anatomy     : Remove anatomical tags for the unwanted gender.
    filter_presentation: Also remove presentation/clothing tags.
    apply_replacements : Replace some tags with gender-opposite equivalents.
    tag_format         : "underscores" or "spaces" - output word separator style.
    delimiter          : Tag separator for output (default ", ").
                         Input is always split on the delimiter's stripped form
                         so leading/trailing spaces around tags are handled
                         automatically.

    Returns
    -------
    Filtered tag string using the same delimiter.
    """
    if mode == "off" or not text.strip():
        return text

    # Split on the delimiter, stripping surrounding whitespace from every tag.
    # This makes "tag1,tag2" and "tag1, tag2" behave identically regardless
    # of what the user set as their delimiter.
    split_char = (
        delimiter.strip() or delimiter
    )  # fall back to full delimiter if it's all whitespace
    raw_tags = [t.strip() for t in text.split(split_char) if t.strip()]

    if mode == "strip_female_tags":
        anatomy_blocklist = FEMALE_ANATOMY
        presentation_blocklist = FEMALE_PRESENTATION
        replacement_map = FEMALE_TO_MALE_REPLACEMENTS
    else:  # mode == "strip_male_tags"
        anatomy_blocklist = MALE_ANATOMY
        presentation_blocklist = MALE_PRESENTATION
        replacement_map = MALE_TO_FEMALE_REPLACEMENTS

    # Build active blocklist
    blocklist = set()
    if filter_anatomy:
        blocklist |= anatomy_blocklist
    if filter_presentation:
        blocklist |= presentation_blocklist

    def normalise(tag: str) -> str:
        """Collapse both space and underscore variants to underscores for matching."""
        return tag.lower().replace(" ", "_")

    def format_tag(tag: str) -> str:
        """Apply the chosen output format to a tag."""
        if tag_format == "spaces":
            return tag.replace("_", " ")
        return tag.replace(" ", "_")  # underscores (default)

    output_tags = []
    for tag in raw_tags:
        tag_norm = normalise(tag)

        # Replacement pass (before blocklist - a replacement keeps the tag alive)
        if apply_replacements and tag_norm in replacement_map:
            replacement = replacement_map[tag_norm]
            if replacement:
                output_tags.append(format_tag(replacement))
            # replacement == None → drop silently
            continue

        # Blocklist pass
        if tag_norm in blocklist:
            continue  # drop tag

        # Tag survived - reformat and keep
        output_tags.append(format_tag(tag))

    return delimiter.join(output_tags)


# ---------------------------------------------------------------------------
# ComfyUI node definition
# ---------------------------------------------------------------------------


class GenderTagFilter:
    """
    ComfyUI node: Gender Tag Filter
    Removes and/or replaces gendered Danbooru/e621 tags.
    """

    CATEGORY = "utils/tags"
    FUNCTION = "run"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("filtered_tags",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "Comma-separated tag string to filter.",
                    },
                ),
                "mode": (
                    ["off", "strip_female_tags", "strip_male_tags"],
                    {
                        "default": "strip_female_tags",
                        "tooltip": (
                            "'strip_female_tags' → remove female anatomy/presentation tags\n"
                            "'strip_male_tags'   → remove male anatomy/presentation tags\n"
                            "'off'               → pass through unchanged"
                        ),
                    },
                ),
                "filter_anatomy": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": (
                            "Remove explicit anatomical tags for the unwanted gender.\n"
                            "e.g. in male-mode: breasts, vagina, pussy …"
                        ),
                    },
                ),
                "filter_presentation": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": (
                            "Also remove gendered clothing/accessory/makeup tags.\n"
                            "Disable for crossdressing characters.\n"
                            "e.g. in male-mode: bra, lipstick, high_heels, dress …"
                        ),
                    },
                ),
                "apply_replacements": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": (
                            "Replace some removed tags with gender-appropriate counterparts\n"
                            "instead of just deleting them.\n"
                            "e.g. in strip_female_tags mode: large_breasts -> muscular_chest"
                        ),
                    },
                ),
                "tag_format": (
                    ["underscores", "spaces"],
                    {
                        "default": "underscores",
                        "tooltip": (
                            "Word separator style expected by your model.\n"
                            "'underscores' -> big_breasts  (Danbooru/e621, most SDXL models)\n"
                            "'spaces'      -> big breasts  (some fine-tuned models)\n"
                            "Input tags are always accepted in either style regardless."
                        ),
                    },
                ),
                "delimiter": (
                    "STRING",
                    {
                        "default": ", ",
                        "tooltip": (
                            "Separator used between output tags.\n"
                            "Input is parsed forgivingly - leading/trailing spaces\n"
                            "around each tag are stripped automatically, so both\n"
                            "'tag1,tag2' and 'tag1, tag2' parse correctly."
                        ),
                    },
                ),
            }
        }

    def run(
        self,
        text: str,
        mode: str,
        filter_anatomy: bool,
        filter_presentation: bool,
        apply_replacements: bool,
        tag_format: str,
        delimiter: str,
    ) -> tuple:
        result = filter_gender_tags(
            text=text,
            mode=mode,
            filter_anatomy=filter_anatomy,
            filter_presentation=filter_presentation,
            apply_replacements=apply_replacements,
            tag_format=tag_format,
            delimiter=delimiter,
        )
        return (result,)


# ---------------------------------------------------------------------------
# ComfyUI registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "GenderTagFilter": GenderTagFilter,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GenderTagFilter": "Gender Tag Filter 🏳️‍🌈",
}

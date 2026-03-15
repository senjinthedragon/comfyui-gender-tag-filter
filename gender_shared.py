"""
gender_shared.py - comfyui-gender-tag-filter: Shared Data and Utilities
Copyright (c) 2026 Senjin the Dragon.
https://github.com/senjinthedragon/comfyui-gender-tag-filter
Licensed under the MIT License.
See LICENSE for full license information.

==========================================================================
IMPORTANT NOTE
==========================================================================
This module is a prompt engineering utility for AI image generation models.
Its sole purpose is to help these models produce output that matches the
user's intended scene by adjusting the vocabulary in the prompt string.

It makes no claims about gender identity, linguistics, or real people.
All word mappings are chosen purely on the basis of what AI image
generation models have been trained to recognise.
==========================================================================

Shared data maps and utility functions imported by all gender filter nodes
in this pack.
Do not import ComfyUI-specific code here.

Contains the spaCy lazy loader (cached per model name), tag normalisation,
NL/tag detection helpers, negation detection (both spaCy dependency-tree and
regex fallback), all pronoun maps, gendered noun/adjective maps, anatomy sets
and replacement maps (tag format and NL format), clothing swap maps (underscore
and space format), the full neopronoun map, and the dangling adjective pattern.

Adding a new tag, swap pair, or neopronoun in this file automatically applies
the change to all three nodes without touching their individual files.
"""

import re
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# spaCy lazy loader
# ---------------------------------------------------------------------------

_spacy_cache: dict = {}


def load_spacy(model_name: str):
    """
    Load a spaCy model by name. Caches per model name so switching the
    model string in the ComfyUI UI correctly loads the new model.
    Returns the model or None on failure.
    """
    if model_name in _spacy_cache:
        return _spacy_cache[model_name]

    try:
        import spacy  # noqa: PLC0415
        nlp = spacy.load(model_name)
        _spacy_cache[model_name] = nlp
        log.info(f"[GenderFilter] spaCy model '{model_name}' loaded.")
        return nlp
    except ImportError:
        log.warning(
            "[GenderFilter] spaCy is not installed. Using regex fallback.\n"
            "  Install with:\n"
            "    pip install spacy\n"
            "    python -m spacy download en_core_web_sm"
        )
    except OSError:
        log.warning(
            f"[GenderFilter] spaCy model '{model_name}' not found. "
            f"Using regex fallback.\n"
            f"  Install model with:\n"
            f"    python -m spacy download {model_name}"
        )

    _spacy_cache[model_name] = None
    return None


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def preserve_case(original: str, replacement: str) -> str:
    """Match the capitalisation style of the original word."""
    if not replacement:
        return replacement
    if original.isupper():
        return replacement.upper()
    if original[0].isupper():
        return replacement.capitalize()
    return replacement


def make_swap_pattern(word_map: dict) -> list:
    """
    Build (compiled_pattern, replacement_or_None) list from a word map.
    Sorted longest-key-first to avoid partial matches on shared substrings.
    """
    patterns = []
    for src, dst in sorted(word_map.items(), key=lambda x: -len(x[0])):
        pat = re.compile(r'\b' + re.escape(src) + r'\b', re.IGNORECASE)
        patterns.append((pat, dst))
    return patterns


def apply_swap_patterns(text: str, patterns: list) -> str:
    """Apply swap patterns preserving capitalisation; None replacement removes."""
    for pattern, replacement in patterns:
        if replacement is None:
            text = pattern.sub('', text)
        else:
            text = pattern.sub(
                lambda m, r=replacement: preserve_case(m.group(0), r),
                text
            )
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\s+([,.])', r'\1', text)
    text = re.sub(r',\s*,', ',', text)
    return text.strip()


def normalise_tag(tag: str) -> str:
    """
    Collapse spaces and underscores to underscores for map lookups.
    Backslash-escaped sequences (e.g. Danbooru \\( and \\)) are preserved.
    Uses regex to only replace spaces not preceded by a backslash.
    """
    # Replace backslash-space sequences temporarily to protect them
    protected = re.sub(r'\\(.)', r'BSESC\1BSESC', tag.lower())
    converted = protected.replace(" ", "_")
    return re.sub(r'BSESC(.)BSESC', r'\\\1', converted)


def format_tag(tag: str, tag_format: str) -> str:
    """
    Apply the chosen output format to a tag.
    Backslash-escaped sequences are preserved regardless of format.
    """
    protected = re.sub(r'\\(.)', r'BSESC\1BSESC', tag)
    if tag_format == "spaces":
        converted = protected.replace("_", " ")
    else:
        converted = protected.replace(" ", "_")
    return re.sub(r'BSESC(.)BSESC', r'\\\1', converted)


# ---------------------------------------------------------------------------
# NL / tag detection
# ---------------------------------------------------------------------------

NL_STOP_WORDS = {
    # Articles and copulas - never appear in Danbooru tags
    "a", "an", "the",
    "is", "was", "are", "were", "be", "been", "being",
    # Conjunctions that do NOT appear in Danbooru tag connectors.
    # Note: "with", "and", "or", "in", "on", "of", "at", "from", "by",
    # "up", "down", "out", "off", "away", "over", "under", "around"
    # are intentionally excluded - they are common in Danbooru compound
    # tags such as "furry with non-furry", "tongue out", "from behind",
    # "looking at viewer", "thumbs up", "bent over" etc.
    "but", "so", "yet", "nor",
    "through", "into", "between", "against",
    # Personal pronouns - these do not appear in Danbooru tags
    "he", "she", "they", "we", "you",
    "his", "her", "their", "its", "our", "your", "my",
    "him", "them", "us",
    "this", "that", "these", "those",
    "every", "either",
    # Verb forms that would never appear in a pure tag list
    "got", "had", "has", "have",
    "took", "stepped",
    "wore", "worn",
}


def is_natural_language(text: str, nlp=None) -> bool:
    """
    Return True if text looks like natural language rather than a tag.
    Uses spaCy dependency parsing when available, stop-word heuristic otherwise.
    """
    words = text.replace("_", " ").split()
    if len(words) <= 2:
        return False
    if {w.lower() for w in words} & NL_STOP_WORDS:
        return True
    if nlp is not None:
        doc = nlp(text.replace("_", " "))
        has_subject = any(t.dep_ in {"nsubj", "nsubjpass"} for t in doc)
        has_verb    = any(t.pos_ == "VERB" for t in doc)
        if has_subject and has_verb:
            return True
    if len(words) > 4:
        return True
    return False


def chunk_is_tag(text: str, nlp=None) -> bool:
    """
    Return True if text looks like a standalone tag rather than NL.
    Inverse of is_natural_language - used in the NL filter to skip
    chunks already handled by the tag filter.
    """
    words = text.replace("_", " ").split()
    if len(words) <= 2:
        return True
    if {w.lower() for w in words} & NL_STOP_WORDS:
        return False
    if nlp is not None:
        doc = nlp(text.replace("_", " "))
        has_subject = any(t.dep_ in {"nsubj", "nsubjpass"} for t in doc)
        has_verb    = any(t.pos_ == "VERB" for t in doc)
        if has_subject and has_verb:
            return False
    if len(words) > 3:
        return False
    return True


# ---------------------------------------------------------------------------
# Negation helpers
# ---------------------------------------------------------------------------

NEGATION_WORDS = {
    "no", "not", "without", "lacking", "never", "none",
    "doesn't", "don't", "didn't", "won't", "isn't", "aren't",
    "hasn't", "hadn't", "hardly", "barely", "scarcely",
}


def is_negated_regex(text: str, word: str) -> bool:
    """Heuristic: negation word within 4 tokens before target word."""
    pattern = re.compile(
        r'\b(' + '|'.join(re.escape(n) for n in NEGATION_WORDS) + r')'
        r'(\s+\w+){0,3}\s+\b' + re.escape(word) + r'\b',
        re.IGNORECASE
    )
    return bool(pattern.search(text))


def has_negation_ancestor(token) -> bool:
    """
    Check spaCy dependency tree for a negation relation affecting this token.
    spaCy marks negation modifiers with dep_ == 'neg'.
    """
    for child in token.head.children:
        if child.dep_ == "neg":
            return True
    for child in token.children:
        if child.dep_ == "neg":
            return True
    return False


# ---------------------------------------------------------------------------
# Neopronoun map
# ---------------------------------------------------------------------------
# Format: { neopronoun: (male_equivalent, female_equivalent) }
# Index 0 = male target (strip_female_* mode)
# Index 1 = female target (strip_male_* mode)
#
# All entries use space-separated form; normalise before lookup.

NEOPRONOUN_MAP = {
    # Chakat / hermaphrodite - very common in furry fandom
    "shi":          ("he",      "she"),
    "hir":          ("his",     "her"),
    "hirs":         ("his",     "hers"),
    "hirself":      ("himself", "herself"),
    # Singular they/them - plural handled separately via spaCy morphology
    "they":         ("he",      "she"),
    "them":         ("him",     "her"),
    "their":        ("his",     "her"),
    "theirs":       ("his",     "hers"),
    "themselves":   ("himself", "herself"),
    "themself":     ("himself", "herself"),
    # xe/xem/xyr
    "xe":           ("he",      "she"),
    "xem":          ("him",     "her"),
    "xyr":          ("his",     "her"),
    "xyrs":         ("his",     "hers"),
    "xemself":      ("himself", "herself"),
    # ze/zir
    "ze":           ("he",      "she"),
    "zir":          ("his",     "her"),
    "zirs":         ("his",     "hers"),
    "zirself":      ("himself", "herself"),
    # ey/em/eir - Spivak
    "ey":           ("he",      "she"),
    "em":           ("him",     "her"),
    "eir":          ("his",     "her"),
    "eirs":         ("his",     "hers"),
    "emself":       ("himself", "herself"),
    # fae/faer - fandom-specific
    "fae":          ("he",      "she"),
    "faer":         ("his",     "her"),
    "faers":        ("his",     "hers"),
    "faerself":     ("himself", "herself"),
    # Note: "it/its" intentionally excluded - overwhelmingly used for
    # objects and animals in model training data.
}

# Flat tag-format neopronoun blocklist for the tag filter.
# Maps normalised tag forms to their tuple index target.
NEOPRONOUN_TAG_FORMS = {normalise_tag(k) for k in NEOPRONOUN_MAP}


# ---------------------------------------------------------------------------
# Binary pronoun maps
# ---------------------------------------------------------------------------

FEMALE_TO_MALE_PRONOUNS = {
    "herself":  "himself",
    "she's":    "he's",
    "she":      "he",
    "her":      "his",
    "hers":     "his",
}

MALE_TO_FEMALE_PRONOUNS = {
    "himself":  "herself",
    "he's":     "she's",
    "he":       "she",
    "his":      "her",
    "him":      "her",
}


# ---------------------------------------------------------------------------
# Gendered noun / adjective maps
# ---------------------------------------------------------------------------

FEMALE_TO_MALE_WORDS = {
    "woman":        "man",
    "women":        "men",
    "girl":         "boy",
    "girls":        "boys",
    "lady":         "gentleman",
    "ladies":       "gentlemen",
    "female":       "male",
    "females":      "males",
    "gal":          "guy",
    "gals":         "guys",
    "girlfriend":   "boyfriend",
    "wife":         "husband",
    "mother":       "father",
    "mom":          "dad",
    "daughter":     "son",
    "sister":       "brother",
    "aunt":         "uncle",
    "niece":        "nephew",
    "mistress":     "master",
    "queen":        "king",
    "princess":     "prince",
    "goddess":      "god",
    "witch":        "warlock",
    "nun":          "monk",
    "heroine":      "hero",
    "waitress":     "waiter",
    "actress":      "actor",
    "busty":        "muscular",
    "buxom":        "muscular",
    "curvy":        "athletic",
    "voluptuous":   "athletic",
    "feminine":     "masculine",
    # Furry / fandom
    "vixen":        "fox",
    "doe":          "buck",
    "mare":         "stallion",
    "hen":          "rooster",
    "cow":          "bull",
    "ewe":          "ram",
    "tigress":      "tiger",
    "lioness":      "lion",
    "empress":      "emperor",
}

MALE_TO_FEMALE_WORDS = {
    "man":          "woman",
    "men":          "women",
    "boy":          "girl",
    "boys":         "girls",
    "gentleman":    "lady",
    "gentlemen":    "ladies",
    "male":         "female",
    "males":        "females",
    "guy":          "gal",
    "guys":         "gals",
    "boyfriend":    "girlfriend",
    "husband":      "wife",
    "father":       "mother",
    "dad":          "mom",
    "son":          "daughter",
    "brother":      "sister",
    "uncle":        "aunt",
    "nephew":       "niece",
    "master":       "mistress",
    "king":         "queen",
    "prince":       "princess",
    "god":          "goddess",
    "warlock":      "witch",
    "monk":         "nun",
    "hero":         "heroine",
    "waiter":       "waitress",
    "actor":        "actress",
    "muscular":     "busty",
    "masculine":    "feminine",
    "fox":          "vixen",
    "buck":         "doe",
    "stallion":     "mare",
    "rooster":      "hen",
    "bull":         "cow",
    "ram":          "ewe",
    "tiger":        "tigress",
    "lion":         "lioness",
    "emperor":      "empress",
}


# ---------------------------------------------------------------------------
# Anatomy sets and replacement maps
# ---------------------------------------------------------------------------

# Root words for compound tag scanning in the tag filter.
FEMALE_ANATOMY_ROOTS = {
    "breast", "breasts", "nipple", "nipples",
    "pussy", "vagina", "vulva", "labia", "clitoris", "clit",
    "womb", "uterus", "ovaries", "cervix",
}

MALE_ANATOMY_ROOTS = {
    "penis", "cock", "dick", "phallus", "erection", "boner",
    "balls", "testicles", "testes", "scrotum", "ballsack",
    "foreskin", "glans", "sheath", "knot",
}

# Full tag blocklists (exact normalised matches, underscore format)
FEMALE_ANATOMY = {
    "female", "girl", "woman",
    "breasts", "breast", "small_breasts", "medium_breasts", "large_breasts",
    "huge_breasts", "gigantic_breasts", "flat_chest", "flat_chested",
    "micro_breasts", "saggy_breasts", "perky_breasts", "breast_grab",
    "breast_squeeze", "breast_press", "breast_expansion", "breast_hold",
    "breast_lift", "bouncing_breasts", "jiggling_breasts",
    "topless_female", "nude_female",
    "nipples", "nipple",
    "pussy", "vagina", "vulva", "labia", "clitoris", "clit",
    "female_pubic_hair", "female_genitalia",
    "uterus", "womb", "cervix", "ovaries",
    "vaginal", "vaginal_penetration", "vaginal_sex", "vaginal_insertion",
    "vaginal_fluid", "vaginal_juice",
    "femdom",
    "pregnant", "pregnancy", "pregnant_belly",
    "lactation", "lactating", "milk", "breastfeeding", "nursing",
    "menstruation",
    "girl_on_top", "cowgirl_position", "reverse_cowgirl_position",
    "yuri",
}

MALE_ANATOMY = {
    "male", "boy", "man",
    "penis", "cock", "dick", "phallus", "erection", "boner",
    "balls", "testicles", "testes", "scrotum", "ballsack",
    "foreskin", "glans", "shaft",
    "male_genitalia", "male_pubic_hair",
    "cum", "cumshot", "ejaculation", "orgasm", "cum_on_body",
    "cum_inside", "cum_in_mouth", "cum_drip", "cum_string",
    "creampie", "internal_cumshot",
    "sheath", "knot", "knotted_penis",
    "penile", "penile_penetration",
    "yaoi",
    "bulge", "bulge_outline",
    "topless_male", "nude_male",
    "pecs", "muscular_chest",
    "bara",
    "maledom",
}

# NL anatomy sets (space format for prose matching)
FEMALE_ANATOMY_NL = {
    "breasts", "breast", "boobs", "boob", "tits", "tit",
    "nipples", "nipple",
    "pussy", "vagina", "vulva", "labia", "clitoris", "clit",
    "womb", "uterus", "ovaries",
    "hips",
}

MALE_ANATOMY_NL = {
    "penis", "cock", "dick", "phallus", "erection", "boner",
    "balls", "testicles", "scrotum",
    "foreskin", "glans",
    "sheath", "knot",
}

# Anatomy replacement maps for tag context
FEMALE_TO_MALE_REPLACEMENTS = {
    "large_breasts":    "muscular_chest",
    "huge_breasts":     "muscular_chest",
    "breasts":          "pecs",
    "wide_hips":        "narrow_hips",
    "hourglass_figure": "athletic_build",
    "slender":          "lean",
    "feminine":         "masculine",
    "girl":             "male",
    "woman":            "male",
    "female":           "male",
    "yuri":             "yaoi",
    "femdom":           "maledom",
}

MALE_TO_FEMALE_REPLACEMENTS = {
    "pecs":             "breasts",
    "muscular_chest":   "large_breasts",
    "narrow_hips":      "wide_hips",
    "athletic_build":   "hourglass_figure",
    "masculine":        "feminine",
    "boy":              "female",
    "man":              "female",
    "male":             "female",
    "yaoi":             "yuri",
    "maledom":          "femdom",
}

# Anatomy replacement maps for NL context
# None = no clean NL equivalent; remove instead.
FEMALE_ANATOMY_NL_REPLACEMENTS = {
    "breasts":  "pecs",
    "breast":   "pec",
    "boobs":    "pecs",
    "boob":     "pec",
    "tits":     "pecs",
    "tit":      "pec",
    "nipples":  "nipples",
    "nipple":   "nipple",
    "pussy":    None,
    "vagina":   None,
    "vulva":    None,
    "labia":    None,
    "clitoris": None,
    "clit":     None,
    "womb":     None,
    "uterus":   None,
    "ovaries":  None,
    "hips":     "hips",
}

MALE_ANATOMY_NL_REPLACEMENTS = {
    "penis":    None,
    "cock":     None,
    "dick":     None,
    "phallus":  None,
    "erection": None,
    "boner":    None,
    "balls":    None,
    "testicles": None,
    "scrotum":  None,
    "foreskin": None,
    "glans":    None,
    "sheath":   None,
    "knot":     None,
}


# ---------------------------------------------------------------------------
# Presentation / clothing tag lists and replacement maps
# ---------------------------------------------------------------------------

FEMALE_PRESENTATION = {
    "lipstick", "lip_gloss", "makeup", "mascara", "eyeshadow", "blush",
    "foundation", "rouge", "beauty_mark", "mole_on_breast",
    "nail_polish", "painted_nails", "long_nails",
    "bra", "brassiere", "sports_bra", "bikini_top", "strapless_bra",
    "panties", "thong", "g-string", "lingerie", "underwear_female",
    "garter_belt", "garter", "stockings", "pantyhose", "nylons",
    "dress", "skirt", "miniskirt", "sundress", "evening_gown",
    "frilled_skirt", "pleated_skirt", "short_skirt",
    "high_heels", "heels", "stilettos", "wedge_heels",
    "feminine", "effeminate",
    "hair_bow", "hair_ribbon", "scrunchie",
    "female_swimwear", "bikini", "one-piece_swimsuit",
    "corset", "bustier", "chemise", "nightgown", "babydoll",
    "female_focus",
}

MALE_PRESENTATION = {
    "tie", "necktie", "business_suit", "suit_and_tie",
    "masculine", "macho",
    "boxer_briefs", "jockstrap", "male_underwear",
    "chest_hair", "body_hair",
    "male_focus",
}

# Clothing replacement maps - tag format (underscores)
FEMALE_TO_MALE_CLOTHING = {
    "evening_gown":         "tuxedo",
    "one-piece_swimsuit":   "swim_trunks",
    "pencil_skirt":         "trousers",
    "pleated_skirt":        "trousers",
    "frilled_skirt":        "trousers",
    "short_skirt":          "shorts",
    "bikini_top":           "tank_top",
    "sports_bra":           None,
    "strapless_bra":        None,
    "garter_belt":          None,
    "high_heels":           "boots",
    "wedge_heels":          "boots",
    "hair_bow":             None,
    "hair_ribbon":          None,
    "dress":                "suit",
    "sundress":             "suit",
    "gown":                 "robe",
    "skirt":                "trousers",
    "miniskirt":            "shorts",
    "blouse":               "shirt",
    "bikini":               "swim_trunks",
    "female_swimwear":      "swim_trunks",
    "lingerie":             "underwear",
    "chemise":              "undershirt",
    "nightgown":            "pajamas",
    "babydoll":             "pajamas",
    "bra":                  None,
    "brassiere":            None,
    "panties":              None,
    "thong":                None,
    "g-string":             None,
    "underwear_female":     None,
    "corset":               None,
    "bustier":              None,
    "stockings":            "socks",
    "pantyhose":            None,
    "nylons":               None,
    "heels":                "boots",
    "stilettos":            "boots",
    "scrunchie":            None,
    "garter":               None,
    "feminine":             "masculine",
    "effeminate":           None,
    "female_focus":         "male_focus",
}

MALE_TO_FEMALE_CLOTHING = {
    "swim_trunks":          "bikini",
    "boxer_briefs":         None,
    "suit_and_tie":         "evening_gown",
    "tuxedo":               "evening_gown",
    "suit":                 "dress",
    "robe":                 "gown",
    "trousers":             "skirt",
    "shorts":               "miniskirt",
    "shirt":                "blouse",
    "pajamas":              "nightgown",
    "undershirt":           "chemise",
    "socks":                "stockings",
    "boots":                "high_heels",
    "jockstrap":            None,
    "male_underwear":       None,
    "boxer_briefs":         None,
    "chest_hair":           None,
    "body_hair":            None,
    "masculine":            "feminine",
    "macho":                None,
    "male_focus":           "female_focus",
}

# Clothing replacement maps - NL format (spaces)
CLOTHING_FEMALE_TO_MALE_NL = {
    "evening gown":         "tuxedo",
    "one-piece swimsuit":   "swim trunks",
    "pencil skirt":         "trousers",
    "pleated skirt":        "trousers",
    "frilled skirt":        "trousers",
    "bikini top":           "tank top",
    "bikini bottom":        "swim trunks",
    "sports bra":           None,
    "strapless bra":        None,
    "garter belt":          None,
    "high heels":           "boots",
    "wedge heels":          "boots",
    "platform heels":       "boots",
    "hair bow":             None,
    "hair ribbon":          None,
    "dress":                "suit",
    "gown":                 "robe",
    "skirt":                "trousers",
    "miniskirt":            "shorts",
    "blouse":               "shirt",
    "crop top":             "tank top",
    "tube top":             "tank top",
    "bikini":               "swim trunks",
    "swimsuit":             "swim trunks",
    "lingerie":             "underwear",
    "negligee":             "underwear",
    "chemise":              "undershirt",
    "nightgown":            "pajamas",
    "babydoll":             "pajamas",
    "bra":                  None,
    "brassiere":            None,
    "panties":              None,
    "thong":                None,
    "corset":               None,
    "bustier":              None,
    "stockings":            "socks",
    "pantyhose":            None,
    "nylons":               None,
    "heels":                "boots",
    "stilettos":            "boots",
    "scrunchie":            None,
    "garter":               None,
}

CLOTHING_MALE_TO_FEMALE_NL = {
    "swim trunks":          "bikini",
    "boxer briefs":         None,
    "suit and tie":         "evening gown",
    "tuxedo":               "evening gown",
    "suit":                 "dress",
    "robe":                 "gown",
    "trousers":             "skirt",
    "shorts":               "miniskirt",
    "shirt":                "blouse",
    "pajamas":              "nightgown",
    "undershirt":           "chemise",
    "underwear":            "lingerie",
    "socks":                "stockings",
    "boots":                "high heels",
    "jockstrap":            None,
    "boxers":               None,
}

# ---------------------------------------------------------------------------
# Dangling adjective pattern (used in NL anatomy removal)
# ---------------------------------------------------------------------------

DANGLING_ADJ_PATTERN = re.compile(
    r'\b(?:(?:large|huge|massive|tiny|small|big|gigantic|perky|saggy|'
    r'round|flat|firm|soft|hard|erect|throbbing|enormous|pert|'
    r'plump|supple|toned|shapely)(?:,\s*|\s+))+',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# spaCy plural they/them detection
# ---------------------------------------------------------------------------

def is_plural_they(token) -> bool:
    """
    Distinguish singular they (gender-neutral pronoun) from plural they.
    Returns True when plural - leave untouched.
    """
    number = token.morph.get("Number")
    if number and "Plur" in number:
        return True
    if token.text.lower() in {"they", "them", "their", "theirs", "themselves"}:
        subject_count = sum(
            1 for t in token.sent
            if t.dep_ in {"nsubj", "nsubjpass"} and t.pos_ == "NOUN"
        )
        if subject_count > 1:
            return True
    return False

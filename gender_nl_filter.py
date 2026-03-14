"""
GenderNLFilter - ComfyUI Custom Node
======================================
Filters and rewrites gendered language in natural language prompts,
or in mixed prompts containing both tags and natural language fragments.

Designed to chain after GenderTagFilter for mixed-content pipelines:

    [prompt] -> GenderTagFilter -> GenderNLFilter -> CLIPTextEncodeSDXL

Both nodes accept and output STRING, so they wire together naturally.

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

Controls
--------
mode                        : "off" | "strip_female_language" | "strip_male_language"
                              Which gendered vocabulary to rewrite.

handle_negations            : bool (default True)
                              Protect negated anatomy terms from removal.
                              e.g. "no breasts", "without a vagina"
                              Requires spaCy for full accuracy; the regex
                              fallback uses a 4-token proximity heuristic.

handle_pronouns             : bool (default True)
                              Swap binary gendered pronouns and possessives.
                              she/her/hers/herself  <->  he/him/his/himself

rewrite_references          : bool (default True)
                              Swap gendered nouns and adjectives.
                              woman/girl/female  <->  man/boy/male  etc.
                              Also covers furry-specific terms.

swap_clothing               : bool (default True)
                              Replace gendered clothing terms with equivalents,
                              or remove them where no clean equivalent exists.
                              e.g. dress -> suit, skirt -> trousers,
                                   bra -> removed, bikini -> swim trunks

map_neopronouns_to_binary   : bool (default True)
                              Map neopronouns and gender-neutral pronouns to
                              binary equivalents that AI image generation models
                              are likely to recognise from their training data.
                              Covers: shi/hir (Chakat/furry), they/them,
                              xe/xem, ze/zir, ey/em (Spivak), fae/faer.
                              Singular they/them is remapped; plural they/them
                              is detected by spaCy and left untouched (the regex
                              fallback cannot reliably make this distinction).
                              When off, all neopronouns pass through unchanged.

spacy_model                 : str (default "en_core_web_sm")
                              spaCy model to use for NLP processing.
                              "en_core_web_sm"  ~12MB  - good for most cases
                              "en_core_web_md"  ~43MB  - better word vectors
                              "en_core_web_lg"  ~560MB - best accuracy
                              Falls back to regex if spaCy is not installed.

Installation
------------
Place this file alongside gender_tag_filter.py in:
    ComfyUI/custom_nodes/gender_tag_filter/

Installing spaCy (recommended):
    pip install spacy
    python -m spacy download en_core_web_sm

The node works without spaCy but negation detection and plural they/them
disambiguation will be less accurate.
"""

import logging
import re

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# spaCy lazy loader
# ---------------------------------------------------------------------------

_spacy_cache: dict = {}


def _load_spacy(model_name: str):
    """
    Attempt to load a spaCy model. Returns the model or None on failure.
    Cached so the model loads only once per ComfyUI session.
    """
    if model_name in _spacy_cache:
        return _spacy_cache[model_name]

    try:
        import spacy  # noqa: PLC0415

        nlp = spacy.load(model_name)
        _spacy_cache[model_name] = nlp
        log.info(f"[GenderNLFilter] spaCy model '{model_name}' loaded.")
        return nlp
    except ImportError:
        log.warning(
            "[GenderNLFilter] spaCy is not installed. Using regex fallback.\n"
            "  Install with:\n"
            "    pip install spacy\n"
            "    python -m spacy download en_core_web_sm"
        )
    except OSError:
        log.warning(
            f"[GenderNLFilter] spaCy model '{model_name}' not found. "
            f"Using regex fallback.\n"
            f"  Install model with:\n"
            f"    python -m spacy download {model_name}"
        )

    _spacy_cache[model_name] = None
    return None


# ---------------------------------------------------------------------------
# Binary pronoun maps
# ---------------------------------------------------------------------------

FEMALE_TO_MALE_PRONOUNS = {
    "herself": "himself",
    "she's": "he's",
    "she": "he",
    "her": "his",
    "hers": "his",
}

MALE_TO_FEMALE_PRONOUNS = {
    "himself": "herself",
    "he's": "she's",
    "he": "she",
    "his": "her",
    "him": "her",
}

# ---------------------------------------------------------------------------
# Neopronoun map
# ---------------------------------------------------------------------------
# Maps neopronouns and gender-neutral pronouns to binary equivalents.
# Chosen purely on the basis of what AI image generation models recognise.
#
# Format: { neopronoun: (male_equivalent, female_equivalent) }
# Index 0 = male target (used in strip_female_language mode)
# Index 1 = female target (used in strip_male_language mode)

NEOPRONOUN_MAP = {
    # Chakat / hermaphrodite pronouns - very common in furry fandom writing
    "shi": ("he", "she"),
    "hir": ("his", "her"),
    "hirs": ("his", "hers"),
    "hirself": ("himself", "herself"),
    # Singular they/them - gender-neutral, mainstream usage
    # Plural they/them is handled separately via spaCy morphology check.
    "they": ("he", "she"),
    "them": ("him", "her"),
    "their": ("his", "her"),
    "theirs": ("his", "hers"),
    "themselves": ("himself", "herself"),
    "themself": ("himself", "herself"),
    # xe/xem/xyr set
    "xe": ("he", "she"),
    "xem": ("him", "her"),
    "xyr": ("his", "her"),
    "xyrs": ("his", "hers"),
    "xemself": ("himself", "herself"),
    # ze/zir set
    "ze": ("he", "she"),
    "zir": ("his", "her"),
    "zirs": ("his", "hers"),
    "zirself": ("himself", "herself"),
    # ey/em/eir - Spivak pronouns
    "ey": ("he", "she"),
    "em": ("him", "her"),
    "eir": ("his", "her"),
    "eirs": ("his", "hers"),
    "emself": ("himself", "herself"),
    # fae/faer - fandom-specific
    "fae": ("he", "she"),
    "faer": ("his", "her"),
    "faers": ("his", "hers"),
    "faerself": ("himself", "herself"),
    # Note: "it/its" as a chosen pronoun is intentionally excluded.
    # It is overwhelmingly used for objects and animals in model training
    # data, making remapping it unreliable and potentially harmful to output.
}

# ---------------------------------------------------------------------------
# Gendered noun / adjective maps
# ---------------------------------------------------------------------------

FEMALE_TO_MALE_WORDS = {
    "woman": "man",
    "women": "men",
    "girl": "boy",
    "girls": "boys",
    "lady": "gentleman",
    "ladies": "gentlemen",
    "female": "male",
    "females": "males",
    "gal": "guy",
    "gals": "guys",
    "girlfriend": "boyfriend",
    "wife": "husband",
    "mother": "father",
    "mom": "dad",
    "daughter": "son",
    "sister": "brother",
    "aunt": "uncle",
    "niece": "nephew",
    "mistress": "master",
    "queen": "king",
    "princess": "prince",
    "goddess": "god",
    "witch": "warlock",
    "nun": "monk",
    "heroine": "hero",
    "waitress": "waiter",
    "actress": "actor",
    "busty": "muscular",
    "buxom": "muscular",
    "curvy": "athletic",
    "voluptuous": "athletic",
    "feminine": "masculine",
    # Furry / fandom specific
    "vixen": "fox",
    "doe": "buck",
    "mare": "stallion",
    "hen": "rooster",
    "cow": "bull",
    "ewe": "ram",
    "tigress": "tiger",
    "lioness": "lion",
    "empress": "emperor",
}

MALE_TO_FEMALE_WORDS = {
    "man": "woman",
    "men": "women",
    "boy": "girl",
    "boys": "girls",
    "gentleman": "lady",
    "gentlemen": "ladies",
    "male": "female",
    "males": "females",
    "guy": "gal",
    "guys": "gals",
    "boyfriend": "girlfriend",
    "husband": "wife",
    "father": "mother",
    "dad": "mom",
    "son": "daughter",
    "brother": "sister",
    "uncle": "aunt",
    "nephew": "niece",
    "master": "mistress",
    "king": "queen",
    "prince": "princess",
    "god": "goddess",
    "warlock": "witch",
    "monk": "nun",
    "hero": "heroine",
    "waiter": "waitress",
    "actor": "actress",
    "muscular": "busty",
    "masculine": "feminine",
    "fox": "vixen",
    "buck": "doe",
    "stallion": "mare",
    "rooster": "hen",
    "bull": "cow",
    "ram": "ewe",
    "tiger": "tigress",
    "lion": "lioness",
    "emperor": "empress",
}

# ---------------------------------------------------------------------------
# Clothing swap maps
# ---------------------------------------------------------------------------
# Format: { source_term: replacement_or_None }
# None = remove entirely (no clean model-recognisable equivalent exists).
# Multi-word terms are matched before single-word terms (longest key first).

CLOTHING_FEMALE_TO_MALE = {
    # Multi-word terms first
    "evening gown": "tuxedo",
    "one-piece swimsuit": "swim trunks",
    "pencil skirt": "trousers",
    "pleated skirt": "trousers",
    "frilled skirt": "trousers",
    "bikini top": "tank top",
    "bikini bottom": "swim trunks",
    "sports bra": None,
    "strapless bra": None,
    "garter belt": None,
    "high heels": "boots",
    "wedge heels": "boots",
    "platform heels": "boots",
    "hair bow": None,
    "hair ribbon": None,
    # Single-word terms
    "dress": "suit",
    "gown": "robe",
    "skirt": "trousers",
    "miniskirt": "shorts",
    "blouse": "shirt",
    "crop top": "tank top",
    "tube top": "tank top",
    "bikini": "swim trunks",
    "swimsuit": "swim trunks",
    "lingerie": "underwear",
    "negligee": "underwear",
    "chemise": "undershirt",
    "nightgown": "pajamas",
    "babydoll": "pajamas",
    "bra": None,
    "brassiere": None,
    "panties": None,
    "thong": None,
    "corset": None,
    "bustier": None,
    "stockings": "socks",
    "pantyhose": None,
    "nylons": None,
    "heels": "boots",
    "stilettos": "boots",
    "scrunchie": None,
    "garter": None,
}

CLOTHING_MALE_TO_FEMALE = {
    # Multi-word terms first
    "swim trunks": "bikini",
    "boxer briefs": None,
    "suit and tie": "evening gown",
    # Single-word terms
    "tuxedo": "evening gown",
    "suit": "dress",
    "robe": "gown",
    "trousers": "skirt",
    "shorts": "miniskirt",
    "shirt": "blouse",
    "blouse": "blouse",  # already female; no-op
    "pajamas": "nightgown",
    "undershirt": "chemise",
    "underwear": "lingerie",
    "socks": "stockings",
    "boots": "high heels",
    "jockstrap": None,
    "boxers": None,
}

# ---------------------------------------------------------------------------
# Anatomy sets (natural language - spaces not underscores)
# ---------------------------------------------------------------------------

FEMALE_ANATOMY_NL = {
    "breasts",
    "breast",
    "boobs",
    "boob",
    "tits",
    "tit",
    "nipples",
    "nipple",
    "pussy",
    "vagina",
    "vulva",
    "labia",
    "clitoris",
    "clit",
    "womb",
    "uterus",
    "ovaries",
    "hips",
}

MALE_ANATOMY_NL = {
    "penis",
    "cock",
    "dick",
    "phallus",
    "erection",
    "boner",
    "balls",
    "testicles",
    "scrotum",
    "foreskin",
    "glans",
    "sheath",
    "knot",
}

# Adjectives that may dangle after their anatomy noun is removed
DANGLING_ADJ_PATTERN = re.compile(
    r"\b(large|huge|massive|tiny|small|big|gigantic|perky|saggy|"
    r"round|flat|firm|soft|hard|erect|throbbing|enormous|pert|"
    r"plump|supple|toned|shapely)\s+$",
    re.IGNORECASE,
)

NEGATION_WORDS = {
    "no",
    "not",
    "without",
    "lacking",
    "never",
    "none",
    "doesn't",
    "don't",
    "didn't",
    "won't",
    "isn't",
    "aren't",
    "hasn't",
    "hadn't",
    "hardly",
    "barely",
    "scarcely",
}

# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


def _preserve_case(original: str, replacement: str) -> str:
    """Match the capitalisation style of the original word."""
    if not replacement:
        return replacement
    if original.isupper():
        return replacement.upper()
    if original[0].isupper():
        return replacement.capitalize()
    return replacement


def _make_swap_pattern(word_map: dict) -> list:
    """
    Build (compiled_pattern, replacement_or_None) list.
    Sorted longest-key-first to avoid partial matches.
    """
    patterns = []
    for src, dst in sorted(word_map.items(), key=lambda x: -len(x[0])):
        pat = re.compile(r"\b" + re.escape(src) + r"\b", re.IGNORECASE)
        patterns.append((pat, dst))
    return patterns


def _apply_swap_patterns(text: str, patterns: list) -> str:
    """Apply swap patterns preserving capitalisation; None replacement removes."""
    for pattern, replacement in patterns:
        if replacement is None:
            text = pattern.sub("", text)
        else:
            text = pattern.sub(
                lambda m, r=replacement: _preserve_case(m.group(0), r), text
            )
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.])", r"\1", text)
    text = re.sub(r",\s*,", ",", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Regex fallback
# ---------------------------------------------------------------------------


def _is_negated_regex(text: str, word: str) -> bool:
    """Heuristic: negation word within 4 tokens before target word."""
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(n) for n in NEGATION_WORDS) + r")"
        r"(\s+\w+){0,3}\s+\b" + re.escape(word) + r"\b",
        re.IGNORECASE,
    )
    return bool(pattern.search(text))


def _remove_anatomy_regex(text: str, anatomy_set: set, handle_negations: bool) -> str:
    for word in sorted(anatomy_set, key=len, reverse=True):
        pat = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        if not pat.search(text):
            continue
        if handle_negations and _is_negated_regex(text, word):
            continue
        # Remove any dangling adjective immediately before the word
        text = re.sub(
            DANGLING_ADJ_PATTERN.pattern + re.escape(word),
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = pat.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.])", r"\1", text)
    text = re.sub(r",\s*,", ",", text)
    return text.strip()


def _process_regex(
    text: str,
    mode: str,
    handle_negations: bool,
    handle_pronouns: bool,
    rewrite_references: bool,
    swap_clothing: bool,
    map_neopronouns: bool,
) -> str:
    if mode == "strip_female_language":
        pronoun_map = FEMALE_TO_MALE_PRONOUNS
        word_map = FEMALE_TO_MALE_WORDS
        anatomy_set = FEMALE_ANATOMY_NL
        clothing_map = CLOTHING_FEMALE_TO_MALE
        neo_index = 0
    else:
        pronoun_map = MALE_TO_FEMALE_PRONOUNS
        word_map = MALE_TO_FEMALE_WORDS
        anatomy_set = MALE_ANATOMY_NL
        clothing_map = CLOTHING_MALE_TO_FEMALE
        neo_index = 1

    # Step 1 - anatomy removal
    text = _remove_anatomy_regex(text, anatomy_set, handle_negations)

    # Step 2 - clothing swaps
    if swap_clothing:
        text = _apply_swap_patterns(text, _make_swap_pattern(clothing_map))

    # Step 3 - neopronoun mapping (must run before binary pronouns)
    if map_neopronouns:
        neo_swap = {k: v[neo_index] for k, v in NEOPRONOUN_MAP.items()}
        text = _apply_swap_patterns(text, _make_swap_pattern(neo_swap))

    # Step 4 - binary pronoun swap
    if handle_pronouns:
        text = _apply_swap_patterns(text, _make_swap_pattern(pronoun_map))

    # Step 5 - gendered nouns / adjectives
    if rewrite_references:
        text = _apply_swap_patterns(text, _make_swap_pattern(word_map))

    return text


# ---------------------------------------------------------------------------
# spaCy processing
# ---------------------------------------------------------------------------


def _has_negation_ancestor(token) -> bool:
    """Check dependency tree for a negation relation affecting this token."""
    for child in token.head.children:
        if child.dep_ == "neg":
            return True
    for child in token.children:
        if child.dep_ == "neg":
            return True
    return False


def _is_plural_they(token) -> bool:
    """
    Use spaCy morphology to distinguish singular they (gender-neutral pronoun)
    from plural they (multiple subjects). Returns True when plural - in which
    case the token should be left untouched.
    """
    number = token.morph.get("Number")
    if number and "Plur" in number:
        return True
    # Secondary heuristic: count distinct noun phrase subjects in the sentence
    if token.text.lower() in {"they", "them", "their", "theirs", "themselves"}:
        subject_count = sum(
            1
            for t in token.sent
            if t.dep_ in {"nsubj", "nsubjpass"} and t.pos_ == "NOUN"
        )
        if subject_count > 1:
            return True
    return False


def _process_spacy(
    text: str,
    nlp,
    mode: str,
    handle_negations: bool,
    handle_pronouns: bool,
    rewrite_references: bool,
    swap_clothing: bool,
    map_neopronouns: bool,
) -> str:
    if mode == "strip_female_language":
        pronoun_map = FEMALE_TO_MALE_PRONOUNS
        word_map = MALE_TO_FEMALE_WORDS  # intentional: we're removing female refs
        anatomy_set = FEMALE_ANATOMY_NL
        clothing_map = CLOTHING_FEMALE_TO_MALE
        neo_index = 0
    else:
        pronoun_map = MALE_TO_FEMALE_PRONOUNS
        word_map = FEMALE_TO_MALE_WORDS
        anatomy_set = MALE_ANATOMY_NL
        clothing_map = CLOTHING_MALE_TO_FEMALE
        neo_index = 1

    # Fix word_map assignment - should match mode
    if mode == "strip_female_language":
        word_map = FEMALE_TO_MALE_WORDS
    else:
        word_map = MALE_TO_FEMALE_WORDS

    neo_swap = {k: v[neo_index] for k, v in NEOPRONOUN_MAP.items()}

    # Build the clothing lookup with longest-first ordering
    clothing_sorted = sorted(clothing_map.items(), key=lambda x: -len(x[0]))

    doc = nlp(text)
    result_tokens = []

    for i, token in enumerate(doc):
        token_lower = token.text.lower()
        ws = token.whitespace_

        # ── Anatomy removal ──────────────────────────────────────────────
        if token_lower in anatomy_set:
            if handle_negations and _has_negation_ancestor(token):
                result_tokens.append(token.text_with_ws)
            else:
                # Remove dangling adjective from previous token if present
                if result_tokens and i > 0:
                    prev = doc[i - 1]
                    if prev.pos_ == "ADJ" and prev.head.i == token.i:
                        result_tokens.pop()
                        if result_tokens and result_tokens[-1].strip() == "":
                            result_tokens.pop()
                result_tokens.append(ws)
            continue

        # ── Clothing swaps ───────────────────────────────────────────────
        # Multi-word clothing terms need a lookahead check
        if swap_clothing:
            matched_clothing = False
            for src, dst in clothing_sorted:
                src_tokens = src.split()
                if len(src_tokens) > 1:
                    # Check if this token starts a multi-word match
                    end = i + len(src_tokens)
                    if end <= len(doc):
                        span = " ".join(t.text.lower() for t in doc[i:end])
                        if span == src:
                            if dst:
                                result_tokens.append(
                                    _preserve_case(token.text, dst)
                                    + doc[end - 1].whitespace_
                                )
                            else:
                                result_tokens.append(doc[end - 1].whitespace_)
                            # We need to skip the remaining tokens of the span.
                            # We do this by appending empty strings for them.
                            # Store skip count in a local variable processed below.
                            for skip_tok in doc[i + 1 : end]:
                                result_tokens.append("")
                            matched_clothing = True
                            break
                else:
                    if token_lower == src:
                        if dst:
                            result_tokens.append(_preserve_case(token.text, dst) + ws)
                        else:
                            result_tokens.append(ws)
                        matched_clothing = True
                        break
            if matched_clothing:
                continue

        # ── Neopronoun mapping ───────────────────────────────────────────
        if map_neopronouns and token_lower in neo_swap:
            if token_lower in {
                "they",
                "them",
                "their",
                "theirs",
                "themselves",
                "themself",
            }:
                if _is_plural_they(token):
                    result_tokens.append(token.text_with_ws)
                    continue
            replacement = neo_swap[token_lower]
            result_tokens.append(_preserve_case(token.text, replacement) + ws)
            continue

        # ── Binary pronoun swap ──────────────────────────────────────────
        if handle_pronouns and token_lower in pronoun_map:
            replacement = pronoun_map[token_lower]
            result_tokens.append(_preserve_case(token.text, replacement) + ws)
            continue

        # ── Gendered noun / adjective swap ───────────────────────────────
        if rewrite_references and token_lower in word_map:
            replacement = word_map[token_lower]
            result_tokens.append(_preserve_case(token.text, replacement) + ws)
            continue

        # ── Unchanged ────────────────────────────────────────────────────
        result_tokens.append(token.text_with_ws)

    text_out = "".join(result_tokens)
    text_out = re.sub(r"[ \t]{2,}", " ", text_out)
    text_out = re.sub(r"\s+([,.])", r"\1", text_out)
    text_out = re.sub(r",\s*,", ",", text_out)
    return text_out.strip()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def filter_nl_gender(
    text: str,
    mode: str = "off",
    handle_negations: bool = True,
    handle_pronouns: bool = True,
    rewrite_references: bool = True,
    swap_clothing: bool = True,
    map_neopronouns: bool = True,
    spacy_model: str = "en_core_web_sm",
) -> tuple:
    """
    Filter gendered natural language in a prompt string.
    Returns (filtered_text, backend_used).
    backend_used is "spacy", "regex", or "off".
    """
    if mode == "off" or not text.strip():
        return text, "off"

    nlp = _load_spacy(spacy_model)

    if nlp is not None:
        result = _process_spacy(
            text=text,
            nlp=nlp,
            mode=mode,
            handle_negations=handle_negations,
            handle_pronouns=handle_pronouns,
            rewrite_references=rewrite_references,
            swap_clothing=swap_clothing,
            map_neopronouns=map_neopronouns,
        )
        return result, "spacy"
    else:
        result = _process_regex(
            text=text,
            mode=mode,
            handle_negations=handle_negations,
            handle_pronouns=handle_pronouns,
            rewrite_references=rewrite_references,
            swap_clothing=swap_clothing,
            map_neopronouns=map_neopronouns,
        )
        return result, "regex"


# ---------------------------------------------------------------------------
# ComfyUI node definition
# ---------------------------------------------------------------------------


class GenderNLFilter:
    """
    ComfyUI node: Gender Natural Language Filter
    Rewrites gendered vocabulary in natural language prompts or mixed
    tag+NL prompts. Chain after GenderTagFilter for full coverage.
    Uses spaCy for accurate negation detection and pronoun disambiguation,
    with automatic regex fallback if spaCy is not installed.
    """

    CATEGORY = "utils/tags"
    FUNCTION = "run"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("filtered_text", "backend_used")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": (
                            "Natural language prompt, tag list, or mixed content.\n"
                            "Chain after GenderTagFilter for full tag+NL coverage."
                        ),
                    },
                ),
                "mode": (
                    ["off", "strip_female_language", "strip_male_language"],
                    {
                        "default": "strip_female_language",
                        "tooltip": (
                            "'strip_female_language' -> rewrite female-coded vocabulary\n"
                            "'strip_male_language'   -> rewrite male-coded vocabulary\n"
                            "'off'                   -> pass through unchanged"
                        ),
                    },
                ),
                "handle_negations": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": (
                            "Protect negated anatomy terms from removal.\n"
                            "e.g. 'no breasts' and 'without a vagina' are left untouched.\n"
                            "spaCy uses dependency parsing for accuracy; the regex\n"
                            "fallback uses a 4-token proximity heuristic."
                        ),
                    },
                ),
                "handle_pronouns": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": (
                            "Swap binary gendered pronouns.\n"
                            "she/her/hers/herself  <->  he/him/his/himself"
                        ),
                    },
                ),
                "rewrite_references": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": (
                            "Swap gendered nouns and adjectives.\n"
                            "woman/girl/lady/feminine  <->  man/boy/guy/masculine\n"
                            "Also covers furry terms: vixen/doe/mare/tigress etc."
                        ),
                    },
                ),
                "swap_clothing": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": (
                            "Replace gendered clothing terms with equivalents,\n"
                            "or remove them where no equivalent exists.\n"
                            "e.g. dress -> suit, skirt -> trousers,\n"
                            "     bra -> removed, bikini -> swim trunks"
                        ),
                    },
                ),
                "map_neopronouns_to_binary": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": (
                            "Map neopronouns and gender-neutral pronouns to binary\n"
                            "equivalents that AI image models are likely to recognise.\n"
                            "Covers: shi/hir (Chakat/furry), they/them, xe/xem,\n"
                            "ze/zir, ey/em (Spivak), fae/faer.\n"
                            "Singular they/them is remapped; plural they/them is\n"
                            "detected by spaCy and preserved (regex is approximate).\n"
                            "When off, all neopronouns pass through unchanged."
                        ),
                    },
                ),
                "spacy_model": (
                    "STRING",
                    {
                        "default": "en_core_web_sm",
                        "tooltip": (
                            "spaCy model to use for NLP processing.\n"
                            "en_core_web_sm  ~12MB  - good for most cases (recommended)\n"
                            "en_core_web_md  ~43MB  - better word vectors\n"
                            "en_core_web_lg  ~560MB - best accuracy\n"
                            "Falls back to regex automatically if spaCy is not installed.\n"
                            "See node pack README for installation instructions."
                        ),
                    },
                ),
            }
        }

    def run(
        self,
        text: str,
        mode: str,
        handle_negations: bool,
        handle_pronouns: bool,
        rewrite_references: bool,
        swap_clothing: bool,
        map_neopronouns_to_binary: bool,
        spacy_model: str,
    ) -> tuple:
        filtered, backend = filter_nl_gender(
            text=text,
            mode=mode,
            handle_negations=handle_negations,
            handle_pronouns=handle_pronouns,
            rewrite_references=rewrite_references,
            swap_clothing=swap_clothing,
            map_neopronouns=map_neopronouns_to_binary,
            spacy_model=spacy_model,
        )
        return (filtered, backend)


# ---------------------------------------------------------------------------
# ComfyUI registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "GenderNLFilter": GenderNLFilter,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GenderNLFilter": "Gender NL Filter 🏳️‍🌈",
}

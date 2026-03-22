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

Contains the spaCy lazy loader (cached per model name), tag syntax parsing
(emphasis/weight, LoRA, BREAK), tag normalisation, NL/tag detection helpers,
negation detection (both spaCy dependency-tree and regex fallback), pronoun
disambiguation, all pronoun maps, gendered noun/adjective maps, anatomy sets
and replacement maps (tag format and NL format), clothing swap maps (underscore
and space format), the full neopronoun map, the dangling adjective pattern,
and precompiled swap patterns for the NL regex fallback.

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
# Tag syntax utilities (emphasis, LoRA, BREAK)
# ---------------------------------------------------------------------------

_SPECIAL_SYNTAX_RE = re.compile(
    r'^<(?:lora|hypernet|lyco|embedding):.*>$', re.IGNORECASE
)


def is_special_syntax(tag: str) -> bool:
    """Return True for LoRA, hypernetwork, LyCORIS, and embedding syntax."""
    s = tag.strip()
    if _SPECIAL_SYNTAX_RE.match(s):
        return True
    if s.lower().startswith('embedding:'):
        return True
    return False


def is_break_keyword(tag: str) -> bool:
    """Return True for the BREAK keyword used in SDXL prompts."""
    return tag.strip() == 'BREAK'


def unwrap_emphasis(tag: str) -> tuple:
    """
    Strip A1111/Forge emphasis syntax from a tag.
    Handles: (tag), (tag:1.3), ((tag)), [tag], [[tag]], etc.
    Returns (inner_tag, prefix, suffix_with_weight).
    If no emphasis syntax, returns (tag, '', '').
    """
    s = tag.strip()
    if not s:
        return s, '', ''

    if s[0] == '(':
        open_char, close_char = '(', ')'
    elif s[0] == '[':
        open_char, close_char = '[', ']'
    else:
        return s, '', ''

    n_open = 0
    while n_open < len(s) and s[n_open] == open_char:
        n_open += 1

    n_close = 0
    end = len(s)
    while n_close < end and s[end - 1 - n_close] == close_char:
        n_close += 1

    if n_open == 0 or n_close == 0:
        return s, '', ''

    depth = min(n_open, n_close)
    inner = s[depth:len(s) - depth]
    prefix = open_char * depth
    suffix = close_char * depth

    weight_match = re.search(r':(\d+\.?\d*)$', inner)
    if weight_match:
        weight_str = weight_match.group(0)
        inner = inner[:weight_match.start()]
        suffix = weight_str + suffix
    elif not inner:
        return s, '', ''

    return inner, prefix, suffix


def rewrap_emphasis(inner: str, prefix: str, suffix: str) -> str:
    """Re-wrap a processed tag with its original emphasis syntax."""
    if prefix or suffix:
        return f'{prefix}{inner}{suffix}'
    return inner


# ---------------------------------------------------------------------------
# Shared text utilities
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


# ---------------------------------------------------------------------------
# Tag normalisation and formatting
# ---------------------------------------------------------------------------

_BS_ESCAPE_RE = re.compile(r'\\(.)')
_BS_RESTORE_RE = re.compile(r'BSESC(.)BSESC')


def normalise_tag(tag: str) -> str:
    """
    Collapse spaces and underscores to underscores for map lookups.
    Backslash-escaped sequences (e.g. Danbooru \\( and \\)) are preserved.
    """
    protected = _BS_ESCAPE_RE.sub(r'BSESC\1BSESC', tag.lower())
    converted = protected.replace(" ", "_")
    return _BS_RESTORE_RE.sub(r'\\\1', converted)


def format_tag(tag: str, tag_format: str) -> str:
    """
    Apply the chosen output format to a tag.
    Backslash-escaped sequences are preserved regardless of format.
    """
    protected = _BS_ESCAPE_RE.sub(r'BSESC\1BSESC', tag)
    if tag_format == "spaces":
        converted = protected.replace("_", " ")
    else:
        converted = protected.replace(" ", "_")
    return _BS_RESTORE_RE.sub(r'\\\1', converted)


# ---------------------------------------------------------------------------
# NL / tag detection
# ---------------------------------------------------------------------------

NL_STOP_WORDS = frozenset({
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
    # Additional verb forms common in NL but absent from tags
    "could", "would", "should", "might", "shall", "will",
    "does", "did", "do",
    "while", "when", "where", "which", "who", "whom", "whose",
    "because", "since", "until", "unless", "although", "though",
})


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

NEGATION_WORDS = frozenset({
    "no", "not", "without", "lacking", "never", "none",
    "doesn't", "don't", "didn't", "won't", "isn't", "aren't",
    "hasn't", "hadn't", "hardly", "barely", "scarcely",
    "neither", "cannot", "can't", "wouldn't", "shouldn't",
    "mustn't", "needn't", "absent", "minus", "devoid",
})

_NEGATION_PREFIX = re.compile(
    r'\b(' + '|'.join(re.escape(n) for n in sorted(NEGATION_WORDS, key=len, reverse=True)) + r')'
    r'(\s+\w+){0,3}\s+',
    re.IGNORECASE
)


def is_negated_regex(text: str, word: str) -> bool:
    """Heuristic: negation word within 4 tokens before target word."""
    pattern = re.compile(
        _NEGATION_PREFIX.pattern + r'\b' + re.escape(word) + r'\b',
        re.IGNORECASE
    )
    return bool(pattern.search(text))


_NEGATION_DET_WORDS = frozenset({"no", "none", "neither", "never"})


def has_negation_ancestor(token) -> bool:
    """
    Check spaCy dependency tree for a negation relation affecting this token.
    spaCy marks negation modifiers with dep_ == 'neg'. Also catches the
    'no + noun' pattern where spaCy labels 'no' as dep_ == 'det' rather
    than 'neg' (e.g. 'no breasts', 'no penis').
    """
    for child in token.head.children:
        if child.dep_ == "neg":
            return True
    for child in token.children:
        if child.dep_ == "neg":
            return True
        # 'no breasts' -> 'no' is dep_='det' modifying 'breasts'
        if child.dep_ == "det" and child.text.lower() in _NEGATION_DET_WORDS:
            return True
    # Also check if the token's head is a verb negated by 'not'
    # e.g. 'does not have breasts' -> 'not' negates 'have', 'breasts' is dobj
    if token.head.pos_ in {"VERB", "AUX"}:
        for child in token.head.children:
            if child.dep_ == "neg":
                return True
    return False


# ---------------------------------------------------------------------------
# Pronoun disambiguation
# ---------------------------------------------------------------------------

def disambiguate_her_spacy(token) -> str:
    """
    Disambiguate 'her' between possessive (-> 'his') and object (-> 'him')
    using spaCy dependency and morphology.
    'her book' (possessive det) -> 'his book'
    'I saw her' (object pronoun) -> 'I saw him'
    """
    if token.dep_ == "poss":
        return "his"
    poss = token.morph.get("Poss")
    if poss and "Yes" in poss:
        return "his"
    return "him"


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
    # ve/ver/vis - less common but used in some furry communities
    "ve":           ("he",      "she"),
    "ver":          ("him",     "her"),
    "vis":          ("his",     "her"),
    "verself":      ("himself", "herself"),
    # per/pers - Marge Piercy neopronouns
    "per":          ("he",      "she"),
    "pers":         ("his",     "her"),
    "perself":      ("himself", "herself"),
    # Note: "it/its" intentionally excluded - overwhelmingly used for
    # objects and animals in model training data.
}


# ---------------------------------------------------------------------------
# Binary pronoun maps
# ---------------------------------------------------------------------------

FEMALE_TO_MALE_PRONOUNS = {
    "herself":  "himself",
    "she's":    "he's",
    "she":      "he",
    # "her" is ambiguous: possessive -> "his", object -> "him".
    # Regex fallback defaults to "his" (possessive is more common in prompts).
    # The spaCy path uses disambiguate_her_spacy() for accurate resolution.
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
    # Core identity
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
    # Relationships and family
    "girlfriend":   "boyfriend",
    "wife":         "husband",
    "mother":       "father",
    "mom":          "dad",
    "mommy":        "daddy",
    "mama":         "papa",
    "mum":          "dad",
    "daughter":     "son",
    "daughters":    "sons",
    "sister":       "brother",
    "sisters":      "brothers",
    "aunt":         "uncle",
    "aunts":        "uncles",
    "niece":        "nephew",
    "nieces":       "nephews",
    "grandmother":  "grandfather",
    "grandma":      "grandpa",
    "granddaughter": "grandson",
    "stepdaughter": "stepson",
    "stepmother":   "stepfather",
    "stepmom":      "stepdad",
    "bride":        "groom",
    "fiancee":      "fiance",
    "fiancée":      "fiancé",
    # Youth / informal
    "maiden":       "lad",
    "damsel":       "lad",
    "lass":         "lad",
    "lassie":       "laddie",
    "babe":         "hunk",
    "chick":        "dude",
    # Titles and royalty
    "mistress":     "master",
    "queen":        "king",
    "queens":       "kings",
    "princess":     "prince",
    "empress":      "emperor",
    "duchess":      "duke",
    "baroness":     "baron",
    "countess":     "count",
    "marchioness":  "marquess",
    "matriarch":    "patriarch",
    # Mythological / fantasy
    "goddess":      "god",
    "witch":        "warlock",
    "witches":      "warlocks",
    "sorceress":    "sorcerer",
    "enchantress":  "enchanter",
    "priestess":    "priest",
    "succubus":     "incubus",
    "mermaid":      "merman",
    "mermaids":     "mermen",
    "siren":        "satyr",
    "nymph":        "faun",
    "valkyrie":     "einherjar",
    # Religious / spiritual
    "nun":          "monk",
    "nuns":         "monks",
    "abbess":       "abbot",
    # Professional / occupational
    "heroine":      "hero",
    "heroines":     "heroes",
    "waitress":     "waiter",
    "actress":      "actor",
    "hostess":      "host",
    "seamstress":   "tailor",
    "huntress":     "hunter",
    "governess":    "governor",
    "dominatrix":   "dominator",
    "temptress":    "tempter",
    "seductress":   "seducer",
    "songstress":   "singer",
    "stewardess":   "steward",
    "maid":         "manservant",
    "handmaiden":   "manservant",
    "heiress":      "heir",
    "ballerina":    "dancer",
    "showgirl":     "showman",
    "milkmaid":     "milkman",
    "landlady":     "landlord",
    "headmistress": "headmaster",
    # Adjectives / descriptors
    "busty":        "muscular",
    "buxom":        "muscular",
    "curvy":        "athletic",
    "voluptuous":   "athletic",
    "feminine":     "masculine",
    "womanly":      "manly",
    "girlish":      "boyish",
    "ladylike":     "gentlemanly",
    "matronly":     "fatherly",
    "motherly":     "fatherly",
    "sisterly":     "brotherly",
    # Furry / fandom - animals
    "vixen":        "fox",
    "doe":          "buck",
    "mare":         "stallion",
    "filly":        "colt",
    "hen":          "rooster",
    "cow":          "bull",
    "heifer":       "steer",
    "ewe":          "ram",
    "sow":          "boar",
    "tigress":      "tiger",
    "lioness":      "lion",
    "she-wolf":     "wolf",
    "she_wolf":     "wolf",
    "dragoness":    "dragon",
    "peahen":       "peacock",
    "goose":        "gander",
    "jenny":        "jack",
    "nanny_goat":   "billy_goat",
    "leopardess":   "leopard",
    "she-bear":     "bear",
    "she_bear":     "bear",
    "dam":          "sire",
    # Furry-specific character types
    "catgirl":      "catboy",
    "foxgirl":      "foxboy",
    "wolfgirl":     "wolfboy",
    "doggirl":      "dogboy",
    "bunnygirl":    "bunnyboy",
    "cowgirl":      "cowboy",
    "batgirl":      "batboy",
    "lamia":        "naga",
    "harpy":        "tengu",
}

MALE_TO_FEMALE_WORDS = {
    # Core identity
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
    # Relationships and family
    "boyfriend":    "girlfriend",
    "husband":      "wife",
    "father":       "mother",
    "dad":          "mom",
    "daddy":        "mommy",
    "papa":         "mama",
    "son":          "daughter",
    "sons":         "daughters",
    "brother":      "sister",
    "brothers":     "sisters",
    "uncle":        "aunt",
    "uncles":       "aunts",
    "nephew":       "niece",
    "nephews":      "nieces",
    "grandfather":  "grandmother",
    "grandpa":      "grandma",
    "grandson":     "granddaughter",
    "stepson":      "stepdaughter",
    "stepfather":   "stepmother",
    "stepdad":      "stepmom",
    "groom":        "bride",
    "fiance":       "fiancee",
    "fiancé":       "fiancée",
    # Youth / informal
    "lad":          "lass",
    "laddie":       "lassie",
    "hunk":         "babe",
    "dude":         "chick",
    # Titles and royalty
    "master":       "mistress",
    "king":         "queen",
    "kings":        "queens",
    "prince":       "princess",
    "emperor":      "empress",
    "duke":         "duchess",
    "baron":        "baroness",
    "count":        "countess",
    "marquess":     "marchioness",
    "patriarch":    "matriarch",
    # Mythological / fantasy
    "god":          "goddess",
    "warlock":      "witch",
    "warlocks":     "witches",
    "sorcerer":     "sorceress",
    "enchanter":    "enchantress",
    "priest":       "priestess",
    "incubus":      "succubus",
    "merman":       "mermaid",
    "mermen":       "mermaids",
    "satyr":        "siren",
    "faun":         "nymph",
    "einherjar":    "valkyrie",
    # Religious / spiritual
    "monk":         "nun",
    "monks":        "nuns",
    "abbot":        "abbess",
    # Professional / occupational
    "hero":         "heroine",
    "heroes":       "heroines",
    "waiter":       "waitress",
    "actor":        "actress",
    "host":         "hostess",
    "tailor":       "seamstress",
    "hunter":       "huntress",
    "governor":     "governess",
    "dominator":    "dominatrix",
    "tempter":      "temptress",
    "seducer":      "seductress",
    "singer":       "songstress",
    "steward":      "stewardess",
    "manservant":   "maid",
    "heir":         "heiress",
    "dancer":       "ballerina",
    "showman":      "showgirl",
    "milkman":      "milkmaid",
    "landlord":     "landlady",
    "headmaster":   "headmistress",
    # Adjectives / descriptors
    "muscular":     "busty",
    "masculine":    "feminine",
    "manly":        "womanly",
    "boyish":       "girlish",
    "gentlemanly":  "ladylike",
    "fatherly":     "motherly",
    "brotherly":    "sisterly",
    # Furry / fandom - animals
    "fox":          "vixen",
    "buck":         "doe",
    "stallion":     "mare",
    "colt":         "filly",
    "rooster":      "hen",
    "bull":         "cow",
    "steer":        "heifer",
    "ram":          "ewe",
    "boar":         "sow",
    "tiger":        "tigress",
    "lion":         "lioness",
    "wolf":         "she-wolf",
    "dragon":       "dragoness",
    "peacock":      "peahen",
    "gander":       "goose",
    "jack":         "jenny",
    "billy_goat":   "nanny_goat",
    "leopard":      "leopardess",
    "bear":         "she-bear",
    "sire":         "dam",
    # Furry-specific character types
    "catboy":       "catgirl",
    "foxboy":       "foxgirl",
    "wolfboy":      "wolfgirl",
    "dogboy":       "doggirl",
    "bunnyboy":     "bunnygirl",
    "cowboy":       "cowgirl",
    "batboy":       "batgirl",
    "naga":         "lamia",
    "tengu":        "harpy",
}


# ---------------------------------------------------------------------------
# Anatomy sets and replacement maps
# ---------------------------------------------------------------------------

# Root words for compound tag scanning in the tag filter.
# Only includes words safe from false positives when split on underscores.
FEMALE_ANATOMY_ROOTS = frozenset({
    "breast", "breasts", "boob", "boobs", "tit", "tits",
    "nipple", "nipples", "areola", "areolae",
    "pussy", "vagina", "vaginal", "vulva", "labia", "clitoris", "clit",
    "womb", "uterus", "ovaries", "cervix", "cervical",
    "paizuri", "titjob", "titfuck",
    "girl", "girls", "female",
    "lactation", "lactating", "breastfeeding",
    "cunnilingus", "tribadism", "scissoring",
    "yuri", "lesbian",
})

MALE_ANATOMY_ROOTS = frozenset({
    "penis", "penile", "cock", "dick", "phallus",
    "erection", "boner",
    "balls", "testicles", "testes", "scrotum", "ballsack",
    "foreskin", "glans",
    "sheath", "knot", "knotted", "knotting",
    "cum", "cumshot", "ejaculation", "creampie", "bukkake",
    "boy", "boys", "male",
    "fellatio", "blowjob", "deepthroat",
    "yaoi", "bara", "gay",
    "prostate",
})

# Full tag blocklists (exact normalised matches, underscore format)
FEMALE_ANATOMY = frozenset({
    # Gender identity / count tags
    "female", "girl", "woman",
    "1girl", "2girls", "3girls", "4girls", "5girls", "6+girls",
    "multiple_girls", "solo_female", "female_only",
    # Breast size variants
    "breasts", "breast",
    "micro_breasts", "small_breasts", "medium_breasts", "large_breasts",
    "huge_breasts", "gigantic_breasts", "colossal_breasts",
    # Breast descriptors
    "sagging_breasts", "saggy_breasts", "perky_breasts", "firm_breasts",
    "bouncing_breasts", "jiggling_breasts", "hanging_breasts",
    "torpedo_breasts", "cone_breasts", "asymmetrical_breasts",
    "uneven_breasts",
    # Breast positions
    "breasts_apart", "breasts_together", "breasts_out",
    "breasts_outside",
    # Breast actions / interactions
    "breast_grab", "breast_squeeze", "breast_press", "breast_hold",
    "breast_lift", "breast_smother", "breast_expansion",
    "breast_sucking", "breast_feeding", "breast_rest",
    "breast_conscious", "breast_envy",
    "paizuri", "titjob", "titfuck", "mammary_intercourse",
    "symmetrical_docking", "naizuri",
    # Cleavage
    "cleavage", "sideboob", "underboob", "side_boob", "under_boob",
    # Flat chest (female-coded in Danbooru/e621)
    "flat_chest", "flat_chested",
    # Nipple variants
    "nipples", "nipple",
    "inverted_nipples", "puffy_nipples", "dark_nipples", "pink_nipples",
    "erect_nipples", "nipple_piercing", "nipple_slip", "nipple_tweak",
    "nipple_stimulation", "nipple_clamps",
    # Areola
    "areola", "areolae", "large_areolae", "dark_areolae",
    "puffy_areolae",
    # Female genitalia
    "pussy", "vagina", "vulva", "labia", "clitoris", "clit",
    "pussy_juice", "wet_pussy", "spread_pussy", "shaved_pussy",
    "hairy_pussy", "cameltoe", "camel_toe", "pussy_hair",
    "labia_piercing", "clit_piercing",
    # Vaginal actions
    "vaginal", "vaginal_penetration", "vaginal_sex", "vaginal_insertion",
    "vaginal_fluid", "vaginal_juice", "vaginal_fingering",
    "vaginal_object_insertion",
    # Pubic / genital labels
    "female_pubic_hair", "female_genitalia",
    # Internal anatomy
    "uterus", "womb", "cervix", "ovaries",
    "cervical_penetration", "womb_tattoo",
    # Female-specific acts
    "cunnilingus", "tribadism", "scissoring",
    # Orgasm / ejaculation
    "female_orgasm", "squirting", "female_ejaculation",
    # Body shape
    "wide_hips", "thick_thighs", "child_bearing_hips",
    "hourglass_figure", "pear_shaped",
    # Pregnancy and lactation
    "pregnant", "pregnancy", "pregnant_belly", "baby_bump",
    "lactation", "lactating", "breastfeeding", "nursing", "breast_milk",
    # Menstruation
    "menstruation",
    # Positions
    "girl_on_top", "cowgirl_position", "reverse_cowgirl_position",
    "amazon_position",
    # Orientation / genre
    "yuri", "lesbian",
    # Power dynamics
    "femdom", "female_domination",
    # Nudity labels
    "topless_female", "nude_female",
    # Hermaphrodite / futanari
    "futanari", "futa", "newhalf", "dickgirl",
})

MALE_ANATOMY = frozenset({
    # Gender identity / count tags
    "male", "boy", "man",
    "1boy", "2boys", "3boys", "4boys", "5boys", "6+boys",
    "multiple_boys", "solo_male", "male_only",
    # Penis variants
    "penis", "cock", "dick", "phallus",
    "small_penis", "large_penis", "huge_penis",
    "erect_penis", "flaccid_penis", "semi-erect",
    "veiny_penis", "thick_penis",
    "circumcised", "uncircumcised",
    # Furry penis types
    "horse_penis", "equine_penis", "canine_penis",
    "knotted_penis", "barbed_penis", "hemipenes",
    "penile_spines", "tapered_penis", "prehensile_penis",
    # Testicles
    "balls", "testicles", "testes", "scrotum", "ballsack",
    "large_balls", "hanging_balls",
    # Foreskin / glans
    "foreskin", "glans", "frenulum",
    # Erection
    "erection", "boner", "hard-on", "morning_wood",
    # Sheath / knot (furry)
    "sheath", "knot", "knotted", "knotting",
    # Ejaculation / cum
    "cum", "cumshot", "ejaculation", "orgasm",
    "cum_on_body", "cum_inside", "cum_in_mouth",
    "cum_drip", "cum_string", "cum_on_face",
    "cum_on_chest", "cum_on_stomach", "cum_on_back",
    "cum_on_ass", "cum_inflation", "excessive_cum",
    "precum", "pre-cum", "cum_pool", "cum_bath",
    "cum_covered", "cum_trail", "cum_explosion",
    "creampie", "internal_cumshot",
    "male_ejaculation",
    # Male-specific acts
    "handjob", "blowjob", "fellatio", "deepthroat", "deep_throat",
    "facial_(cum)", "bukkake", "gokkun",
    "prostate", "prostate_massage",
    "frottage", "docking_(penile)", "sounding", "urethral",
    "cock_ring", "cock_sleeve", "cock_cage",
    # Penile actions
    "penile", "penile_penetration",
    # Male genitalia labels
    "male_genitalia", "male_pubic_hair",
    # Body / muscle
    "pecs", "muscular_chest", "abs", "six_pack",
    "chest_muscles", "defined_abs",
    # Bulge
    "bulge", "bulge_outline", "visible_bulge", "crotch_bulge",
    # Orientation / genre
    "yaoi", "gay", "bara",
    # Power dynamics
    "maledom", "male_domination",
    # Nudity labels
    "topless_male", "nude_male",
    # Shaft (standalone tag is male-coded)
    "shaft",
})

# NL anatomy sets (space format for prose matching)
FEMALE_ANATOMY_NL = frozenset({
    "breasts", "breast", "boobs", "boob", "tits", "tit",
    "bust", "bosom", "bosoms",
    "cleavage", "sideboob", "underboob",
    "mammary", "mammaries",
    "nipples", "nipple",
    "areola", "areolae",
    "pussy", "vagina", "vulva", "labia", "clitoris", "clit",
    "womb", "uterus", "ovaries", "cervix",
    "hips",
})

MALE_ANATOMY_NL = frozenset({
    "penis", "cock", "dick", "phallus",
    "erection", "boner",
    "balls", "testicles", "scrotum",
    "foreskin", "glans",
    "sheath", "knot",
    "shaft",
    "pecs", "pec",
    "bulge",
    "manhood",
})

# Anatomy replacement maps for tag context
FEMALE_TO_MALE_REPLACEMENTS = {
    # Breast -> chest/pec equivalents
    "breasts":              "pecs",
    "breast":               "pec",
    "small_breasts":        "flat_chest",
    "medium_breasts":       "pecs",
    "large_breasts":        "muscular_chest",
    "huge_breasts":         "muscular_chest",
    "gigantic_breasts":     "muscular_chest",
    "colossal_breasts":     "muscular_chest",
    "micro_breasts":        "flat_chest",
    "flat_chest":           "flat_chest",
    "cleavage":             "chest",
    "sideboob":             "chest",
    "underboob":            "chest",
    # Body shape
    "wide_hips":            "narrow_hips",
    "hourglass_figure":     "athletic_build",
    "slender":              "lean",
    # Identity swaps
    "feminine":             "masculine",
    "girl":                 "male",
    "woman":                "male",
    "female":               "male",
    # Count tags
    "1girl":                "1boy",
    "2girls":               "2boys",
    "3girls":               "3boys",
    "4girls":               "4boys",
    "5girls":               "5boys",
    "6+girls":              "6+boys",
    "multiple_girls":       "multiple_boys",
    "solo_female":          "solo_male",
    "female_only":          "male_only",
    # Orientation / genre
    "yuri":                 "yaoi",
    "lesbian":              "gay",
    # Power dynamics
    "femdom":               "maledom",
    "female_domination":    "male_domination",
    # Nudity
    "topless_female":       "topless_male",
    "nude_female":          "nude_male",
    # Genitalia swaps
    "cameltoe":             "bulge",
    "camel_toe":            "bulge",
    # Focus
    "female_focus":         "male_focus",
    # Futanari
    "futanari":             "male",
    "futa":                 "male",
    "newhalf":              "male",
    "dickgirl":             "male",
    # Positions
    "girl_on_top":          "boy_on_top",
}

MALE_TO_FEMALE_REPLACEMENTS = {
    # Chest -> breast equivalents
    "pecs":                 "breasts",
    "muscular_chest":       "large_breasts",
    "chest":                "cleavage",
    # Body shape
    "narrow_hips":          "wide_hips",
    "athletic_build":       "hourglass_figure",
    # Identity swaps
    "masculine":            "feminine",
    "boy":                  "female",
    "man":                  "female",
    "male":                 "female",
    # Count tags
    "1boy":                 "1girl",
    "2boys":                "2girls",
    "3boys":                "3girls",
    "4boys":                "4girls",
    "5boys":                "5girls",
    "6+boys":               "6+girls",
    "multiple_boys":        "multiple_girls",
    "solo_male":            "solo_female",
    "male_only":            "female_only",
    # Orientation / genre
    "yaoi":                 "yuri",
    "gay":                  "lesbian",
    "bara":                 "yuri",
    # Power dynamics
    "maledom":              "femdom",
    "male_domination":      "female_domination",
    # Nudity
    "topless_male":         "topless_female",
    "nude_male":            "nude_female",
    # Genitalia swaps
    "bulge":                "cameltoe",
    "bulge_outline":        "cameltoe",
    # Focus
    "male_focus":           "female_focus",
}

# Anatomy replacement maps for NL context
# None = no clean NL equivalent; remove instead.
FEMALE_ANATOMY_NL_REPLACEMENTS = {
    "breasts":      "pecs",
    "breast":       "pec",
    "boobs":        "pecs",
    "boob":         "pec",
    "tits":         "pecs",
    "tit":          "pec",
    "bust":         "chest",
    "bosom":        "chest",
    "bosoms":       "chest",
    "cleavage":     "chest",
    "sideboob":     "chest",
    "underboob":    "chest",
    "mammary":      "pectoral",
    "mammaries":    "pectorals",
    "nipples":      "nipples",
    "nipple":       "nipple",
    "areola":       "areola",
    "areolae":      "areolae",
    "pussy":        "cock",
    "vagina":       "penis",
    "vulva":        None,
    "labia":        None,
    "clitoris":     None,
    "clit":         None,
    "womb":         None,
    "uterus":       None,
    "ovaries":      None,
    "cervix":       None,
    "hips":         "hips",
}

MALE_ANATOMY_NL_REPLACEMENTS = {
    "penis":        "pussy",
    "cock":         "pussy",
    "dick":         "pussy",
    "phallus":      None,
    "erection":     None,
    "boner":        None,
    "balls":        None,
    "testicles":    None,
    "scrotum":      None,
    "foreskin":     None,
    "glans":        None,
    "sheath":       None,
    "knot":         None,
    "shaft":        None,
    "pecs":         "breasts",
    "pec":          "breast",
    "bulge":        None,
    "manhood":      None,
}


# ---------------------------------------------------------------------------
# Presentation / clothing tag lists and replacement maps
# ---------------------------------------------------------------------------

FEMALE_PRESENTATION = frozenset({
    # Makeup / beauty
    "lipstick", "lip_gloss", "makeup", "mascara", "eyeshadow", "blush",
    "foundation", "rouge", "beauty_mark", "mole_on_breast",
    "nail_polish", "painted_nails", "long_nails", "fake_nails",
    "eyeliner", "eyelash_extensions", "false_eyelashes", "contour",
    "lip_liner", "concealer", "powder", "bronzer", "highlighter_(makeup)",
    # Underwear / lingerie
    "bra", "brassiere", "sports_bra", "bikini_top", "strapless_bra",
    "push-up_bra", "underwire_bra", "lace_bra", "sheer_bra",
    "panties", "thong", "g-string", "lingerie", "underwear_female",
    "boy_shorts_(underwear)", "crotchless_panties", "lace_panties",
    "garter_belt", "garter", "stockings", "pantyhose", "nylons",
    "fishnet_stockings", "fishnet_pantyhose", "fishnets",
    "thigh_highs", "stay-ups",
    "teddy_(lingerie)", "negligee", "babydoll",
    "corset", "bustier", "chemise", "nightgown",
    # Dresses and skirts
    "dress", "skirt", "miniskirt", "sundress", "evening_gown",
    "frilled_skirt", "pleated_skirt", "short_skirt",
    "maxi_dress", "midi_dress", "mini_dress",
    "cocktail_dress", "wedding_dress", "prom_dress",
    "pencil_skirt", "a-line_skirt", "wrap_dress",
    "ball_gown", "strapless_dress", "backless_dress",
    "halter_dress", "bodycon_dress",
    # Tops
    "blouse", "crop_top", "tube_top", "halter_top",
    "camisole", "tank_top_(female)",
    # Swimwear
    "female_swimwear", "bikini", "one-piece_swimsuit",
    "micro_bikini", "sling_bikini", "string_bikini",
    "brazilian_bikini", "tankini", "monokini",
    "competition_swimsuit", "school_swimsuit",
    # Shoes / footwear
    "high_heels", "heels", "stilettos", "wedge_heels",
    "platform_heels", "kitten_heels", "peep-toe_heels",
    "slingback_heels", "mary_janes", "ballet_flats",
    "thigh-high_boots",
    # Hair accessories
    "hair_bow", "hair_ribbon", "scrunchie",
    "hair_ornament_(female)", "tiara", "fascinator",
    # Accessories
    "clutch_purse", "handbag", "purse", "ankle_bracelet", "anklet",
    # Other garments
    "slip", "petticoat", "sarong", "pareo",
    "leotard_(female)", "bodysuit_(female)",
    "catsuit",
    # Cosplay / costumes
    "maid_outfit", "maid_headdress", "maid_apron", "french_maid",
    "bunny_girl", "bunny_ears_(cosplay)", "playboy_bunny",
    "cheerleader", "cheerleader_uniform",
    "sailor_fuku", "serafuku",
    # Exposure / situational
    "pantyshot", "upskirt", "no_bra", "no_panties",
    "visible_bra", "bra_strap", "panty_pull", "bra_pull",
    "skirt_lift", "skirt_pull", "dress_lift",
    "zettai_ryouiki", "absolute_territory",
    # Gender descriptors
    "feminine", "effeminate",
    # Focus tags
    "female_focus",
})

MALE_PRESENTATION = frozenset({
    # Neckwear / formalwear
    "tie", "necktie", "bow_tie", "business_suit", "suit_and_tie",
    "tuxedo", "cummerbund", "cufflinks",
    # Tops
    "dress_shirt", "polo_shirt",
    # Underwear
    "boxer_briefs", "boxers", "briefs", "jockstrap", "male_underwear",
    "trunks_(underwear)",
    # Body features
    "chest_hair", "body_hair", "facial_hair",
    "beard", "mustache", "goatee", "stubble", "sideburns",
    # Swimwear
    "swim_trunks", "board_shorts", "speedo", "swimming_briefs",
    # Traditional / cultural
    "fundoshi", "loincloth",
    # Accessories
    "codpiece", "suspenders",
    # Footwear
    "loafers", "oxfords", "brogues", "combat_boots",
    # Pants / bottoms
    "cargo_shorts", "cargo_pants",
    # Outerwear
    "vest", "waistcoat",
    # Gender descriptors
    "masculine", "macho",
    # Focus tags
    "male_focus",
})

# Clothing replacement maps - tag format (underscores)
FEMALE_TO_MALE_CLOTHING = {
    # Dresses -> suits / formalwear
    "evening_gown":         "tuxedo",
    "ball_gown":            "tuxedo",
    "cocktail_dress":       "business_suit",
    "wedding_dress":        "tuxedo",
    "prom_dress":           "tuxedo",
    "strapless_dress":      "suit",
    "backless_dress":       "suit",
    "halter_dress":         "suit",
    "bodycon_dress":        "suit",
    "dress":                "suit",
    "sundress":             "suit",
    "maxi_dress":           "suit",
    "midi_dress":           "suit",
    "mini_dress":           "suit",
    "wrap_dress":           "suit",
    "gown":                 "robe",
    # Skirts -> trousers / shorts
    "pencil_skirt":         "trousers",
    "pleated_skirt":        "trousers",
    "frilled_skirt":        "trousers",
    "a-line_skirt":         "trousers",
    "short_skirt":          "shorts",
    "skirt":                "trousers",
    "miniskirt":            "shorts",
    # Tops
    "blouse":               "shirt",
    "crop_top":             "tank_top",
    "tube_top":             "tank_top",
    "halter_top":           "tank_top",
    "camisole":             "undershirt",
    # Swimwear
    "one-piece_swimsuit":   "swim_trunks",
    "bikini_top":           "tank_top",
    "bikini":               "swim_trunks",
    "female_swimwear":      "swim_trunks",
    "micro_bikini":         "swim_trunks",
    "sling_bikini":         "swim_trunks",
    "string_bikini":        "swim_trunks",
    "brazilian_bikini":     "swim_trunks",
    "tankini":              "swim_trunks",
    "monokini":             "swim_trunks",
    "competition_swimsuit": "swim_trunks",
    "school_swimsuit":      "swim_trunks",
    # Underwear / lingerie
    "bra":                  None,
    "brassiere":            None,
    "sports_bra":           None,
    "strapless_bra":        None,
    "push-up_bra":          None,
    "underwire_bra":        None,
    "lace_bra":             None,
    "sheer_bra":            None,
    "panties":              "boxer_briefs",
    "thong":                None,
    "g-string":             None,
    "boy_shorts_(underwear)": "boxer_briefs",
    "crotchless_panties":   None,
    "lace_panties":         None,
    "underwear_female":     "male_underwear",
    "lingerie":             "underwear",
    "teddy_(lingerie)":     None,
    "negligee":             "pajamas",
    "babydoll":             "pajamas",
    "chemise":              "undershirt",
    "nightgown":            "pajamas",
    "corset":               None,
    "bustier":              None,
    # Hosiery
    "garter_belt":          None,
    "garter":               None,
    "stockings":            "socks",
    "pantyhose":            None,
    "nylons":               None,
    "fishnet_stockings":    None,
    "fishnet_pantyhose":    None,
    "fishnets":             None,
    "thigh_highs":          "socks",
    "stay-ups":             None,
    # Shoes
    "high_heels":           "boots",
    "heels":                "boots",
    "stilettos":            "boots",
    "wedge_heels":          "boots",
    "platform_heels":       "boots",
    "kitten_heels":         "loafers",
    "peep-toe_heels":       "boots",
    "slingback_heels":      "boots",
    "mary_janes":           "loafers",
    "ballet_flats":         "loafers",
    "thigh-high_boots":     "boots",
    # Hair accessories
    "hair_bow":             None,
    "hair_ribbon":          None,
    "scrunchie":            None,
    "tiara":                None,
    "fascinator":           None,
    # Accessories
    "clutch_purse":         None,
    "handbag":              None,
    "purse":                None,
    "ankle_bracelet":       None,
    "anklet":               None,
    # Other garments
    "slip":                 None,
    "petticoat":            None,
    "sarong":               "shorts",
    "pareo":                "shorts",
    "catsuit":              "bodysuit",
    # Cosplay
    "maid_outfit":          "butler_outfit",
    "maid_headdress":       None,
    "maid_apron":           None,
    "french_maid":          "butler",
    "bunny_girl":           "bunny_boy",
    "playboy_bunny":        None,
    "cheerleader":          None,
    "cheerleader_uniform":  None,
    "sailor_fuku":          "school_uniform",
    "serafuku":             "school_uniform",
    # Gender descriptors
    "feminine":             "masculine",
    "effeminate":           "masculine",
    # Focus
    "female_focus":         "male_focus",
}

MALE_TO_FEMALE_CLOTHING = {
    # Formalwear -> dresses
    "tuxedo":               "evening_gown",
    "business_suit":        "cocktail_dress",
    "suit_and_tie":         "evening_gown",
    "suit":                 "dress",
    "robe":                 "gown",
    # Bottoms
    "trousers":             "skirt",
    "shorts":               "miniskirt",
    "cargo_shorts":         "miniskirt",
    "cargo_pants":          "skirt",
    # Tops
    "shirt":                "blouse",
    "dress_shirt":          "blouse",
    "polo_shirt":           "blouse",
    # Swimwear
    "swim_trunks":          "bikini",
    "board_shorts":         "bikini",
    "speedo":               "one-piece_swimsuit",
    "swimming_briefs":      "one-piece_swimsuit",
    # Underwear
    "boxer_briefs":         "panties",
    "boxers":               "panties",
    "briefs":               "panties",
    "jockstrap":            None,
    "male_underwear":       "underwear_female",
    "trunks_(underwear)":   "panties",
    # Sleepwear
    "pajamas":              "nightgown",
    "undershirt":           "chemise",
    "underwear":            "lingerie",
    # Hosiery
    "socks":                "stockings",
    # Shoes
    "boots":                "high_heels",
    "combat_boots":         "high_heels",
    "loafers":              "mary_janes",
    "oxfords":              "mary_janes",
    "brogues":              "mary_janes",
    # Accessories
    "suspenders":           "garter_belt",
    "cummerbund":           None,
    "cufflinks":            None,
    "codpiece":             None,
    # Traditional
    "fundoshi":             None,
    "loincloth":            None,
    # Outerwear
    "vest":                 "corset",
    "waistcoat":            "corset",
    # Neckwear
    "tie":                  "choker",
    "necktie":              "choker",
    "bow_tie":              "hair_ribbon",
    # Body features (remove, no female equivalent)
    "chest_hair":           None,
    "body_hair":            None,
    "facial_hair":          None,
    "beard":                None,
    "mustache":             None,
    "goatee":               None,
    "stubble":              None,
    "sideburns":            None,
    # Cosplay
    "butler_outfit":        "maid_outfit",
    "butler":               "french_maid",
    "bunny_boy":            "bunny_girl",
    # Gender descriptors
    "masculine":            "feminine",
    "macho":                "feminine",
    # Focus
    "male_focus":           "female_focus",
}

# Clothing replacement maps - NL format (spaces)
CLOTHING_FEMALE_TO_MALE_NL = {
    # Dresses -> suits
    "evening gown":         "tuxedo",
    "ball gown":            "tuxedo",
    "cocktail dress":       "business suit",
    "wedding dress":        "tuxedo",
    "prom dress":           "tuxedo",
    "strapless dress":      "suit",
    "backless dress":       "suit",
    "halter dress":         "suit",
    "bodycon dress":        "suit",
    "maxi dress":           "suit",
    "midi dress":           "suit",
    "mini dress":           "suit",
    "wrap dress":           "suit",
    "one-piece swimsuit":   "swim trunks",
    "pencil skirt":         "trousers",
    "pleated skirt":        "trousers",
    "frilled skirt":        "trousers",
    "a-line skirt":         "trousers",
    "bikini top":           "tank top",
    "bikini bottom":        "swim trunks",
    "micro bikini":         "swim trunks",
    "string bikini":        "swim trunks",
    "sports bra":           None,
    "strapless bra":        None,
    "push-up bra":          None,
    "underwire bra":        None,
    "lace bra":             None,
    "garter belt":          None,
    "high heels":           "boots",
    "wedge heels":          "boots",
    "platform heels":       "boots",
    "kitten heels":         "loafers",
    "hair bow":             None,
    "hair ribbon":          None,
    # Single-word items
    "dress":                "suit",
    "gown":                 "robe",
    "skirt":                "trousers",
    "miniskirt":            "shorts",
    "blouse":               "shirt",
    "camisole":             "undershirt",
    "crop top":             "tank top",
    "tube top":             "tank top",
    "halter top":           "tank top",
    "bikini":               "swim trunks",
    "swimsuit":             "swim trunks",
    "lingerie":             "underwear",
    "negligee":             "pajamas",
    "nightgown":            "pajamas",
    "chemise":              "undershirt",
    "babydoll":             "pajamas",
    "bra":                  None,
    "brassiere":            None,
    "panties":              "boxers",
    "thong":                None,
    "corset":               None,
    "bustier":              None,
    "stockings":            "socks",
    "pantyhose":            None,
    "nylons":               None,
    "fishnets":             None,
    "heels":                "boots",
    "stilettos":            "boots",
    "scrunchie":            None,
    "garter":               None,
    "tiara":                None,
    "leotard":              "singlet",
    "catsuit":              "bodysuit",
    "sarong":               "shorts",
    "petticoat":            None,
    "slip":                 None,
    "anklet":               None,
}

CLOTHING_MALE_TO_FEMALE_NL = {
    # Formalwear -> dresses
    "suit and tie":         "evening gown",
    "business suit":        "cocktail dress",
    "swim trunks":          "bikini",
    "board shorts":         "bikini",
    "boxer briefs":         "panties",
    "dress shirt":          "blouse",
    "polo shirt":           "blouse",
    "combat boots":         "high heels",
    "cargo shorts":         "miniskirt",
    "cargo pants":          "skirt",
    "bow tie":              "hair ribbon",
    # Single-word items
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
    "loafers":              "mary janes",
    "oxfords":              "mary janes",
    "jockstrap":            None,
    "boxers":               "panties",
    "briefs":               "panties",
    "speedo":               "swimsuit",
    "suspenders":           "garter belt",
    "cummerbund":           None,
    "cufflinks":            None,
    "codpiece":             None,
    "fundoshi":             None,
    "loincloth":            None,
    "vest":                 "corset",
    "waistcoat":            "corset",
    "singlet":              "leotard",
    "bodysuit":             "catsuit",
    "tie":                  "choker",
    "necktie":              "choker",
}

# ---------------------------------------------------------------------------
# Dangling adjective pattern (used in NL anatomy removal)
# ---------------------------------------------------------------------------

DANGLING_ADJ_PATTERN = re.compile(
    r'\b(?:(?:large|huge|massive|tiny|small|big|gigantic|perky|saggy|'
    r'round|flat|firm|soft|hard|erect|throbbing|enormous|pert|'
    r'plump|supple|toned|shapely|heavy|ample|generous|modest|'
    r'voluptuous|meaty|thick|thin|slender|delicate|swollen|'
    r'hanging|bouncy|jiggly|veiny|girthy|long|short|fat|'
    r'smooth|hairy|shaved|trimmed|wet|dripping|glistening|'
    r'stiff|rigid|taut|loose|floppy|pendulous|bulging|'
    r'prominent|pronounced|defined|sculpted|chiseled)(?:,\s*|\s+))+',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# spaCy plural they/them detection
# ---------------------------------------------------------------------------

_THEY_FORMS = frozenset({"they", "them", "their", "theirs", "themselves", "themself"})


def is_plural_they(token) -> bool:
    """
    Distinguish singular they (gender-neutral pronoun) from plural they.
    Returns True when plural - leave untouched.
    """
    number = token.morph.get("Number")
    if number and "Plur" in number:
        return True
    if token.text.lower() in _THEY_FORMS:
        subject_count = sum(
            1 for t in token.sent
            if t.dep_ in {"nsubj", "nsubjpass"} and t.pos_ == "NOUN"
        )
        if subject_count > 1:
            return True
    return False


# ---------------------------------------------------------------------------
# Precompiled swap patterns for the NL regex fallback
# ---------------------------------------------------------------------------
# These are compiled once at module load time to avoid recompilation on
# every call to the NL filter.

FEMALE_PRONOUN_PATTERNS = make_swap_pattern(FEMALE_TO_MALE_PRONOUNS)
MALE_PRONOUN_PATTERNS = make_swap_pattern(MALE_TO_FEMALE_PRONOUNS)

FEMALE_WORD_PATTERNS = make_swap_pattern(FEMALE_TO_MALE_WORDS)
MALE_WORD_PATTERNS = make_swap_pattern(MALE_TO_FEMALE_WORDS)

FEMALE_CLOTHING_NL_PATTERNS = make_swap_pattern(CLOTHING_FEMALE_TO_MALE_NL)
MALE_CLOTHING_NL_PATTERNS = make_swap_pattern(CLOTHING_MALE_TO_FEMALE_NL)

_NEO_TO_MALE = {k: v[0] for k, v in NEOPRONOUN_MAP.items()}
_NEO_TO_FEMALE = {k: v[1] for k, v in NEOPRONOUN_MAP.items()}
NEO_TO_MALE_PATTERNS = make_swap_pattern(_NEO_TO_MALE)
NEO_TO_FEMALE_PATTERNS = make_swap_pattern(_NEO_TO_FEMALE)

# Remove-only variants (for when swap is disabled)
_FEMALE_CLOTHING_REMOVE = {k: None for k in CLOTHING_FEMALE_TO_MALE_NL}
_MALE_CLOTHING_REMOVE = {k: None for k in CLOTHING_MALE_TO_FEMALE_NL}
FEMALE_CLOTHING_NL_REMOVE_PATTERNS = make_swap_pattern(_FEMALE_CLOTHING_REMOVE)
MALE_CLOTHING_NL_REMOVE_PATTERNS = make_swap_pattern(_MALE_CLOTHING_REMOVE)

# comfyui_dedupe_tags.py
"""
comfyui_dedupe_tags.py - comfyui-gender-tag-filter: Dedupe Tags Node
Copyright (c) 2026 Senjin the Dragon.
https://github.com/senjinthedragon/comfyui-gender-tag-filter
Licensed under the MIT License.
See LICENSE for full license information.

ComfyUI node (DedupeTags) that removes duplicate tags from a
comma-separated tag string, keeping the first occurrence of each.

Supports A1111/Forge emphasis syntax: (tag:1.3) and tag are correctly
identified as the same tag. LoRA syntax and the BREAK keyword are
preserved untouched.
"""

from .gender_shared import unwrap_emphasis, is_special_syntax, is_break_keyword


class DedupeTags:
    """
    Removes duplicate tags from a comma-separated tag string.
    Keeps the FIRST occurrence of each tag, removing any later duplicates.
    Leading/trailing whitespace is stripped from each tag.
    Empty tags (e.g. from double commas) are also removed.
    Underscore and space variants of the same tag are treated as duplicates
    (e.g. "big_fingers" and "big fingers" are considered identical).
    Emphasis-wrapped duplicates are detected: (large_breasts:1.3) and
    large_breasts are treated as the same tag (the first occurrence wins).
    LoRA syntax and BREAK keywords always pass through.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True}),
            },
            "optional": {
                "case_sensitive": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "dedupe"
    CATEGORY = "utils/tags"

    def dedupe(self, text, case_sensitive=False):
        # Split on comma, strip whitespace, drop empty strings
        tags = [t.strip() for t in text.split(",")]
        tags = [t for t in tags if t]

        seen = set()
        result = []

        for tag in tags:
            # Always pass through special syntax and BREAK untouched
            if is_special_syntax(tag) or is_break_keyword(tag):
                result.append(tag)
                continue

            # Unwrap emphasis to get the core tag for dedup comparison
            inner, _, _ = unwrap_emphasis(tag)

            # Normalise to lowercase with underscores for dedupe comparison.
            if case_sensitive:
                key = inner.replace(" ", "_")
            else:
                key = inner.lower().replace(" ", "_")

            if key not in seen:
                seen.add(key)
                result.append(tag)  # Always append original form

        return (", ".join(result),)


NODE_CLASS_MAPPINGS = {
    "DedupeTags": DedupeTags,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DedupeTags": "Dedupe Tags \U0001f3f7\ufe0f",
}

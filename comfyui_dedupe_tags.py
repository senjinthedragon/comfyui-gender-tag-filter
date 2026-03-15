# comfyui_dedupe_tags.py
"""
comfyui_dedupe_tags.py - comfyui-gender-tag-filter: Dedupe Tags Node
Copyright (c) 2026 Senjin the Dragon.
https://github.com/senjinthedragon/comfyui-gender-tag-filter
Licensed under the MIT License.
See LICENSE for full license information.

ComfyUI node (DedupeTags) that removes duplicate tags from a
comma-separated tag string, keeping the first occurrence of each.
"""

class DedupeTags:
    """
    Removes duplicate tags from a comma-separated tag string.
    Keeps the FIRST occurrence of each tag, removing any later duplicates.
    Leading/trailing whitespace is stripped from each tag.
    Empty tags (e.g. from double commas) are also removed.
    Underscore and space variants of the same tag are treated as duplicates
    (e.g. "big_fingers" and "big fingers" are considered identical).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True}),
            },
            "optional": {
                "delimiter": ("STRING", {"default": ", "}),
                "case_sensitive": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "dedupe"
    CATEGORY = "utils/tags"

    def dedupe(self, text, delimiter=", ", case_sensitive=False):
        # Split on comma, strip whitespace, drop empty strings
        tags = [t.strip() for t in text.split(",")]
        tags = [t for t in tags if t]

        seen = set()
        result = []

        for tag in tags:
            # Normalise to lowercase with underscores for dedupe comparison.
            if case_sensitive:
                key = tag.replace(" ", "_")
            else:
                key = tag.lower().replace(" ", "_")

            if key not in seen:
                seen.add(key)
                result.append(tag)  # Always append original casing/spacing

        return (delimiter.join(result),)


NODE_CLASS_MAPPINGS = {
    "DedupeTags": DedupeTags,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DedupeTags": "Dedupe Tags \U0001f3f7\ufe0f",
}

"""
__init__.py - comfyui-gender-tag-filter: Node Pack Entry Point
Copyright (c) 2026 Senjin the Dragon.
https://github.com/senjinthedragon/comfyui-gender-tag-filter
Licensed under the MIT License.
See LICENSE for full license information.

Registers all three nodes with ComfyUI: GenderTagFilter, GenderNLFilter,
and DedupeTags. All nodes appear under the utils/tags category.
"""

from .gender_tag_filter import (
    NODE_CLASS_MAPPINGS as TAG_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as TAG_DISPLAY_MAPPINGS,
)
from .gender_nl_filter import (
    NODE_CLASS_MAPPINGS as NL_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as NL_DISPLAY_MAPPINGS,
)
from .comfyui_dedupe_tags import (
    NODE_CLASS_MAPPINGS as DEDUP_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as DEDUP_DISPLAY_MAPPINGS,
)

NODE_CLASS_MAPPINGS = {**TAG_CLASS_MAPPINGS, **NL_CLASS_MAPPINGS, **DEDUP_CLASS_MAPPINGS}
NODE_DISPLAY_NAME_MAPPINGS = {**TAG_DISPLAY_MAPPINGS, **NL_DISPLAY_MAPPINGS, **DEDUP_DISPLAY_MAPPINGS}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

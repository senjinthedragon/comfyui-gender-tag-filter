# 🏷️ v1.1.0 - Dedupe Tags joins the pack

One new node, and the full pipeline now ships as a single install.

---

## What's new

**Dedupe Tags is now part of the node pack.**

It's the node you want between your tag concatenation step and the Gender Tag Filter. It removes duplicate tags from a comma-separated string, keeping the first occurrence of each.

The smart part: it treats underscores and spaces as equivalent, so `big_breasts` and `big breasts` are correctly identified as the same tag regardless of which form upstream nodes produce. TIPO and other prompt expanders regularly output both forms when you concatenate a static quality tag prefix with their output - without this, both variants survive and reach the CLIP encoder.

The node sits in the `utils/tags` category alongside the gender filter nodes, and like them it strips empty tags and double-comma artefacts automatically.

---

## Installation

No workflow changes needed if you were already using a dedupe node. The class name is `DedupeTags` and all inputs are identical to what you'd expect. Just update the pack and restart ComfyUI.

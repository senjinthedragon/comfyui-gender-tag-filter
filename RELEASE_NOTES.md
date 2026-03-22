# v1.2.1 - Source layout restored

A housekeeping patch. No functional changes.

---

## Highlights

### Human-readable data maps restored

The Ruff formatter had quietly collapsed all the neatly aligned data maps and replacement tables in `gender_shared.py` into dense, hard-to-read single-line style. The maps are now protected with `# fmt: off` / `# fmt: on` markers so the aligned column layout is preserved and stays that way.

If you ever want to add words, tags, or swap pairs to the data sets, `gender_shared.py` is once again easy to navigate and edit.

### Updated screenshot

The node reference screenshot has been updated to reflect the current node layout.

---

## Upgrading

No breaking changes. Drop-in replacement for v1.2.0.

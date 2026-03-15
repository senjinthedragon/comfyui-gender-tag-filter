# ComfyUI Gender Tag Filter

[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](https://opensource.org/licenses/MIT)
[![Author: Senjin the Dragon](https://img.shields.io/badge/Author-Senjin_the_Dragon-gold.svg)](https://github.com/senjinthedragon)

A ComfyUI node pack for filtering and rewriting gendered vocabulary in AI image generation prompts. Built to correct the female-biased output of prompt expansion models like TIPO when generating male or mixed-gender scenes.

_This is an independent node pack and is not affiliated with the ComfyUI development team._

<p align="center">
  <img src="https://raw.githubusercontent.com/senjinthedragon/comfyui-gender-tag-filter/main/assets/comfyui1.webp" alt="Workflow with both nodes chained together, showing output of each node.">
</p>

> [!IMPORTANT]
> **A note on scope**
>
> These nodes are prompt engineering utilities for AI image generation models. Their sole purpose is to help models produce output that matches your intended scene by adjusting the vocabulary in your prompt string before it reaches the CLIP encoder.
>
> They make no claims about gender identity, linguistics, or real people. All word mappings are chosen purely on the basis of what AI image generation models have been trained to recognise.

## Why does this exist?

Prompt expansion models such as TIPO are trained on large tag datasets that have a strong bias toward female characters and anatomy. When you feed them a male scene - particularly a gay or all-male furry scene - they frequently add female anatomy tags or feminise characters regardless of what you asked for. This causes the image model to generate unwanted female anatomy on your characters.

The standard workaround of adding `ban_tags` helps but is incomplete. This node pack adds a dedicated filtering stage that sits between your prompt expander and your CLIP encoder, and strips or rewrites any vocabulary that doesn't match your intended gender.

## Nodes

This pack contains two nodes, both found under `utils/tags` in the ComfyUI node browser. They are designed to work independently or in series.

### Gender Tag Filter 🏳️‍🌈

Filters gendered Danbooru and e621 style tag lists. Handles underscore and space separated tags, and is tolerant of inconsistent spacing around delimiters.

**Best used for:** pure tag prompts, or as the first stage in a mixed tag+NL pipeline.

### Gender NL Filter 🏳️‍🌈

Filters and rewrites gendered vocabulary in natural language prompts or mixed tag+NL prompts. Uses [spaCy](https://spacy.io/) for accurate negation detection and pronoun disambiguation, with automatic fallback to regex if spaCy is not installed.

**Best used for:** natural language prompts, SillyTavern character card descriptions, or as the second stage after Gender Tag Filter.

### Dedupe Tags 🏷️

Removes duplicate tags from a comma-separated tag string, keeping the first occurrence of each. Treats underscores and spaces as equivalent so `big_breasts` and `big breasts` are correctly identified as the same tag regardless of which form upstream nodes produce. Case-insensitive by default.

**Best used for:** cleaning up merged tag strings before they reach the CLIP encoder, particularly after concatenating a static quality tag prefix with TIPO output.

## Requirements

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) (latest recommended)
- Python 3.10–3.12 (comes with ComfyUI - see note below)
- (recommended) [spaCy](https://spacy.io/) for the NL Filter node - the tag filter node has no extra dependencies

> [!WARNING]
> **spaCy does not currently support Python 3.13 or 3.14.**
> spaCy depends on `pydantic v1` and `blis`, neither of which build successfully on Python 3.13 or 3.14 as of this writing. If you are running ComfyUI under Python 3.13 or 3.14, the Gender NL Filter node will automatically fall back to regex mode and log a message in the console. Everything still works - you just won't get the accuracy benefits of spaCy until upstream support catches up.
>
> If spaCy accuracy matters to you, create your ComfyUI venv explicitly under Python 3.12:
>
> ```shell
> python3.12 -m venv venv
> source venv/bin/activate   # Linux/Mac
> # or
> venv\Scripts\activate      # Windows
> pip install spacy
> python -m spacy download en_core_web_sm
> ```

## Installation

### 1. Install the node pack

Clone or download this repository into your ComfyUI custom nodes folder:

```shell
cd ComfyUI/custom_nodes
git clone https://github.com/senjinthedragon/comfyui-gender-tag-filter
```

Or download the ZIP and extract it so the folder structure looks like this:

```
ComfyUI/custom_nodes/comfyui-gender-tag-filter/
    __init__.py
    gender_shared.py
    gender_tag_filter.py
    gender_nl_filter.py
    comfyui_dedupe_tags.py
    README.md
```

### 2. Install spaCy (recommended)

Both nodes benefit from spaCy. The Gender NL Filter uses it for accurate negation detection and plural `they/them` disambiguation. The Gender Tag Filter uses it for more accurate detection of natural language fragments mixed into tag lists by TIPO. The nodes work without spaCy but accuracy is reduced in both cases.

```shell
pip install spacy
python -m spacy download en_core_web_sm
```

> [!TIP]
> If you are running ComfyUI in a virtual environment, make sure you activate it before running the commands above. If you installed ComfyUI via the Windows portable package, use the `python_embeded` Python that ships with it:
>
> ```shell
> .\python_embeded\python.exe -m pip install spacy
> .\python_embeded\python.exe -m spacy download en_core_web_sm
> ```

### 3. Restart ComfyUI

Both nodes will appear under `utils/tags` in the node browser after a restart.

## Usage

### Basic setup - tag-only prompt

Drop **Gender Tag Filter** between your prompt expander (e.g. TIPO, DedupeTags) and your CLIP encoder:

```
TIPO → DanbooruTagSnakeCaseFixer → IllustriousPromptSorter
     → StringConcatenate → [Dedupe Tags]
     → [Gender Tag Filter]
     → CLIPTextEncodeSDXL
```

### Extended setup - mixed tag + natural language prompt

Chain both nodes in series. The tag filter cleans the tag portion first, then the NL filter handles any natural language fragments:

```
... → DedupeTags → [Gender Tag Filter] → [Gender NL Filter] → CLIPTextEncodeSDXL
```

Since both nodes take a `STRING` input and return a `STRING` output, they wire together directly with no adapter nodes needed.

> [!TIP]
> The Gender NL Filter has a second output called `backend_used` which returns either `spacy`, `regex`, or `off`. You do not need to connect it to anything, but wiring it to a **ShowText** node while you are getting set up is a handy way to confirm spaCy is running without having to dig through the console.

## Node Reference

### Gender Tag Filter

| Input                 | Type     | Default             | Description                                                                                                                                                                                                      |
| --------------------- | -------- | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `text`                | STRING   | -                   | Tag string to filter                                                                                                                                                                                             |
| `mode`                | dropdown | `strip_female_tags` | `strip_female_tags`, `strip_male_tags`, or `off`                                                                                                                                                                 |
| `filter_anatomy`      | boolean  | true                | Remove anatomical tags. Also scans compound tags for root words, so `huge_breasts`, `breast_grab` etc. are caught even if not individually listed.                                                               |
| `filter_presentation` | boolean  | false               | Also remove gendered clothing and accessory tags. Disable for crossdressing characters.                                                                                                                          |
| `apply_replacements`  | boolean  | false               | Replace removed anatomy tags with gender-appropriate counterparts instead of deleting them. e.g. `large_breasts` → `muscular_chest`, `breasts` → `pecs`                                                          |
| `swap_clothing_tags`  | boolean  | true                | When `filter_presentation` is on, replace clothing tags with equivalents instead of removing. e.g. `skirt` → `trousers`, `bikini` → `swim_trunks`, `bra` → removed. No effect when `filter_presentation` is off. |
| `map_neopronouns`     | boolean  | true                | Map neopronoun tags (`shi`, `hir`, `they`, `xe`, `ze`, `ey`, `fae` etc.) to binary equivalents image models recognise. Same set as the NL Filter for consistent standalone behaviour.                            |
| `handle_negations`    | boolean  | true                | Protect tags that appear in a negated context in mixed prompts from removal. Uses a 4-token proximity heuristic.                                                                                                 |
| `tag_format`          | dropdown | `underscores`       | Output word separator style. `underscores` for most models, `spaces` for some fine-tuned models. Input always accepted in either style. Natural language fragments bypass this entirely.                         |
| `delimiter`           | string   | `, `                | Tag separator for output. Input is parsed forgivingly.                                                                                                                                                           |
| `spacy_model`         | string   | `en_core_web_sm`    | spaCy model for NL fragment detection. Falls back to stop-word heuristic if not installed.                                                                                                                       |

### Gender NL Filter

| Input                 | Type     | Default                 | Description                                                                                                                                                                                                                      |
| --------------------- | -------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `text`                | STRING   | -                       | Prompt to filter                                                                                                                                                                                                                 |
| `mode`                | dropdown | `strip_female_language` | `strip_female_language`, `strip_male_language`, or `off`                                                                                                                                                                         |
| `filter_anatomy`      | boolean  | true                    | Process anatomy words at all. Turn off to leave all anatomy language completely untouched.                                                                                                                                       |
| `replace_anatomy`     | boolean  | true                    | Replace anatomy words with gender-appropriate counterparts rather than removing them. e.g. `Her breasts bounced` → `His pecs bounced`. Words with no clean equivalent are still removed. No effect when `filter_anatomy` is off. |
| `handle_negations`    | boolean  | true                    | Protect negated anatomy terms. e.g. `no breasts`, `without a vagina` left untouched. spaCy uses dependency parsing; regex uses 4-token heuristic.                                                                                |
| `handle_pronouns`     | boolean  | true                    | Swap binary gendered pronouns. `she/her/hers/herself` ↔ `he/him/his/himself`                                                                                                                                                     |
| `rewrite_references`  | boolean  | true                    | Swap gendered nouns and adjectives. `woman/girl/lady` ↔ `man/boy/guy` etc. Also covers furry terms: `vixen/doe/mare/tigress` etc.                                                                                                |
| `filter_presentation` | boolean  | true                    | Process clothing and accessory language at all. Turn off to leave all clothing language untouched. Useful for crossdressing characters.                                                                                          |
| `swap_clothing`       | boolean  | true                    | Replace clothing terms with equivalents rather than removing. e.g. `dress` → `suit`, `skirt` → `trousers`, `bra` → removed. No effect when `filter_presentation` is off.                                                         |
| `map_neopronouns`     | boolean  | true                    | Map neopronouns to binary equivalents. Covers `shi/hir` (Chakat/furry), `they/them`, `xe/xem`, `ze/zir`, `ey/em` (Spivak), `fae/faer`. Plural `they/them` preserved by spaCy.                                                    |
| `spacy_model`         | string   | `en_core_web_sm`        | spaCy model for NLP processing. Falls back to regex if not installed.                                                                                                                                                            |

**Outputs (NL Filter only):**

| Output          | Type   | Description                                       |
| --------------- | ------ | ------------------------------------------------- |
| `filtered_text` | STRING | The processed prompt                              |
| `backend_used`  | STRING | `spacy`, `regex`, or `off` - useful for debugging |

### Dedupe Tags

| Input            | Type    | Default | Description                                                                                                                                            |
| ---------------- | ------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `text`           | STRING  | -       | Comma-separated tag string to dedupe                                                                                                                   |
| `delimiter`      | string  | `, `    | Separator used in the output                                                                                                                           |
| `case_sensitive` | boolean | false   | When off, `Big_Breasts` and `big breasts` are treated as the same tag. When on, only exact matches (after underscore/space normalisation) are deduped. |

## Crossdressing characters

If your character is intentionally wearing clothing associated with a different gender, turn off `filter_presentation` on both nodes. This preserves all clothing tags and language while still removing anatomy tags that don't match your character. The tag filter's `filter_presentation` and the NL filter's `filter_presentation` work the same way - turning both off is the single switch for full crossdressing support.

## spaCy model sizes

| Model            | Size    | Notes                                                                          |
| ---------------- | ------- | ------------------------------------------------------------------------------ |
| `en_core_web_sm` | ~12 MB  | Recommended. Good accuracy for prompt-length text.                             |
| `en_core_web_md` | ~43 MB  | Better word vectors, marginal improvement for this use case.                   |
| `en_core_web_lg` | ~560 MB | Best accuracy. Worthwhile if you are processing longer character descriptions. |

> [!NOTE]
> spaCy models are tiny compared to the checkpoints you are already running. The small model is 12MB. Your checkpoint is probably 6GB. Install spaCy.

## Troubleshooting

**Node doesn't appear in ComfyUI:**\
Make sure the folder is directly inside `ComfyUI/custom_nodes/` and contains `__init__.py`. Restart ComfyUI fully after installing.

**`backend_used` shows `regex` but I installed spaCy:**\
Make sure you installed spaCy into the same Python environment that ComfyUI is using. If you are on the Windows portable package, use `python_embeded\python.exe -m pip install spacy` rather than a system Python. Check the ComfyUI console for the warning message - it will tell you exactly what went wrong.

**Compound tags like `furry with non-furry` or `tongue out` are being treated as natural language:**\
Update to v1.0.1 - this was a bug in the NL fragment detector's stop word list. Words like `with`, `out`, `from`, `at` were incorrectly flagged as natural language markers, causing common Danbooru compound tags to bypass underscore formatting.

**Tags with spaces are not being matched:**\
Both nodes normalise tags internally - `large breasts` and `large_breasts` are treated as the same tag regardless of your `tag_format` setting. If a tag is still slipping through, check that it is in the blocklist in `gender_shared.py`. The lists are plain Python sets and are easy to extend.

**Negated anatomy is being removed anyway:**\
You are likely running on the regex fallback rather than spaCy. The regex heuristic scans 4 tokens back for a negation word, which covers most cases but not all sentence structures. Install spaCy for reliable negation detection.

**Plural `they/them` is being swapped when it shouldn't be:**\
Same as above - this distinction requires spaCy. The regex fallback cannot reliably tell singular from plural `they/them` and will remap both.

**spaCy fails to install with errors about `blis`, `thinc`, or `pydantic`:**\
You are most likely running Python 3.13 or 3.14. spaCy does not currently support either version due to incompatibilities in its `pydantic v1` and `blis` dependencies. The `blis` build failure also triggers a secondary gcc error (`unrecognized command-line option '-mavx512pf'`) on systems with gcc 14 or newer, which compounds the problem. The node will run correctly on the regex fallback in the meantime. To use spaCy, recreate your ComfyUI venv under Python 3.12 - see the [Requirements](#requirements) section for instructions.

## ☕ Support the Developer

I'm a solo developer building tools to make AI-assisted roleplay and image generation better for the community. I maintain these projects in my free time, and any support is genuinely appreciated.

If this node pack saves you frustration, please consider:

- **[Sponsoring me on GitHub](https://github.com/sponsors/senjinthedragon)**
- **[Buying me a coffee on Ko-fi](https://ko-fi.com/senjinthedragon)**
- **Starring this repository** to help others find it

## License

This project is licensed under the [MIT License](LICENSE).

# 🏳️‍🌈 He Said, She Said - Let the Model Say What You Actually Want

If you've ever used TIPO or another prompt expansion model to generate male or all-male scenes and watched it cheerfully add breasts, vaginas, and feminine pronouns to your characters anyway - this node pack is for you.

TIPO is great at what it does. The problem is that it was trained on a dataset with a heavy female bias, and it shows. `ban_tags` helps but it's playing whack-a-mole. This pack adds a proper filtering stage directly in your ComfyUI workflow, between your prompt expander and your CLIP encoder, that strips or rewrites any gendered vocabulary that doesn't match your intended scene.

---

## What's in the box

Two nodes, both found under **utils/tags** in the node browser. They're designed to work standalone or chained together.

### Gender Tag Filter

Handles Danbooru and e621 style tag lists. Drops or replaces anatomy tags, clothing tags, and gendered character tags. Smart enough to catch compound tags it's never seen before - `huge_breasts`, `breast_grab`, `hanging_breasts` are all caught without being individually listed, because it knows `breasts` is an anatomy root word. Also detects natural language fragments that TIPO sometimes sneaks into its output and passes them through untouched for the NL filter to handle.

### Gender NL Filter

Handles natural language prompts and mixed content. Swaps pronouns, rewrites gendered nouns and adjectives, replaces clothing descriptions, and maps neopronouns to binary equivalents that image models actually understand. When `replace_anatomy` is on, anatomy words in sentences are substituted rather than deleted - so `Her breasts bounced` becomes `His pecs bounced` rather than `His bounced`. Uses [spaCy](https://spacy.io/) for accurate negation detection (`no breasts` is left alone) and plural `they/them` disambiguation, with automatic regex fallback if spaCy isn't installed.

---

## Highlights

**Neopronoun support** - covers `shi/hir` (Chakat/furry), `they/them`, `xe/xem`, `ze/zir`, `ey/em` (Spivak), and `fae/faer`. Maps them to binary equivalents that image models recognise from their training data, because feeding `xe` to a SDXL model is not going to do what you want. Toggle it off if you want to preserve them.

**Crossdressing characters** - both nodes have independent toggles for anatomy and presentation/clothing. Turn off clothing filtering and your character keeps their outfit; anatomy filtering still runs. It was designed with the furry fandom in mind where this comes up constantly.

**Mixed prompt handling** - TIPO sometimes outputs a tag list with a natural language sentence or two mixed in. The tag filter detects these fragments and routes them to the NL filter rather than mangling their spacing with underscores.

**Works without spaCy** - the regex fallback covers most real-world cases. spaCy just makes negation detection and plural pronoun disambiguation significantly more reliable. See the README for install instructions.

---

## spaCy and Python 3.13 / 3.14

spaCy currently does not install on Python 3.13 or 3.14 due to upstream incompatibilities with `pydantic v1` and `blis`. If you're on a recent Arch or other rolling release system you may run into this. Both nodes fall back to regex automatically, so nothing breaks - you just get slightly less accurate negation handling. The README has instructions for setting up a Python 3.12 venv if you want full spaCy support.

---

## Installation

```shell
cd ComfyUI/custom_nodes
git clone https://github.com/senjinthedragon/comfyui-gender-tag-filter
```

Then optionally:

```shell
pip install spacy
python -m spacy download en_core_web_sm
```

Restart ComfyUI and both nodes appear under **utils/tags**.

---

Built for the furry AI art community, but useful for anyone whose prompt expander keeps ignoring what they asked for. If it saves you frustration, a star on the repo goes a long way.

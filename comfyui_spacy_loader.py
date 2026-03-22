"""
comfyui_spacy_loader.py - comfyui-gender-tag-filter: SpaCy Model Loader Node
Copyright (c) 2026 Senjin the Dragon.
https://github.com/senjinthedragon/comfyui-gender-tag-filter
Licensed under the MIT License.
See LICENSE for full license information.

Loads a spaCy language model from ComfyUI/models/spacy/ and outputs it as a
SPACY_NLP object for use by GenderTagFilter and GenderNLFilter. Wire this node
into the spacy_nlp input on either filter node to enable spaCy-backed processing.

Models are loaded by directory path rather than package name, so they do not
need to be installed via pip. Place an extracted spaCy model folder (the one
that contains meta.json) inside ComfyUI/models/spacy/ and it will appear in
the dropdown automatically.

To download and place a model:
  python -m spacy download en_core_web_sm
  # locate the downloaded folder (the versioned inner folder with meta.json)
  # and move it into ComfyUI/models/spacy/

If spaCy is not installed, or the models/spacy/ directory is empty, this node
raises a clear error rather than silently falling back. Leave the spacy_nlp
input disconnected on the filter nodes to use their regex/heuristic fallback.
"""

import os


def _get_spacy_models_dir() -> str | None:
    try:
        import folder_paths
        paths = folder_paths.get_folder_paths("spacy")
        return paths[0] if paths else None
    except Exception:
        return None


def _find_inner_model(folder_path: str) -> str | None:
    """
    If folder_path is a pip package wrapper (no meta.json directly, but a
    versioned subfolder containing one), return the path to that inner folder.
    Otherwise return None.
    """
    try:
        for sub in sorted(os.listdir(folder_path)):
            inner = os.path.join(folder_path, sub)
            if os.path.isdir(inner) and os.path.isfile(os.path.join(inner, "meta.json")):
                return inner
    except OSError:
        pass
    return None


def _scan_spacy_models() -> list[str]:
    """
    Return a sorted list of candidate model names from the models/spacy/ folder.

    Includes both correctly placed models (meta.json directly inside the folder)
    and wrapper folders (pip package structure where meta.json is one level
    deeper inside a versioned subfolder). Both kinds appear in the dropdown;
    wrapper folders produce a clear error at load time with instructions.
    """
    models_dir = _get_spacy_models_dir()
    if not models_dir or not os.path.isdir(models_dir):
        return []

    models = []
    for name in sorted(os.listdir(models_dir)):
        candidate = os.path.join(models_dir, name)
        if not os.path.isdir(candidate):
            continue
        if os.path.isfile(os.path.join(candidate, "meta.json")):
            models.append(name)
        elif _find_inner_model(candidate) is not None:
            models.append(name)
    return models


_NO_MODELS_PLACEHOLDER = "(no models found in models/spacy/)"


class SpaCyModelLoader:
    CATEGORY = "utils/tags"
    FUNCTION = "load"
    RETURN_TYPES = ("SPACY_NLP",)
    RETURN_NAMES = ("spacy_nlp",)

    @classmethod
    def INPUT_TYPES(cls):
        models = _scan_spacy_models()
        choices = models if models else [_NO_MODELS_PLACEHOLDER]
        return {
            "required": {
                "model": (choices, {
                    "tooltip": (
                        "spaCy model to load. Models are read from ComfyUI/models/spacy/.\n"
                        "Any subfolder containing a meta.json appears here.\n\n"
                        "To add a model, download it and place the inner model folder\n"
                        "(the versioned subfolder containing meta.json) into models/spacy/:\n"
                        "  python -m spacy download en_core_web_sm\n\n"
                        "Common models:\n"
                        "  en_core_web_sm   ~12 MB  - recommended for most cases\n"
                        "  en_core_web_md   ~43 MB  - better word vectors\n"
                        "  en_core_web_lg  ~560 MB  - best statistical accuracy\n"
                        "  en_core_web_trf ~400 MB  - transformer-based, highest accuracy\n"
                        "                            (requires: pip install spacy-transformers)"
                    ),
                }),
            }
        }

    def load(self, model):
        if model == _NO_MODELS_PLACEHOLDER:
            raise RuntimeError(
                "No spaCy models found in ComfyUI/models/spacy/.\n"
                "Download a model and place the inner model folder there:\n"
                "  python -m spacy download en_core_web_sm\n"
                "  # move the versioned inner folder (containing meta.json)\n"
                "  # into ComfyUI/models/spacy/"
            )

        try:
            import spacy
        except ImportError:
            raise RuntimeError(
                "spaCy is not installed.\n"
                "Install it with:  pip install spacy"
            )

        models_dir = _get_spacy_models_dir()
        model_path = os.path.join(models_dir, model)

        # ── Wrapper detection ─────────────────────────────────────────────────
        # When a user runs `python -m spacy download en_core_web_sm` they get
        # an outer pip package folder that contains a versioned inner folder:
        #   en_core_web_sm/
        #     __init__.py
        #     en_core_web_sm-3.8.0/   <- this is the actual model (has meta.json)
        #       meta.json
        #       ...
        # If they copied the outer folder instead of the inner one, we detect it
        # and tell them exactly what to move and where.
        if not os.path.isfile(os.path.join(model_path, "meta.json")):
            inner = _find_inner_model(model_path)
            if inner is not None:
                inner_name = os.path.basename(inner)
                raise RuntimeError(
                    f"'{model}' is the outer pip package folder, not the model itself.\n"
                    f"Move the inner versioned folder into models/spacy/ instead:\n"
                    f"  From: {inner}\n"
                    f"  To:   {os.path.join(models_dir, inner_name)}\n"
                    f"You can rename it to '{model}' after moving if you prefer."
                )
            raise RuntimeError(
                f"'{model}' does not appear to be a valid spaCy model folder.\n"
                f"A valid model folder must contain a meta.json file.\n"
                f"Path checked: {model_path}"
            )

        try:
            nlp = spacy.load(model_path)
        except OSError as e:
            raise RuntimeError(
                f"Failed to load spaCy model '{model}' from {model_path}.\n"
                f"The folder exists but may be corrupt or incomplete.\n"
                f"Original error: {e}"
            )

        return (nlp,)


NODE_CLASS_MAPPINGS = {
    "SpaCyModelLoader": SpaCyModelLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SpaCyModelLoader": "SpaCy Model Loader 🔬",
}

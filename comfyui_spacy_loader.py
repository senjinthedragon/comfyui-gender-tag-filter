"""
comfyui_spacy_loader.py - comfyui-gender-tag-filter: SpaCy Model Loader Node
Copyright (c) 2026 Senjin the Dragon.
https://github.com/senjinthedragon/comfyui-gender-tag-filter
Licensed under the MIT License.
See LICENSE for full license information.

Loads a spaCy language model and outputs it as a SPACY_NLP object for use
by GenderTagFilter and GenderNLFilter. Wire this node into the spacy_nlp
input on either filter node to enable spaCy-backed processing.

Models are detected automatically from the active Python environment via
spacy.util.get_installed_models(). Install a model with:
  python -m spacy download en_core_web_sm

If spaCy is not installed, or no models are downloaded yet, this node raises
a clear error with install instructions. Leave the spacy_nlp input disconnected
on the filter nodes to use their regex/heuristic fallback instead.
"""


def _scan_spacy_models() -> list[str]:
    """Return a sorted list of spaCy model names installed in the current environment."""
    try:
        import spacy
        return sorted(spacy.util.get_installed_models())
    except Exception:
        return []


_NO_MODELS_PLACEHOLDER = "(no spaCy models installed)"


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
                        "spaCy model to load. Lists all models installed in the\n"
                        "current Python environment.\n\n"
                        "Install a model with:\n"
                        "  python -m spacy download en_core_web_sm\n"
                        "Then restart ComfyUI.\n\n"
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
                "No spaCy models are installed.\n"
                "Install one with:\n"
                "  python -m spacy download en_core_web_sm\n"
                "Then restart ComfyUI."
            )

        try:
            import spacy
        except ImportError:
            raise RuntimeError(
                "spaCy is not installed.\n"
                "Install it with:  pip install spacy\n"
                "Then download a model:  python -m spacy download en_core_web_sm"
            )

        try:
            nlp = spacy.load(model)
        except OSError as e:
            raise RuntimeError(
                f"Failed to load spaCy model '{model}'.\n"
                f"Original error: {e}"
            )

        return (nlp,)


NODE_CLASS_MAPPINGS = {
    "SpaCyModelLoader": SpaCyModelLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SpaCyModelLoader": "SpaCy Model Loader 🔬",
}

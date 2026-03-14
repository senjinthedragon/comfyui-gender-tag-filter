import warnings
warnings.filterwarnings("ignore", message=".*urllib3.*", module="requests")

import sys
import subprocess

def install_spacy_model():
    try:
        import spacy
        # Check if the model is already there
        if not spacy.util.is_package("en_core_web_sm"):
            print("Gender Filter: Downloading spaCy model 'en_core_web_sm'...")
            subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
    except ImportError:
        # We don't force-install spaCy here because the node has a regex fallback.
        # We just let the user know it's an option.
        print("Gender Filter: spaCy not found. Node will run in Regex Fallback mode (Standard).")
        print("To enable high-accuracy NLP mode, run: pip install spacy")

if __name__ == "__main__":
    install_spacy_model()
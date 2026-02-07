import os

# API Keys - imported from secrets.py (not committed to git)
try:
    from .secrets import ANTHROPIC_API_KEY, UNSTRUCTURED_API_KEY
except ImportError:
    # Fallback to environment variables if secrets.py doesn't exist
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    UNSTRUCTURED_API_KEY = os.environ.get("UNSTRUCTURED_API_KEY", "")


# LLM Configuration
LLM_MODEL = "claude-opus-4-6"
LLM_MODEL_LIGHT = "claude-haiku-4-5-20251001"
EMBEDDING_MODEL = None # Deprecated

# Output
OUTPUT_DIR = "output"

# Input
INPUT_DIR = "inputs" # User requested 'inputs' folder.

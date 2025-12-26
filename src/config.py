import os

VERSION = "0.0.2"
MODEL_NAME = os.environ.get("LOKALITY_MODEL", "gemma3:4b-it-qat")

# This can be toggled at runtime via /debug
DEBUG = os.environ.get("DEBUG", "0") == "1"

import os

VERSION = "v0.1.0"
MODEL_NAME = os.environ.get("LOKALITY_MODEL", "gemma3:4b-it-qat")

# Model performance tuning
SEARCH_DECISION_MAX_TOKENS = 30
RESPONSE_MAX_TOKENS = 300
MEMORY_EXTRACTION_MAX_TOKENS = 200
CONTEXT_WINDOW_SIZE = 4096

# This can be toggled at runtime via /debug
DEBUG = os.environ.get("DEBUG", "0") == "1"

# Logging configuration
LOG_DIR = "logs"
MAX_LOG_AGE_DAYS = 30
MIN_LOGS_FOR_CLEANUP = 10

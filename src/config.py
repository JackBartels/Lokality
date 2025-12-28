import os

VERSION = "v0.0.3"
MODEL_NAME = os.environ.get("LOKALITY_MODEL", "gemma3:4b-it-qat")

# This can be toggled at runtime via /debug
DEBUG = os.environ.get("DEBUG", "0") == "1"

# Logging configuration
LOG_DIR = "logs"
MAX_LOG_AGE_DAYS = 30
MIN_LOGS_FOR_CLEANUP = 10

import os

VERSION = "v0.1.0"
MODEL_NAME = os.environ.get("LOKALITY_MODEL", "gemma3:4b-it-qat")

# Default models ordered by size/resource requirement
# VRAM requirements: 270m/1b (BF16) + buffer, 4b/12b (Q4_0) + buffer
DEFAULT_MODELS = [
    {"name": "gemma3:270m", "min_vram_mb": 640},    # ~400MB (BF16)
    {"name": "gemma3:1b", "min_vram_mb": 2048},     # ~1.5GB (BF16)
    {"name": "gemma3:4b-it-qat", "min_vram_mb": 4096}, # ~3.4GB (Q4_0)
    {"name": "gemma3:12b-it-qat", "min_vram_mb": 10240}, # ~8.7GB (Q4_0)
]

# Model performance tuning
SEARCH_DECISION_MAX_TOKENS = 30
MEMORY_EXTRACTION_MAX_TOKENS = 200
CONTEXT_WINDOW_SIZE = 4096

# This can be toggled at runtime via /debug
DEBUG = os.environ.get("DEBUG", "0") == "1"

# Logging configuration
LOG_DIR = "logs"
MAX_LOG_AGE_DAYS = 30
MIN_LOGS_FOR_CLEANUP = 10

"""
Statistics collection for Lokality.
Monitors model resource usage and estimates context window consumption.
"""
import ollama

from config import MODEL_NAME
from logger import logger
from utils import debug_print

client = ollama.Client()

def _estimate_tokens(text):
    """
    Improved heuristic for token estimation.
    """
    if not text:
        return 0

    # 1. Base: average of char-based and word-based heuristics
    char_tokens = len(text) / 4.0
    word_tokens = len(text.split()) * 1.3

    # 2. Density correction (code, symbols)
    symbol_count = len([c for c in text if not c.isalnum() and not c.isspace()])
    density_bonus = (symbol_count / len(text)) * 2.0 if len(text) > 0 else 0

    base_estimate = (char_tokens + word_tokens) / 2.0
    return int(base_estimate * (1.0 + density_bonus))

def _get_resource_usage(stats):
    """Fetches RAM and VRAM usage from Ollama ps."""
    try:
        ps = client.ps()
        models_list = getattr(ps, 'models', ps)
        for m in models_list:
            if m.model.split(":")[0] in MODEL_NAME or MODEL_NAME in m.model:
                vram_bytes = getattr(m, 'size_vram', 0)
                total_bytes = getattr(m, 'size', 0)
                stats["vram_mb"] = vram_bytes // (1024 * 1024)
                stats["ram_mb"] = max(
                    0, (total_bytes - vram_bytes) // (1024 * 1024)
                )
                break
    except (AttributeError, ollama.ResponseError):
        pass

def get_model_info(memory_store, system_prompt, messages):
    """Gathers statistics about the model and system."""
    stats = {
        "model": MODEL_NAME,
        "context_pct": 0,
        "memory_entries": memory_store.get_fact_count(),
        "ram_mb": 0,
        "vram_mb": 0
    }

    try:
        _get_resource_usage(stats)

        # Context estimation
        show = client.show(MODEL_NAME)
        show_dict = show.model_dump()
        max_ctx = 8192 # Default fallback
        model_info = show_dict.get('modelinfo', {})
        for key, val in model_info.items():
            if 'context_length' in key:
                max_ctx = val
                break

        total_tokens = _estimate_tokens(system_prompt)
        for msg in messages:
            total_tokens += _estimate_tokens(msg['content'])

        stats["context_pct"] = min(100, (total_tokens / max_ctx) * 100)

    except (AttributeError, ollama.ResponseError) as exc:
        logger.warning("Error gathering stats: %s", exc)
        debug_print(f"[*] Error gathering info: {exc}")

    return stats

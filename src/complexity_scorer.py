"""
Complexity and Creativity analysis for user prompts.
Adjusts LLM parameters dynamically based on predicted effort.
"""
import math
import re
import time
from typing import Dict, Any

import ollama

import config
from utils import get_system_resources, debug_print

class ComplexityScorer:
    """
    Analyzes user input to predict the required thinking effort (Complexity)
    and output variability (Creativity) of the model's response.
    """

    _model_context_cache = {}
    _model_size_cache = {"size": 0, "expires": 0}

    # Complexity Levels
    LEVEL_MINIMAL = "MINIMAL"
    LEVEL_SIMPLE = "SIMPLE"
    LEVEL_MODERATE = "MODERATE"
    LEVEL_COMPLEX = "COMPLEX"

    # Verbs and nouns indicating a high-effort thinking/reasoning task
    TASK_INTENSITY_KEYWORDS = {
        "analyze", "analysis", "compare", "contrast", "explain", "why",
        "describe", "summarize", "refactor", "debug", "solve", "math",
        "calculate", "logic", "proof", "architecture", "impact", "relationship",
        "consequence", "difference", "history", "scientific", "detailed",
        "step-by-step", "implementation", "optimization", "comprehensive",
        "advanced", "complex"
    }

    # Technical/Formal domain markers (Predicts Determinism)
    DETERMINISTIC_DOMAIN_KEYWORDS = {
        "code", "coding", "program", "function", "class", "variable",
        "interface", "api", "json", "csv", "table", "strict", "sql",
        "database", "python", "javascript", "c++", "rust", "equation",
        "formula", "data", "deep", "neural"
    }

    # Keywords suggesting creative/divergent thinking (Predicts Creativity)
    CREATIVE_INTENT_KEYWORDS = {
        "story", "poem", "imagine", "joke", "funny", "metaphor",
        "analogy", "brainstorm", "lyrics", "fiction", "plot", "character",
        "dialogue", "creative writing", "improv", "scenario", "beautiful",
        "narrative", "myth", "legend", "haiku", "sonnet", "fable", "creative",
        "fictional", "abstract", "artistic", "personality", "whimsical"
    }

    # Conversational fillers (Predicts low-effort response)
    SIMPLE_KEYWORDS = {
        "hi", "hello", "hey", "thanks", "thank", "bye", "goodbye",
        "ok", "okay", "cool", "nice", "yep", "nope", "yes", "no"
    }

    @staticmethod
    def _get_model_max_ctx() -> int:
        """Retrieves the model's native context window from Ollama."""
        model_name = config.MODEL_NAME
        if model_name in ComplexityScorer._model_context_cache:
            return ComplexityScorer._model_context_cache[model_name]

        try:
            client = ollama.Client()
            info = client.show(model_name).model_dump()
            model_info = info.get('modelinfo', {})
            for key, val in model_info.items():
                if 'context_length' in key:
                    ComplexityScorer._model_context_cache[model_name] = val
                    return val
        except (AttributeError, ollama.ResponseError):
            pass
        return 8192 # Default safe fallback

    @staticmethod
    def _get_loaded_model_size_mb() -> int:
        """Estimates the size of the currently loaded model, cached for 60s."""
        now = time.time()
        if now < ComplexityScorer._model_size_cache["expires"]:
            return ComplexityScorer._model_size_cache["size"]

        try:
            client = ollama.Client()
            ps = client.ps()
            # ps is a list of models or a structure with 'models' attribute
            models_list = getattr(ps, 'models', ps)
            for m in models_list:
                if (m.model.split(":")[0] in config.MODEL_NAME or
                        config.MODEL_NAME in m.model):
                    size_mb = m.size // (1024 * 1024)
                    ComplexityScorer._model_size_cache = {
                        "size": size_mb,
                        "expires": now + 60
                    }
                    return size_mb
        except (AttributeError, ollama.ResponseError):
            pass
        return 0

    @staticmethod
    def _calculate_ari(text: str) -> float:
        """Calculates ARI to gauge the linguistic sophistication of the request."""
        characters = len(re.sub(r'[^a-zA-Z0-9]', '', text))
        words = text.split()
        num_words = len(words)
        num_sentences = len(re.findall(r'[.!?]+', text)) or 1
        if num_words == 0:
            return 0.0
        ari = (4.71 * (characters / num_words) +
               0.5 * (num_words / num_sentences) - 21.43)
        return max(0.0, min(1.0, ari / 14.0))

    @staticmethod
    def _get_structural_score(text: str) -> float:
        """Detects structural markers in the prompt."""
        score = 0.0
        questions = text.count('?')
        if questions > 1:
            score += 0.5 * min(questions, 2)
        if "```" in text:
            score += 0.7
        if re.search(r'^\s*[-*•]\s+', text, re.MULTILINE):
            score += 0.4
        return min(1.0, score)

    @staticmethod
    def get_safe_context_size(requested_ctx: int) -> int:
        """
        Calculates a VRAM-safe context window size based on system resources.
        """
        model_max = ComplexityScorer._get_model_max_ctx()
        model_size_mb = ComplexityScorer._get_loaded_model_size_mb()
        _, vram_mb = get_system_resources()

        # Start with Total VRAM (fallback to 2048 if detection fails)
        total_vram = vram_mb or 2048
        available_headroom = max(0, total_vram - model_size_mb)
        safe_headroom = max(0, available_headroom - 256)
        capped_headroom = safe_headroom * 0.7

        # Assume 0.25MB per token for KV cache + overhead
        vram_tokens_limit = int(capped_headroom / 0.25)

        return max(512, min(requested_ctx, model_max, vram_tokens_limit))

    @staticmethod
    def _get_complexity_metrics(user_input: str):
        """Calculates complexity and creativity raw scores."""
        lower_input = user_input.lower()
        intensity_hits = sum(1 for kw in ComplexityScorer.TASK_INTENSITY_KEYWORDS
                             if kw in lower_input)
        det_domain_hits = sum(1 for kw in ComplexityScorer.DETERMINISTIC_DOMAIN_KEYWORDS
                              if kw in lower_input)
        intent_score = (intensity_hits * 0.4) + (det_domain_hits * 0.3)

        ari_score = ComplexityScorer._calculate_ari(user_input)
        struct_score = ComplexityScorer._get_structural_score(user_input)

        word_count = len(user_input.split())
        len_score = min(1.0, math.log(word_count + 1, 80)) if word_count > 0 else 0.0

        total_complexity = (intent_score * 0.5 + struct_score * 0.25 +
                            ari_score * 0.15 + len_score * 0.1)

        simple_hits = sum(1 for kw in ComplexityScorer.SIMPLE_KEYWORDS
                          if kw in lower_input)
        if (simple_hits > 0 and intensity_hits == 0 and
                det_domain_hits == 0 and word_count < 10):
            total_complexity -= 0.4

        creative_hits = sum(1 for kw in ComplexityScorer.CREATIVE_INTENT_KEYWORDS
                             if kw in lower_input)
        creative_intensity = 0.0
        if creative_hits > 0:
            creative_intensity = 0.4 + (min(creative_hits - 1, 3) * 0.2)

        creativity_score = creative_intensity - (det_domain_hits * 0.3)
        return (
            round(max(0.0, min(1.0, total_complexity)), 2),
            round(max(0.0, min(1.0, creativity_score)), 2),
            {
                "intent": round(intent_score, 2),
                "ari": round(ari_score, 2),
                "struct": round(struct_score, 2),
                "len": round(len_score, 2)
            }
        )

    @staticmethod
    def analyze(user_input: str) -> Dict[str, Any]:
        """
        Calculates predicted complexity and creativity scores for the response.
        """
        if not user_input.strip():
            return {
                "score": 0.0, "creativity": 0.0, "level": "MINIMAL",
                "params": {
                    "num_ctx": 512, "num_predict": -1,
                    "temperature": 0.1, "top_p": 0.4
                }
            }

        score, creativity, raw = ComplexityScorer._get_complexity_metrics(user_input)
        debug_print(
            f"[*] Analysis - Complexity: {score} (Intent:{raw['intent']}, "
            f"ARI:{raw['ari']}, Struct:{raw['struct']}, Len:{raw['len']}), "
            f"Creativity: {creativity}"
        )

        if score <= 0.02:
            level, requested_ctx, base_penalty = ComplexityScorer.LEVEL_MINIMAL, 512, 1.05
        elif score < 0.15:
            level, requested_ctx, base_penalty = ComplexityScorer.LEVEL_SIMPLE, 2048, 1.1
        elif score < 0.45:
            level, requested_ctx, base_penalty = ComplexityScorer.LEVEL_MODERATE, 3072, 1.15
        else:
            level, requested_ctx, base_penalty = ComplexityScorer.LEVEL_COMPLEX, 4096, 1.2

        final_ctx = ComplexityScorer.get_safe_context_size(requested_ctx)

        params = {
            "num_ctx": final_ctx, "num_predict": -1,
            "temperature": round(0.1 + (creativity * 0.7), 2),
            "top_p": round(0.4 + (creativity * 0.55), 2),
            "min_p": round(creativity * 0.1, 2),
            "top_k": int(20 + (creativity * 80)),
            "repeat_penalty": round(base_penalty + (creativity * 0.3), 2),
            "presence_penalty": round(creativity * 0.6, 2)
        }

        return {
            "score": score, "creativity": creativity,
            "level": level, "params": params,
            "details": f"C:{score} Cr:{creativity} (CTX:{final_ctx})"
        }

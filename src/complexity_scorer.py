import math
import ollama
import os
import re
from typing import Dict, Any, Optional

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

    # Verbs and nouns indicating a high-effort thinking/reasoning task (Predicted Complexity)
    TASK_INTENSITY_KEYWORDS = {
        "analyze", "analysis", "compare", "contrast", "explain", "why",
        "describe", "summarize", "refactor", "debug", "solve", "math",
        "calculate", "logic", "proof", "architecture", "impact", "relationship",
        "consequence", "difference", "history", "scientific", "detailed", "step-by-step",
        "implementation", "optimization", "comprehensive", "advanced", "complex"
    }

    # Technical/Formal domain markers (Predicts Determinism)
    DETERMINISTIC_DOMAIN_KEYWORDS = {
        "code", "coding", "program", "function", "class", "variable", "interface", 
        "api", "json", "csv", "table", "strict", "sql", "database", "python",
        "javascript", "c++", "rust", "equation", "formula", "data", "deep", "neural"
    }
    
    # Keywords suggesting creative/divergent thinking (Predicts Creativity)
    CREATIVE_INTENT_KEYWORDS = {
        "story", "poem", "creative", "imagine", "joke", "funny", "metaphor", 
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
        except Exception:
            pass
        return 8192 # Default safe fallback

    @staticmethod
    def _get_loaded_model_size_mb() -> int:
        """Estimates the size of the currently loaded model, cached for 60s."""
        import time
        now = time.time()
        if now < ComplexityScorer._model_size_cache["expires"]:
            return ComplexityScorer._model_size_cache["size"]

        try:
            client = ollama.Client()
            ps = client.ps()
            for m in ps.models:
                if m.model.split(":")[0] in config.MODEL_NAME or config.MODEL_NAME in m.model:
                    size_mb = m.size // (1024 * 1024)
                    ComplexityScorer._model_size_cache = {"size": size_mb, "expires": now + 60}
                    return size_mb
        except Exception:
            pass
        return 0

    @staticmethod
    def _calculate_ari(text: str) -> float:
        """Calculates ARI to gauge the linguistic sophistication of the request."""
        characters = len(re.sub(r'[^a-zA-Z0-9]', '', text))
        words = text.split()
        num_words = len(words)
        num_sentences = len(re.findall(r'[.!?]+', text)) or 1
        if num_words == 0: return 0.0
        ari = 4.71 * (characters / num_words) + 0.5 * (num_words / num_sentences) - 21.43
        return max(0.0, min(1.0, ari / 14.0))

    @staticmethod
    def _get_structural_score(text: str) -> float:
        """Detects structural markers in the prompt that demand high-fidelity responses."""
        score = 0.0
        questions = text.count('?')
        if questions > 1: score += 0.5 * min(questions, 2)
        if "```" in text: score += 0.7 
        if re.search(r'^\s*[-*•]\s+', text, re.MULTILINE): score += 0.4
        return min(1.0, score)

    @staticmethod
    def analyze(user_input: str) -> Dict[str, Any]:
        """
        Calculates predicted complexity and creativity scores for the response.
        """
        if not user_input.strip():
            return {"score": 0.0, "creativity": 0.0, "level": "MINIMAL", "params": {"num_ctx": 256, "num_predict": -1, "temperature": 0.1, "top_p": 0.4}}

        lower_input = user_input.lower()
        
        # --- Predicted Complexity (Model Effort) ---
        intensity_hits = sum(1 for kw in ComplexityScorer.TASK_INTENSITY_KEYWORDS if kw in lower_input)
        det_domain_hits = sum(1 for kw in ComplexityScorer.DETERMINISTIC_DOMAIN_KEYWORDS if kw in lower_input)
        intent_score = (intensity_hits * 0.4) + (det_domain_hits * 0.3)
        
        ari_score = ComplexityScorer._calculate_ari(user_input)
        struct_score = ComplexityScorer._get_structural_score(user_input)
        
        # Logarithmic length scaling: reward detail but don't let it explode
        word_count = len(user_input.split())
        len_score = min(1.0, math.log(word_count + 1, 80)) if word_count > 0 else 0.0

        total_complexity = (intent_score * 0.5 + struct_score * 0.25 + ari_score * 0.15 + len_score * 0.1)
        
        simple_hits = sum(1 for kw in ComplexityScorer.SIMPLE_KEYWORDS if kw in lower_input)
        if simple_hits > 0 and intensity_hits == 0 and det_domain_hits == 0 and word_count < 10:
            total_complexity -= 0.4

        total_complexity = round(max(0.0, min(1.0, total_complexity)), 2)

        # --- Predicted Creativity (Response Variability) ---
        creative_hits = sum(1 for kw in ComplexityScorer.CREATIVE_INTENT_KEYWORDS if kw in lower_input)
        creative_intensity = 0.0
        if creative_hits > 0:
            creative_intensity = 0.4 + (min(creative_hits - 1, 3) * 0.2)
            
        creativity_score = creative_intensity - (det_domain_hits * 0.3)
        creativity_score = max(0.0, min(1.0, creativity_score))

        # --- Parameter Mapping & Constraints ---
        # 1. Base Complexity assignment (num_ctx)
        if total_complexity <= 0.02:
            level = ComplexityScorer.LEVEL_MINIMAL
            requested_ctx = 512
            base_repeat_penalty = 1.05
        elif total_complexity < 0.15:
            level = ComplexityScorer.LEVEL_SIMPLE
            requested_ctx = 2048
            base_repeat_penalty = 1.1
        elif total_complexity < 0.45:
            level = ComplexityScorer.LEVEL_MODERATE
            requested_ctx = 3072
            base_repeat_penalty = 1.15
        else:
            level = ComplexityScorer.LEVEL_COMPLEX
            requested_ctx = 4096
            base_repeat_penalty = 1.2

        # 2. Hard Constraints
        model_max = ComplexityScorer._get_model_max_ctx()
        model_size_mb = ComplexityScorer._get_loaded_model_size_mb()
        _, vram_mb = get_system_resources()
        
        # --- ULTRA-CONSERVATIVE SAFETY FORMULA ---
        # 1. Start with Total VRAM (fallback to 2048 if detection fails)
        total_vram = vram_mb or 2048
        
        # 2. Subtract Model Weight Size
        available_headroom = max(0, total_vram - model_size_mb)
        
        # 3. Subtract a fixed system/GUI buffer (256MB) to protect OS/Tkinter
        safe_headroom = max(0, available_headroom - 256)
        
        # 4. Apply 70% safety cap (leaving 30% for CUDA graphs/fragmentation)
        capped_headroom = safe_headroom * 0.7
        
        # 5. Token Calculation (Assume 0.25MB per token for KV cache + overhead)
        # This allows ~4000 tokens per 1GB of available headroom.
        vram_tokens_limit = int(capped_headroom / 0.25)
        
        # Clamp num_ctx between a safe floor (512) and the dynamic limit
        final_ctx = max(512, min(requested_ctx, model_max, vram_tokens_limit))

        # 3. Sampling (Creativity based)
        temperature = 0.1 + (creativity_score * 0.7)
        top_p = 0.4 + (creativity_score * 0.55)
        min_p = creativity_score * 0.1
        top_k = int(20 + (creativity_score * 80))
        repeat_penalty = base_repeat_penalty + (creativity_score * 0.3)
        presence_penalty = creativity_score * 0.6

        params = {
            "num_ctx": final_ctx,
            "num_predict": -1,
            "temperature": round(temperature, 2),
            "top_p": round(top_p, 2),
            "min_p": round(min_p, 2),
            "top_k": top_k,
            "repeat_penalty": round(repeat_penalty, 2),
            "presence_penalty": round(presence_penalty, 2)
        }

        return {
            "score": total_complexity,
            "creativity": round(creativity_score, 2),
            "level": level,
            "params": params,
            "details": f"C:{total_complexity} Cr:{creativity_score} (Max:{model_max}, VRAM:{vram_tokens_limit}, Model:{model_size_mb}MB)"
        }

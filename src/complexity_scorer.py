"""
Complexity and Creativity analysis for user prompts.
Adjusts LLM parameters dynamically based on predicted effort.
"""
import math
import re
from typing import Dict, Any

from utils import debug_print

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
            level, base_penalty = ComplexityScorer.LEVEL_MINIMAL, 1.05
        elif score < 0.15:
            level, base_penalty = ComplexityScorer.LEVEL_SIMPLE, 1.1
        elif score < 0.45:
            level, base_penalty = ComplexityScorer.LEVEL_MODERATE, 1.15
        else:
            level, base_penalty = ComplexityScorer.LEVEL_COMPLEX, 1.2

        params = {
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
            "details": f"C:{score} Cr:{creativity}"
        }

    @staticmethod
    def is_creative(user_input: str) -> bool:
        """Determines if the prompt has a strong creative intent."""
        _, creativity, _ = ComplexityScorer._get_complexity_metrics(user_input)
        return creativity > 0.5

"""
Memory extraction logic for Lokality.
Uses LLM-driven delta management to maintain a long-term memory database.
"""
import json
import re

import ollama

import config
from utils import debug_print, error_print, get_ollama_client

# client removed from here

class MemoryManager:
    """Manages the extraction of permanent facts from user interactions."""

    @staticmethod
    def _is_mood_or_meta(fact_lower):
        """Checks if the fact describes a transient mood or meta-interaction."""
        # Reject interaction/meta verbs that describe the chat itself
        meta_verbs = {
            "requested", "inquired", "asked", "presented", "tasked",
            "queried", "answered", "responded", "told", "said", "interested in",
            "mentioned", "stated", "explained", "summarized", "discussed"
        }
        # Extensive blacklist of transient physical and emotional states (moods)
        mood_keywords = {
            "tired", "hungry", "thirsty", "sleepy", "exhausted", "sick", "ill",
            "cold", "hot", "sweaty", "energetic", "weak", "dizzy", "faint",
            "happy", "sad", "angry", "frustrated", "annoyed", "bored", "excited",
            "anxious", "nervous", "stressed", "worried", "scared", "afraid",
            "terrified", "lonely", "miserable", "guilty", "ashamed", "jealous",
            "envious", "bitter", "cheerful", "content", "relaxed", "calm",
            "peaceful", "proud", "hopeful", "enthusiastic", "eager", "amused",
            "delighted", "ecstatic", "satisfied", "confused", "puzzled",
            "surprised", "shocked", "overwhelmed", "focused", "distracted",
            "productive", "lazy", "unmotivated", "cranky", "grumpy", "moody"
        }

        words = set(re.findall(r'\b\w+\b', fact_lower))
        return bool(words.intersection(meta_verbs) or words.intersection(mood_keywords))

    @staticmethod
    def _is_transient_action(fact_lower):
        """Checks if the fact describes an action currently in progress."""
        # Reject facts describing current actions (e.g., "is walking", "are searching")
        # Pattern: auxiliary verb (am/is/are/was/were) + word ending in "ing"
        action_pattern = r'\b(am|is|are|was|were)\b\s+[a-z]+ing\b'
        return bool(re.search(action_pattern, fact_lower))

    @staticmethod
    def validate_fact_content(fact):
        """Validates content existence and filters out interaction/meta/mood facts."""
        if not fact or len(fact.strip()) < 3:
            return False

        fact_lower = fact.lower()
        # Filter out "wants to", "wants info", "interested in knowing", etc.
        if re.search(r'\bwants?\b.*\b(to|info|know|about)\b', fact_lower):
            return False
        if "interested in" in fact_lower and "knowing" in fact_lower:
            return False

        if MemoryManager._is_mood_or_meta(fact_lower):
            return False

        if MemoryManager._is_transient_action(fact_lower):
            return False

        return True

    @staticmethod
    def extract_facts(user_input, assistant_response, current_memory_text):
        """Delta-based memory update using structured operations."""
        system_instructions = (
            "You are a Memory Management Module. Extract enduring facts (relevant in 1+ month).\n\n"
            "RULES:\n"
            "1. ENTITY IDENTIFICATION: Identify the SUBJECT of the fact. "
            "Use 'User' ONLY for facts about the user themselves. "
            "For other entities (people, pets, places, objects), use their specific name "
            "or a clear descriptor (e.g., 'Whiskers', 'User's cat', 'Paris'). "
            "Use 'Assistant' for yourself (Lokality).\n"
            "2. SUBJECT-CENTRIC: The 'entity' field MUST be the specific subject "
            "the fact is about. Do not default to 'User' if the fact is about "
            "something or someone else.\n"
            "3. NO TRANSIENTS: Do not record moods, immediate plans, actions in progress, "
            "or conversational filler.\n"
            "4. NO META/SESSION INFO: Do not record what the user 'wants to know', "
            "'asked about', or 'is looking for' in this chat. "
            "Ignore search status and chat flow.\n"
            "5. NO INFERENCE: Record only explicitly stated facts.\n"
            "6. DEDUPLICATION: Use 'update' or 'remove' ONLY for clear factual corrections. "
            "These operations must be used VERY SPARINGLY. Prefer adding new distinct details.\n"
            "7. NO ID, NO UPDATE: If a fact is not in CURRENT MEMORY, you MUST use 'add' "
            "with 'id': null. NEVER use 'update' or 'remove' with 'id': null.\n"
            "8. SELECTIVITY & CAPACITY: Extract ONLY the most significant facts. "
            "FEWER IS BETTER. You may record 0 facts if nothing is enduring. "
            "MAX 3 'add' operations per turn.\n\n"
            "FORMAT: JSON object with 'operations' list.\n"
            "Each op: " 
            "{'op': 'add'|'update'|'remove', 'entity': str, 'fact': str, 'id': int|null}.\n"
            "CRITICAL: Use 'id': null for all 'add' operations. "
            "ID is required and MUST be an integer for all update/remove operations."
        )

        user_prompt = (
            f"### CURRENT MEMORY:\n{current_memory_text}\n\n"
            f"### CONTEXT:\n{assistant_response}\n\n"
            f"### NEW INPUT:\n{user_input}\n\n"
            "Extract permanent facts. Return JSON."
        )

        try:
            res = get_ollama_client().chat(
                model=config.MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_prompt}
                ],
                format="json",
                options={
                    "temperature": 0.0,
                    "num_predict": 512
                }
            )
            response_text = res['message']['content'].strip()
            debug_print(f"[*] Memory: LLM Raw Response: {response_text}")

            all_ops = MemoryManager._parse_llm_response(response_text)

            if all_ops:
                return MemoryManager._validate_operations(all_ops)

        except (ollama.ResponseError, RuntimeError) as exc:
            error_print(f"Memory Update System Error: {exc}")

        return []

    @staticmethod
    def _parse_llm_response(response_text):
        """Parses the LLM response text into a list of operations."""
        ops = []
        try:
            data = json.loads(response_text)
            if isinstance(data, list):
                ops = data
            else:
                ops = data.get("operations", [])
        except (json.JSONDecodeError, AttributeError):
            # Fallback to regex if JSON is somehow wrapped in text
            match = re.search(r'(\{[\s\S]*\}|[[\][\s\S]*])', response_text)
            if match:
                try:
                    data = json.loads(match.group(1))
                    if isinstance(data, list):
                        ops = data
                    else:
                        ops = data.get("operations", [])
                except (json.JSONDecodeError, AttributeError):
                    pass
        return ops

    @staticmethod
    def _validate_operations(all_ops):
        """Validates the list of operations extracted from the LLM."""
        valid_ops = []
        add_count = 0
        for op in all_ops:
            if not isinstance(op, dict) or 'op' not in op:
                continue

            # Validate ID format (must be integer for update/remove)
            if op['op'] in ['update', 'remove']:
                try:
                    op['id'] = int(op.get('id'))
                except (ValueError, TypeError):
                    debug_print(
                        f"[*] Memory: Filtering op with malformed ID: {op.get('id')}"
                    )
                    continue

            if op['op'] in ['add', 'update']:
                fact = op.get('fact', '')
                if not MemoryManager.validate_fact_content(fact):
                    continue

            if op['op'] == 'add':
                if add_count >= 3:
                    debug_print("[*] Memory: Capacity reached. Skipping additional 'add' op.")
                    continue
                add_count += 1

            valid_ops.append(op)
        return valid_ops

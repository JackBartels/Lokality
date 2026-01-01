import ast
import json
import re

import ollama

from complexity_scorer import ComplexityScorer
from config import MODEL_NAME, MEMORY_EXTRACTION_MAX_TOKENS, CONTEXT_WINDOW_SIZE
from logger import logger
from utils import debug_print, error_print

client = ollama.Client()

class MemoryManager:
    @staticmethod
    def validate_fact_content(fact):
        """Validates content existence and filters out interaction/meta/mood facts."""
        if not fact or len(fact.strip()) < 3:
            return False
            
        fact_lower = fact.lower()
        if "wants to" in fact_lower:
            return False

        # Reject interaction/meta verbs that describe the chat itself
        meta_verbs = {
            "requested", "inquired", "asked", "presented", "tasked", 
            "queried", "answered", "responded", "told", "said", 
            "mentioned", "stated", "explained", "summarized"
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
        if words.intersection(meta_verbs) or words.intersection(mood_keywords):
            return False

        # Reject facts describing current actions (e.g., "is walking", "are searching")
        # Pattern: auxiliary verb (am/is/are/was/were) + word ending in "ing"
        action_pattern = r'\b(am|is|are|was|were)\b\s+\w+ing\b'
        if re.search(action_pattern, fact_lower):
            return False
            
        return True

    @staticmethod
    def extract_facts(user_input, assistant_response, current_memory_text):
        """Delta-based memory update using structured operations."""
        system_instructions = (
            "You are a high-precision Memory Management Module.\n\n"
            "ENTITY STANDARDIZATION (SUBJECT-ONLY):\n"
            "- The 'entity' field MUST be the SUBJECT of the fact.\n"
            "- If the User refers to themselves (I, me, my, mine), use 'User'.\n"
            "- If the User refers to you (you, your, yours), use 'Assistant'.\n"
            "- For all other entities, extract the specific SUBJECT (e.g., 'Elon Musk', 'Tokyo').\n"
            "- NEVER use the object as the Entity (WRONG: {'entity': 'Pizza', 'fact': 'User likes it'}).\n\n"
            "CORE RULES:\n"
            "1. GOLDEN RULE: Record ONLY enduring facts relevant in ONE MONTH OR MORE. "
            "STRICTLY FORBIDDEN: Present-tense actions, current events, or conversational context.\n"
            "2. ANTI-LOGISTICS RULE: Never record short-term logistics or immediate personal intent. DO NOT RECORD:\n"
            "   - Immediate tasks or intents (e.g., 'User needs to write an email', 'User is going to bed').\n"
            "   - Short-term plans (e.g., 'User is making dinner tonight').\n"
            "   - Transient physical or emotional states (e.g., 'User is tired', 'User is hungry', 'User is happy', 'User has X in the fridge').\n"
            "3. ANTI-META RULE: Never record the conversation or its flow. DO NOT RECORD:\n"
            "   - User requests or flow instructions (e.g., 'User requested a table', 'User wants to proceed to next question').\n"
            "   - Assistant status or chat summaries.\n"
            "4. INQUIRY VS. IDENTITY: Do not record temporary curiosity. Asking a question does not make 'Interest in [topic]' a permanent attribute.\n"
            "5. SEARCH HYGIENE: Ignore all mentions of 'search results' or 'SEARCH_CONTEXT'. Extract only underlying real-world facts.\n"
            "6. THE NEGATIVE TEST: Assume every fact is transient by default. Only record if it is a permanent ATTRIBUTE (stable) rather than a STATE (temporary).\n"
            "7. OPERATION RULE: Never record assistant operations (searching, scraping, memory updates).\n"
            "8. NO INFERENCE: Record explicitly stated facts, not assumptions based on behavior.\n\n"
            "STRICT DEDUPLICATION PROTOCOL:\n"
            "1. Check CURRENT MEMORY for the entity. Use 'update' or 'remove' ONLY for explicit corrections.\n"
            "2. Accumulate distinct details rather than overwriting.\n\n"
            "FORMATTING:\n"
            "Return a JSON object with a key 'operations' containing a list of operation objects.\n"
            "Each object MUST have: 'op' (add/update/remove), 'entity' (the SUBJECT), 'fact', and 'id'.\n"
            "CRITICAL: The 'id' MUST be a strict INTEGER corresponding to the [ID: x] provided in CURRENT MEMORY (only for update/remove). Use null for 'add'."
        )
        
        user_prompt = (
            f"### CURRENT MEMORY:\n{current_memory_text}\n\n"
            f"### CONTEXT (Assistant's previous response):\n{assistant_response}\n\n"
            f"### NEW USER INPUT:\n{user_input}\n\n"
            "Task: Extract permanent facts from the User's input. "
            "Return a JSON object with the requested operations list."
        )

        try:
            # VRAM Safety check for context size
            safe_ctx = ComplexityScorer.get_safe_context_size(CONTEXT_WINDOW_SIZE)
            
            res = client.chat(
                model=MODEL_NAME, 
                messages=[
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_prompt}
                ],
                format="json",
                options={
                    "num_predict": MEMORY_EXTRACTION_MAX_TOKENS,
                    "num_ctx": safe_ctx,
                    "temperature": 0.0
                }
            )
            response_text = res['message']['content'].strip()
            debug_print(f"[*] Memory: LLM Raw Response: {response_text}")
            
            try:
                data = json.loads(response_text)
                all_ops = data.get("operations", [])
            except json.JSONDecodeError:
                # Fallback to regex if JSON is somehow wrapped in text
                match = re.search(r'(\{[\s\S]*\})', response_text)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        all_ops = data.get("operations", [])
                    except:
                        all_ops = []
                else:
                    all_ops = []
            
            if all_ops:
                valid_ops = []
                for op in all_ops:
                    if not isinstance(op, dict) or 'op' not in op:
                        continue
                        
                    # Validate ID format (must be integer for update/remove)
                    if op['op'] in ['update', 'remove']:
                        try:
                            op['id'] = int(op.get('id'))
                        except (ValueError, TypeError):
                            debug_print(f"[*] Memory: Filtering op with malformed ID: {op.get('id')}")
                            continue

                    if op['op'] in ['add', 'update']:
                        fact = op.get('fact', '')
                        if not MemoryManager.validate_fact_content(fact):
                            continue
                    
                    valid_ops.append(op)
                return valid_ops
                
        except Exception as e:
            error_print(f"Memory Update System Error: {e}")
            
        return []

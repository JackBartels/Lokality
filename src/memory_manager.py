import ast
import json
import re

import ollama

from config import MODEL_NAME, MEMORY_EXTRACTION_MAX_TOKENS, CONTEXT_WINDOW_SIZE
from logger import logger
from utils import debug_print, error_print

client = ollama.Client()

class MemoryManager:
    @staticmethod
    def validate_fact_content(fact):
        """Returns True if the fact is suitable for long-term storage."""
        if not fact or len(fact.strip()) < 3:
            return False
            
        # Hard Filter: Block transient info
        forbidden = {
            "temperature", "humidity", "weather", "forecast", "currently is", 
            "at the moment", "today is", "tonight", "tomorrow", "yesterday", 
            "language model", "conversation turn", "current time", "the time is",
            "wants to know", "wants", "is currently", "is doing", "currently wants",
            "just did", "recently did", "asked me", "requested", "cleared", "deleted",
            "asks about", "asked about", "searching for", "searched for"
        }
        fact_lower = fact.lower()
        if any(key in fact_lower for key in forbidden):
            return False
            
        return True

    @staticmethod
    def extract_facts(user_input, assistant_response, current_memory_text):
        """Delta-based memory update using structured operations."""
        system_instructions = (
            "You are a high-precision Memory Management Module.\n\n"
            "ENTITY STANDARDIZATION:\n"
            "- Extract the specific subject of the fact as the Entity (e.g., 'Elon Musk', 'Tallinn', 'NVIDIA', 'The Assistant').\n"
            "- ONLY use 'The User' for facts about the user's personal identity, preferences, or history.\n"
            "- If a fact is about a global event, organization, or public figure, use that specific name as the Entity.\n\n"
            "CRITICAL CATEGORIES:\n"
            "- Identity (Names, long-term roles, occupations, residence, hometown).\n"
            "- Permanent Interests (Broad goals, ongoing learning).\n"
            "- Preferences & Tools (Static likes/dislikes). ONLY record if the user EXPLICITLY states a preference (e.g., 'I like X' or 'I love X').\n"
            "- Entity Attributes (Permanent facts about people, places, or the Assistant itself).\n\n"
            "DO NOT RECORD:\n"
            "### GOLDEN RULE: If a piece of information will not still be relevant or true in ONE MONTH, do NOT record it. ###\n"
            "- INFERRED PREFERENCES: NEVER infer that a user likes or prefers something just because they asked about it or are currently using it (e.g., if a user asks for a pizza recipe, do NOT record 'Likes pizza' unless they explicitly say so).\n"
            "- PRESENT WANTS & IMMEDIATE ACTIONS: NEVER record what the user currently wants to do, see, or know in the context of the chat (e.g., 'Wants to see the code', 'Wants to clear the screen', 'Is currently looking at a file').\n"
            "- CURRENT & RECENT ACTIONS: NEVER record what the user or assistant IS currently doing or JUST did within the conversation (e.g., 'User is asking a question', 'Assistant is explaining logic', 'User just cleared the memory').\n"
            "- TRANSIENT REQUESTS: Do not record temporary requests like 'Show me a joke' or 'Tell me a story'.\n"
            "- QUESTIONS & TOPICS: NEVER record that a user 'Asks about [topic]' or 'Is curious about [X]'. Questions are not permanent facts about the user's identity.\n"
            "- TRANSIENT INFO: Obvious AI/Assistant roles, transient moods, current weather/time, temporary events, or conversational filler.\n\n"
            "OKAY TO RECORD:\n"
            "- LONG-TERM ASPIRATIONS: Only record goals, future plans, or enduring desires that define the user's personality or life path (e.g., 'Aims to learn Rust', 'Wants to move to Italy in 2026').\n\n"
            "STRICT DEDUPLICATION PROTOCOL:\n"
            "1. ENTITY SCAN: Check CURRENT MEMORY for the specific entity.\n"
            "2. MULTIPLE ENTRIES ALLOWED: Each entity can have unlimited distinct, non-overlapping facts. Do NOT merge unrelated facts. Preserving multiple specific details is better than overwriting them with a single general statement.\n"
            "3. VERY RARE OPERATIONS: 'update' and 'remove' are extremely rare. ONLY use them if the User explicitly negates a previous fact (e.g., 'I don't play guitar anymore' or 'I moved from X to Y').\n"
            "4. PREFER REDUNDANCY: It is always better to have two distinct facts (e.g., 'Likes Pizza' and 'Likes Burgers') than to overwrite one. Accumulate information instead of replacing it.\n"
            "5. SEMANTIC MATCH: If a fact is conceptually identical to one already known for that entity, return [].\n"
            "6. GOLDEN RULES FOR OPERATIONS:\n"
            "- ALWAYS USE 'add' for new preferences, interests, tools, or attributes, even if similar to existing ones.\n"
            "- ONLY USE 'update' for direct, explicit corrections of historical facts (e.g., change of city, change of job title).\n"
            "- NEVER USE 'update' to refine phrasing. If the user says something slightly differently, either 'add' it as a new distinct detail or ignore it.\n\n"
            "SOURCE RESTRICTION:\n"
            "- ONLY record facts that were explicitly stated, confirmed, or assigned by the User in their input.\n"
            "- You may record facts about 'The Assistant' (e.g., a name the user gives you) or other entities, but the information must originate from the User.\n\n"
            "EFFICIENCY & SCOPE:\n"
            "- ATOMIC EVALUATION: Evaluate each potential piece of information individually. Treat every possible fact as a standalone candidate for memory. Just because one fact in a sentence is recordable does not mean other facts in the same sentence are.\n"
            "- Only suggest an operation if there is a MEANINGFUL change to long-term memory. Do not update for trivial variations in phrasing.\n"
            "- You can perform MULTIPLE operations (add, update, remove) in a single response by including them all in the list.\n"
            "- If nothing meaningful has changed, return an empty list [].\n\n"
            "FORMATTING:\n"
            "- Output ONLY the JSON block. Do not include 'Here is the JSON' or any conversational text.\n"
            "- Use ONLY 'add', 'remove', or 'update' as operations.\n"
            "- Example Add: [{'op': 'add', 'entity': 'Elon Musk', 'fact': 'CEO of SpaceX'}]\n"
            "- Example No Changes: []"
        )
        
        user_prompt = (
            f"### CURRENT MEMORY:\n{current_memory_text}\n\n"
            f"### CONTEXT (Assistant's previous response):\n{assistant_response}\n\n"
            f"### NEW USER INPUT (Extract ONLY from here):\n{user_input}\n\n"
            "Task: Extract permanent facts STRICTLY from the User's input. Use the Assistant's response ONLY for context to understand the User. "
            "ONLY use 'update' if the user is explicitly correcting an existing fact shown in CURRENT MEMORY. Otherwise, use 'add' for all new information. "
            "Return [] if no NEW permanent info was shared."
        )

        try:
            res = client.chat(
                model=MODEL_NAME, 
                messages=[
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_prompt}
                ],
                options={
                    "num_predict": MEMORY_EXTRACTION_MAX_TOKENS,
                    "num_ctx": CONTEXT_WINDOW_SIZE
                }
            )
            response_text = res['message']['content'].strip()
            
            debug_print(f"[*] Memory: LLM Raw Response: {response_text}")
            
            # Robust extraction of all dict/list blocks
            all_ops = []
            # Match both lists [...] and individual dicts {...}
            for match in re.finditer(r'(\[[\s\S]*?\]|\{[\s\S]*?\})', response_text):
                content = match.group()
                try:
                    ops = ast.literal_eval(content)
                except Exception:
                    try:
                        ops = json.loads(content)
                    except Exception:
                        continue
                
                if isinstance(ops, list):
                    all_ops.extend(ops)
                elif isinstance(ops, dict):
                    all_ops.append(ops)
            
            if all_ops:
                # Basic validation: ensure we only process dicts with an 'op' key and valid content
                valid_ops = []
                for op in all_ops:
                    if not isinstance(op, dict) or 'op' not in op:
                        continue
                        
                    # Validate content for add/update
                    if op['op'] in ['add', 'update']:
                        fact = op.get('fact', '')
                        if not MemoryManager.validate_fact_content(fact):
                            debug_print(f"[*] Memory: Filtering invalid fact content: {fact[:40]}...")
                            continue
                    
                    valid_ops.append(op)
                
                if valid_ops:
                    return valid_ops
                
            debug_print(f"[*] Memory: No valid operations found in: {response_text}")
                
        except Exception as e:
            error_print(f"Memory Update System Error: {e}")
            
        return []

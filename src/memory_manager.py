import json
import re
import ast
import os
from config import MODEL_NAME, DEBUG
import ollama

client = ollama.Client()

class MemoryManager:
    @staticmethod
    def extract_facts(user_input, assistant_response, current_memory_text):
        """Delta-based memory update using structured operations."""
        system_instructions = (
            "You are a high-precision Memory Management Module.\n\n"
            "ENTITY STANDARDIZATION:\n"
            "- Entities can be 'The User', 'The Assistant', or any specific person, place, or thing mentioned by the user that has long-term relevance.\n\n"
            "CRITICAL CATEGORIES:\n"
            "- Identity (Names, long-term roles, occupations, residence, hometown).\n"
            "- Permanent Interests (Broad goals, ongoing learning).\n"
            "- Preferences & Tools (Static likes/dislikes).\n"
            "- Entity Attributes (Permanent facts about people, places, or the Assistant itself).\n\n"
            "DO NOT RECORD:\n"
            "### GOLDEN RULE: If a piece of information will not still be relevant or true in ONE MONTH, do NOT record it. ###\n"
            "- Obvious AI/Assistant roles, transient moods, current weather/time, temporary events, or conversational filler.\n\n"
            "STRICT DEDUPLICATION PROTOCOL:\n"
            "1. ENTITY SCAN: Check CURRENT MEMORY for the specific entity.\n"
            "2. MULTIPLE ENTRIES ALLOWED: Each entity can have unlimited distinct, non-overlapping facts. Do NOT merge unrelated facts. Preserving multiple specific details is better than overwriting them with a single general statement.\n"
            "3. HIGH RESISTANCE TO CHANGE: Be extremely resistant to modifying or removing existing memories. Only use 'update' or 'remove' if the User EXPLICITLY and DIRECTLY confirms that the existing memory is now incorrect or outdated. If there is any doubt, keep the existing memory and add the new info as a separate entry if it's distinct. DO NOT update a fact just because the wording is slightly different.\n"
            "4. SEMANTIC MATCH: If a fact is conceptually identical to one already known for that entity, return [].\n"
            "5. PRESERVATION: Never overwrite valid long-term memories arbitrarily.\n"
            "- IDENTITY FACTS: Be careful with names and nicknames. Only update them if the user indicates a change or correction.\n"
            "- MINIMAL UPDATES: Prefer adding a new fact over updating an old one unless it's a direct correction. For example, if you know the user likes Pizza and they say they like Burgers, ADD 'Likes Burgers' instead of replacing 'Likes Pizza'.\n\n"
            "SOURCE RESTRICTION:\n"
            "- ONLY record facts that were explicitly stated, confirmed, or assigned by the User in their input.\n"
            "- You may record facts about 'The Assistant' (e.g., a name the user gives you) or other entities, but the information must originate from the User.\n\n"
            "EFFICIENCY & SCOPE:\n"
            "- Only suggest an operation if there is a MEANINGFUL change to long-term memory. Do not update for trivial variations in phrasing.\n"
            "- You can perform MULTIPLE operations (add, update, remove) in a single response by including them all in the list.\n"
            "- If nothing meaningful has changed, return an empty list [].\n\n"
            "FORMATTING:\n"
            "- Output exactly ONE JSON list.\n"
            "- Use ONLY 'add', 'remove', or 'update' as operations. Do NOT use 'create'.\n"
            "- METADATA WARNING: Never include '(ID: #)' inside the 'fact' string. The ID belongs only in the 'id' field for updates.\n"
            "- Example Update: [{'op': 'update', 'id': 46, 'entity': 'The User', 'fact': 'Moved from Paraguay to Minnesota'}]"
        )
        
        user_prompt = (
            f"### CURRENT MEMORY:\n{current_memory_text}\n\n"
            f"### CONTEXT (Assistant's previous response):\n{assistant_response}\n\n"
            f"### NEW USER INPUT (Extract ONLY from here):\n{user_input}\n\n"
            "Task: Extract permanent facts strictly from the User's input. Use the Assistant's response only for context to understand the User. Use existing IDs for updates. Return [] if no NEW permanent info was shared by the user."
        )

        try:
            res = client.chat(model=MODEL_NAME, messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": user_prompt}
            ])
            response_text = res['message']['content'].strip()
            
            if os.environ.get("DEBUG") == "1":
                print(f"\033[90m[*] Memory: LLM Raw Response: {response_text}\033[0m")
            
            # Robust extraction of all list blocks [...]
            # We use non-greedy matching to find separate lists if the LLM outputs more than one.
            all_ops = []
            for match in re.finditer(r'\[[\s\S]*?\]', response_text):
                content = match.group()
                try:
                    # Try Python literal evaluation first (handles single quotes in strings correctly)
                    ops = ast.literal_eval(content)
                except Exception:
                    try:
                        # Fallback to JSON
                        ops = json.loads(content)
                    except Exception:
                        continue
                
                if isinstance(ops, list):
                    all_ops.extend(ops)
                elif isinstance(ops, dict):
                    all_ops.append(ops)
            
            if all_ops:
                # Basic validation: ensure we only process dicts with an 'op' key
                valid_ops = [op for op in all_ops if isinstance(op, dict) and 'op' in op]
                if valid_ops:
                    return valid_ops
                
            if os.environ.get("DEBUG") == "1":
                print(f"\033[90m[*] Memory: No valid operations found in: {response_text}\033[0m")
                
        except Exception as e:
            print(f"\033[91m[*] Memory Update System Error: {e}\033[0m")
            
        return []

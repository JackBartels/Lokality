import ollama
from ddgs import DDGS
import sys
import warnings
import os
from datetime import datetime
import threading
import json
import re
import ast
from memory import MemoryStore

# Configuration
MODEL_NAME = os.environ.get("LOKALITY_MODEL", "gemma3:4b-it-qat")
VERSION = "0.0.1"

client = ollama.Client()

class LocalChatAssistant:
    def __init__(self):
        self.messages = []
        self.current_date = datetime.now().strftime("%A, %B %d, %Y")
        self.memory = MemoryStore()
        self._update_system_prompt()

    def _update_system_prompt(self, query=None):
        relevant_facts = "\n".join(self.memory.get_relevant_facts(query))
        self.system_prompt = (
            f"You are Lokality, a helpful AI assistant with real-time internet access. "
            f"Today's date is {self.current_date}.\n\n"
            f"### RELEVANT LONG-TERM MEMORY (Your Source of Truth):\n{relevant_facts}\n\n"
            "STRICT GUIDELINES ON MEMORY:\n"
            "1. USE PROVIDED FACTS: The memory section above contains the ONLY confirmed facts about the User and yourself. Use them to personalize your response.\n"
            "2. NO HALLUCINATIONS: Never make up names, locations, or preferences for the User. If a detail is not in the memory section, do not assume it exists.\n"
            "3. ASK DON'T GUESS: If the user asks something about themselves that isn't in memory, politely state that you don't know yet and ask them for the information.\n"
            "4. SEARCH FOR TRANSIENT INFO: Use search results for news and weather, but trust memory for identity.\n\n"
            "Be conversational, precise, and professional."
        )

    def _update_memory(self, user_input, assistant_response):
        """Delta-based memory update using structured operations."""
        all_facts = "\n".join(self.memory.get_all_facts())
        
        system_instructions = (
            "You are a memory management module. Your job is to Extract and Record permanent facts (names, locations, jobs, pets, preferences, identity) from the conversation. "
            "If the User shares something personal, you MUST record it. "
            "Output ONLY a JSON list of objects. Example: [{'op': 'add', 'entity': 'The User', 'fact': 'Lives in New York'}]"
        )
        
        user_prompt = (
            f"### CURRENT MEMORY:\n{all_facts}\n\n"
            f"### NEW CONVERSATION TURN:\nUser: {user_input}\nAssistant: {assistant_response}\n\n"
            "Task: Did the user share something new about themselves? Did you receive a name or persona? "
            "Suggest ADD, REMOVE, or UPDATE operations in JSON format. Use 'The User' or 'The Assistant' or a specific name as the entity. "
            "If absolutely nothing permanent was learned, return []."
        )

        try:
            res = client.chat(model=MODEL_NAME, messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": user_prompt}
            ])
            response_text = res['message']['content'].strip()
            
            # Robust JSON extraction
            match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if match:
                content = match.group()
                try:
                    ops = json.loads(content)
                except json.JSONDecodeError:
                    try:
                        ops = ast.literal_eval(content)
                    except (ValueError, SyntaxError) as e:
                        print(f"\033[91m[*] Memory Parse Failed: {e} | Content: {content}\033[0m")
                        return

                if not ops:
                    if os.environ.get("DEBUG"):
                        print(f"\033[90m[*] Memory: No changes detected.\033[0m")
                    return
                    
                updated = False
                for op in ops:
                    if not isinstance(op, dict): continue
                    
                    action = op.get('op')
                    entity = op.get('entity', 'The User')
                    fact = op.get('fact')
                    fact_id = op.get('id')

                    if action == 'add' and fact:
                        print(f"\033[90m[*] Memory: ADD {entity}: {fact}\033[0m")
                        self.memory.add_fact(entity, fact)
                        updated = True
                    elif action == 'remove' and fact_id is not None:
                        print(f"\033[90m[*] Memory: REMOVE ID {fact_id}\033[0m")
                        self.memory.remove_fact(fact_id)
                        updated = True
                    elif action == 'update' and fact_id is not None and fact:
                        print(f"\033[90m[*] Memory: UPDATE ID {fact_id}\033[0m")
                        self.memory.update_fact(fact_id, entity, fact)
                        updated = True
                
                if updated:
                    self._update_system_prompt(user_input)
            
        except Exception as e:
            print(f"\033[91m[*] Memory Update System Error: {e}\033[0m")

    def web_search(self, query):
        """Performs a DuckDuckGo search and returns the top results."""
        print(f"\033[90m[*] Searching for: {query}\033[0m")
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
                if not results:
                    return "No recent web results found."
                
                formatted = []
                for i, r in enumerate(results, 1):
                    formatted.append(f"Source: {r['href']}\nSnippet: {r['body']}")
                return "\n\n".join(formatted)
        except Exception as e:
            return f"Error during search: {e}"

    def decide_and_search(self, user_input):
        """Uses a slimmed down context for the decision to save tokens."""
        recent_context = "\n".join([f"{m['role']}: {m['content'][:100]}..." for m in self.messages[-3:]])
        
        decision_prompt = (
            f"Current Date: {self.current_date}\n"
            f"Recent Conversation:\n{recent_context}\n"
            f"User: {user_input}\n\n"
            "Does answering this require current news, real-time data (stocks, weather), or specific facts not in your training? "
            "Answer ONLY 'YES' or 'NO'."
        )
        
        try:
            res = client.generate(model=MODEL_NAME, prompt=decision_prompt)
            if "YES" in res['response'].upper():
                query_prompt = f"Based on the conversation, what is the best search query for: '{user_input}'? Return ONLY the query."
                q_res = client.generate(model=MODEL_NAME, prompt=query_prompt)
                query = q_res['response'].strip().strip('"')
                return self.web_search(query)
        except Exception:
            pass
        return None

    def clear_long_term_memory(self):
        """Resets the internal long-term memory."""
        self.memory.clear()
        self._update_system_prompt()
        print("\033[90mLong-term memory cleared.\033[0m")

    def get_model_info(self):
        """Gathers statistics about the model and system."""
        stats = {
            "model": MODEL_NAME,
            "context_pct": 0,
            "memory_entries": self.memory.get_fact_count(),
            "ram_mb": 0,
            "vram_mb": 0
        }
        
        try:
            # Get VRAM/RAM info
            ps = client.ps()
            for m in ps.models:
                if m.model.split(":")[0] in MODEL_NAME or MODEL_NAME in m.model:
                    # m.size is total, size_vram is on GPU
                    # These are in bytes
                    vram_bytes = getattr(m, 'size_vram', 0)
                    total_bytes = getattr(m, 'size', 0)
                    stats["vram_mb"] = vram_bytes // (1024 * 1024)
                    stats["ram_mb"] = max(0, (total_bytes - vram_bytes) // (1024 * 1024))
                    break
            
            # Context estimation
            show = client.show(MODEL_NAME)
            show_dict = show.model_dump()
            # Find context length in modelinfo
            max_ctx = 8192 # Default fallback
            model_info = show_dict.get('modelinfo', {})
            for key, val in model_info.items():
                if 'context_length' in key:
                    max_ctx = val
                    break
            
            # Rough token estimation (chars / 4 is a common heuristic, but let's be more conservative)
            total_chars = len(self.system_prompt)
            for msg in self.messages:
                total_chars += len(msg['content'])
            
            estimated_tokens = total_chars // 3 # Heuristic
            stats["context_pct"] = min(100, (estimated_tokens / max_ctx) * 100)
            
        except Exception as e:
            print(f"Error gathering info: {e}")
            
        return stats
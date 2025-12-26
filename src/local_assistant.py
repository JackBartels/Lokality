import ollama
from datetime import datetime
import threading
import os
import re

import config
from config import MODEL_NAME, VERSION
from memory import MemoryStore
from memory_manager import MemoryManager
from search_engine import SearchEngine
from stats_collector import StatsCollector
from utils import debug_print

client = ollama.Client()

class LocalChatAssistant:
    def __init__(self):
        self.messages = []
        self.memory = MemoryStore()
        self.stop_requested = False
        self._update_system_prompt()

    def _update_system_prompt(self, query=None):
        facts = self.memory.get_relevant_facts(query)
        relevant_facts = "\n".join([f"- {f['entity']}: {f['fact']}" for f in facts])
        now = datetime.now()
        current_date = now.strftime("%A, %B %d, %Y")
        current_time = now.strftime("%I:%M %p")
        
        self.system_prompt = (
            f"You are Lokality, a helpful AI assistant with real-time internet access. "
            f"Today's date is {current_date} and the current time is {current_time}.\n\n"
            f"### RELEVANT LONG-TERM MEMORY (Your Source of Truth):\n{relevant_facts}\n\n"
            "STRICT GUIDELINES ON MEMORY:\n"
            "1. USE PROVIDED FACTS: The memory section above contains the ONLY confirmed facts about the User and yourself (Lokality). Use them to personalize your response.\n"
            "2. NAMES & NICKNAMES: The User may give you a specific name or nickname, or share their own. Always check the memory section for these identifiers.\n"
            "3. NO HALLUCINATIONS: Never make up names, locations, or preferences for the User. If a detail is not in the memory section, do not assume it exists.\n"
            "4. ASK DON'T GUESS: If the user asks something about themselves that isn't in memory, politely state that you don't know yet and ask them for the information.\n"
            "5. SEARCH FOR TRANSIENT INFO: Use search results for news and weather, but trust memory for identity.\n"
            "6. LOCAL TIME: You have access to the current local time in the header above. Use it to answer questions about the current time or date directly without searching.\n"
            "7. RESPONSE GUIDELINE: Aim for responses that are around one paragraph in length. You may be shorter for simple queries or longer when the complexity of the request warrants a more detailed explanation.\n\n"
            "Be conversational, precise, and professional."
        )

    def update_memory_async(self, user_input, assistant_response):
        """Dispatches memory update to a background thread."""
        threading.Thread(
            target=self._perform_memory_update, 
            args=(user_input, assistant_response),
            daemon=True
        ).start()

    def _perform_memory_update(self, user_input, assistant_response):
        debug_print(f"[*] Memory: _perform_memory_update called with input: '{user_input[:50]}...'")
            
        # OPTIMIZATION: Skip extraction for trivial/short inputs
        filler_words = {"thanks", "thank", "ok", "okay", "cool", "nice", "hello", "hi", "bye", "yes", "no", "yep", "nope"}
        clean_input = re.sub(r'[^a-zA-Z\s]', '', user_input).lower().strip()
        
        if len(clean_input.split()) < 3 and (not clean_input or clean_input in filler_words):
            debug_print("[*] Memory: Skipping trivial turn.")
            return

        debug_print("[*] Memory: Starting update check...")
        
        # Get structured facts for deduplication
        all_facts_raw = self.memory.get_relevant_facts(user_input)
        all_facts_text = "\n".join([f"[ID: {f['id']}] {f['entity']}: {f['fact']}" for f in all_facts_raw])
        
        ops = MemoryManager.extract_facts(user_input, assistant_response, all_facts_text)
        
        if not ops:
            debug_print("[*] Memory: No meaningful changes detected.")
            return
            
        debug_print(f"[*] Memory: LLM suggested {len(ops)} operations.")
        updated = False
        for op in ops:
            if not isinstance(op, dict): continue
            
            action, entity, fact, fact_id = op.get('op'), op.get('entity', 'The User'), op.get('fact', '').strip(), op.get('id')
            
            # HARD FILTER: Block transient info
            forbidden = {"temperature", "humidity", "weather", "forecast", "currently is", "at the moment", "today is", "tonight", "tomorrow", "yesterday", "language model", "conversation turn"}
            if any(key in fact.lower() for key in forbidden):
                debug_print(f"[*] Memory: BLOCKED Transient/Meta Fact -> {fact[:40]}...")
                continue

            # Robustness: Strip hallucinated (ID: #) suffixes
            fact = re.sub(r'\s*\(ID:\s*\d+\)$', '', fact).strip()
            
            # Verify existence for update/remove
            exists = False
            if fact_id is not None:
                # We can use memory.is_name_fact or similar, but let's just check if it exists
                # For simplicity, we'll assume it doesn't exist if it's not in our recently fetched all_facts_raw
                exists = any(f['id'] == fact_id for f in all_facts_raw)

            debug_print(f"[*] Memory: Attempting {action} | {entity}: {fact[:30]}...")

            if action == 'add' and fact:
                clean_fact = re.sub(r'[^a-zA-Z0-9]', '', fact).lower()
                is_duplicate = any(entity.lower() == f['entity'].lower() and clean_fact == re.sub(r'[^a-zA-Z0-9]', '', f['fact']).lower() for f in all_facts_raw)
                
                if not is_duplicate:
                    debug_print(f"[*] Memory: COMMIT ADD -> {entity}: {fact}")
                    self.memory.add_fact(entity, fact)
                    updated = True
                else:
                    debug_print(f"[*] Memory: BLOCKED Duplicate for {entity} -> {fact}")
            
            elif action == 'remove' and fact_id is not None and exists:
                debug_print(f"[*] Memory: COMMIT REMOVE -> ID {fact_id}")
                self.memory.remove_fact(fact_id)
                updated = True
            elif action == 'update' and fact_id is not None and exists and fact:
                debug_print(f"[*] Memory: COMMIT UPDATE -> ID {fact_id}: {fact}")
                self.memory.update_fact(fact_id, entity, fact)
                updated = True
            elif action in ['update', 'remove'] and not exists:
                debug_print(f"[*] Memory: BLOCKED {action} -> ID {fact_id} not found in recent context.")
        
        if updated:
            debug_print("[*] Memory: Database updated, refreshing system prompt.")
            self._update_system_prompt(user_input)
        else:
            debug_print("[*] Memory: No changes were committed to database.")
        
        debug_print("[*] Memory: Update check finished.")

    def decide_and_search(self, user_input):
        """Uses a single high-speed call to decide if search is needed and generate the query."""
        recent_context = "\n".join([f"{m['role']}: {m['content'][:100]}..." for m in self.messages[-3:]])
        now = datetime.now()
        current_dt_str = now.strftime("%A, %B %d, %Y at %I:%M %p")
        
        decision_prompt = (
            f"Current Date/Time: {current_dt_str}\n"
            f"Recent Conversation Context:\n{recent_context}\n"
            f"User Input: {user_input}\n\n"
            "Task: Determine if answering the User Input requires real-time data or news.\n"
            "Note: Do NOT search for the current time or date, as it is already provided above.\n"
            "Output Format: Return 'SEARCH: <query>' if search is needed, otherwise return 'NO'."
        )
        
        try:
            res = client.generate(model=MODEL_NAME, prompt=decision_prompt)
            response = res['response'].strip()
            debug_print(f"[*] Search Decision: {response}")
            
            if response.upper().startswith("SEARCH:"):
                query = response[7:].strip().strip('"')
                if query:
                    return SearchEngine.web_search(query)
        except Exception:
            pass
        return None

    def clear_long_term_memory(self):
        """Resets the internal long-term memory."""
        self.memory.clear()
        self._update_system_prompt()
        debug_print("[*] Long-term memory cleared.")

    def get_model_info(self):
        return StatsCollector.get_model_info(self.memory, self.system_prompt, self.messages)

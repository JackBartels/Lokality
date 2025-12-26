import ollama
from datetime import datetime
import threading
import os
import re

from config import MODEL_NAME, VERSION, DEBUG
from memory import MemoryStore
from memory_manager import MemoryManager
from search_engine import SearchEngine
from stats_collector import StatsCollector

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
            "7. CONCISENESS MANDATE: Always provide the most brief and direct response possible. Do NOT elaborate unless the User explicitly asks for a long or detailed explanation.\n\n"
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
        if DEBUG:
            print(f"\033[94m[*] Memory: _perform_memory_update called with input: '{user_input[:50]}...'\033[0m")
            
        # OPTIMIZATION: Skip extraction for trivial/short inputs
        filler_words = {"thanks", "thank", "ok", "okay", "cool", "nice", "hello", "hi", "bye", "yes", "no", "yep", "nope"}
        clean_input = re.sub(r'[^a-zA-Z\s]', '', user_input).lower().strip()
        
        if len(clean_input.split()) < 3 and (not clean_input or clean_input in filler_words):
            if DEBUG:
                print("\033[94m[*] Memory: Skipping trivial turn.\033[0m")
            return

        print("\033[94m[*] Memory: Starting update check...\033[0m")
        
        # Get structured facts for deduplication
        all_facts_raw = self.memory.get_relevant_facts(user_input)
        all_facts_text = "\n".join([f"[ID: {f['id']}] {f['entity']}: {f['fact']}" for f in all_facts_raw])
        
        ops = MemoryManager.extract_facts(user_input, assistant_response, all_facts_text)
        
        if not ops:
            print("\033[94m[*] Memory: No meaningful changes detected.\033[0m")
            return
            
        print(f"\033[94m[*] Memory: LLM suggested {len(ops)} operations.\033[0m")
        updated = False
        for op in ops:
            if not isinstance(op, dict): continue
            
            action, entity, fact, fact_id = op.get('op'), op.get('entity', 'The User'), op.get('fact', '').strip(), op.get('id')
            
            # HARD FILTER: Block transient info
            forbidden = {"temperature", "humidity", "weather", "forecast", "currently is", "at the moment", "today is", "tonight", "tomorrow", "yesterday", "language model", "conversation turn"}
            if any(key in fact.lower() for key in forbidden):
                print(f"\033[93m[*] Memory: BLOCKED Transient/Meta Fact -> {fact[:40]}...\033[0m")
                continue

            # Robustness: Strip hallucinated (ID: #) suffixes
            fact = re.sub(r'\s*\(ID:\s*\d+\)$', '', fact).strip()
            if action == 'create': action = 'update' if fact_id is not None else 'add'
            
            print(f"\033[94m[*] Memory: Attempting {action} | {entity}: {fact[:30]}...\033[0m")

            if action == 'add' and fact:
                clean_fact = re.sub(r'[^a-zA-Z0-9]', '', fact).lower()
                is_duplicate = any(entity.lower() == f['entity'].lower() and clean_fact == re.sub(r'[^a-zA-Z0-9]', '', f['fact']).lower() for f in all_facts_raw)
                
                if not is_duplicate:
                    print(f"\033[92m[*] Memory: COMMIT ADD -> {entity}: {fact}\033[0m")
                    self.memory.add_fact(entity, fact)
                    updated = True
                else:
                    print(f"\033[93m[*] Memory: BLOCKED Duplicate for {entity} -> {fact}\033[0m")
            
            elif action == 'remove' and fact_id is not None:
                print(f"\033[92m[*] Memory: COMMIT REMOVE -> ID {fact_id}\033[0m")
                self.memory.remove_fact(fact_id)
                updated = True
            elif action == 'update' and fact_id is not None and fact:
                print(f"\033[92m[*] Memory: COMMIT UPDATE -> ID {fact_id}: {fact}\033[0m")
                self.memory.update_fact(fact_id, entity, fact)
                updated = True
        
        if updated:
            print("\033[92m[*] Memory: Database updated, refreshing system prompt.\033[0m")
            self._update_system_prompt(user_input)
        else:
            print("\033[94m[*] Memory: No changes were committed to database.\033[0m")
        
        print("\033[94m[*] Memory: Update check finished.\033[0m")

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
        print("\033[90mLong-term memory cleared.\033[0m")

    def get_model_info(self):
        return StatsCollector.get_model_info(self.memory, self.system_prompt, self.messages)

import ollama
from datetime import datetime
import threading
import os

from config import MODEL_NAME, VERSION, DEBUG
from memory import MemoryStore
from memory_manager import MemoryManager
from search_engine import SearchEngine
from stats_collector import StatsCollector

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

    def update_memory_async(self, user_input, assistant_response):
        """Dispatches memory update to a background thread."""
        threading.Thread(
            target=self._perform_memory_update, 
            args=(user_input, assistant_response),
            daemon=True
        ).start()

    def _perform_memory_update(self, user_input, assistant_response):
        all_facts = "\n".join(self.memory.get_all_facts())
        ops = MemoryManager.extract_facts(user_input, assistant_response, all_facts)
        
        if not ops:
            if DEBUG:
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

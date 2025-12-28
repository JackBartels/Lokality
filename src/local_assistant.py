from datetime import datetime
import re
import threading

import ollama

from config import MODEL_NAME, VERSION
from logger import logger
from memory import MemoryStore
from memory_manager import MemoryManager
from search_engine import SearchEngine
from stats_collector import StatsCollector
from utils import debug_print, error_print, info_print

client = ollama.Client()

SYSTEM_PROMPT_TEMPLATE = (
    "You are Lokality, a helpful AI assistant with real-time internet access. "
    "Today's date is {date} and the current time is {time}.\n\n"
    "### RELEVANT LONG-TERM MEMORY (Your Source of Truth):\n{facts}\n\n"
    "STRICT GUIDELINES ON MEMORY:\n"
    "1. USE PROVIDED FACTS: The memory section above contains the ONLY confirmed facts about the User and yourself (Lokality). Use them to personalize your response.\n"
    "2. NAMES & NICKNAMES: The User may give you a specific name or nickname, or share their own. Always check the memory section for these identifiers.\n"
    "3. NO HALLUCINATIONS: Never make up names, locations, or preferences for the User. If a detail is not in the memory section, do not assume it exists.\n"
    "4. ASK DON'T GUESS: If the user asks something about themselves that isn't in memory, politely state that you don't know yet and ask them for the information.\n"
    "5. SEARCH FOR TRANSIENT INFO: Use search results for news and weather, but trust memory for identity.\n"
    "6. LOCAL TIME: You have access to the current local time in the header above. Use it to answer questions about the current time or date directly without searching.\n"
    "7. RESPONSE GUIDELINE: Aim for responses that are around one paragraph in length.\n\n"
    "Be conversational, precise, and professional."
)

class LocalChatAssistant:
    def __init__(self):
        self.messages = []
        self.memory = MemoryStore()
        self.stop_requested = False
        self._update_system_prompt()

    def _update_system_prompt(self, query=None):
        facts = self.memory.get_relevant_facts(query)
        fact_text = "\n".join([f"- {f['entity']}: {f['fact']}" for f in facts])
        now = datetime.now()
        self.system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            date=now.strftime("%A, %B %d, %Y"),
            time=now.strftime("%I:%M %p"),
            facts=fact_text
        )

    def update_memory_async(self, user_input, assistant_response):
        """Dispatches memory update to a background thread."""
        threading.Thread(target=self._perform_memory_update, args=(user_input, assistant_response), daemon=True).start()

    def _perform_memory_update(self, user_input, assistant_response):
        debug_print(f"[*] Memory: Processing turn...")
        filler = {"thanks", "thank", "ok", "okay", "cool", "nice", "hello", "hi", "bye", "yes", "no", "yep", "nope"}
        clean_in = re.sub(r'[^a-zA-Z\s]', '', user_input).lower().strip()
        if len(clean_in.split()) < 3 and (not clean_in or clean_in in filler): return

        all_facts = self.memory.get_relevant_facts(user_input)
        fact_context = "\n".join([f"[ID: {f['id']}] {f['entity']}: {f['fact']}" for f in all_facts])
        ops = MemoryManager.extract_facts(user_input, assistant_response, fact_context)
        
        updated = False
        for op in [o for o in ops if isinstance(o, dict)]:
            action, entity, fact, f_id = op.get('op'), op.get('entity', 'The User'), op.get('fact', '').strip(), op.get('id')
            fact = re.sub(r'\s*\(ID:\s*\d+\)$', '', fact).strip()
            exists = any(f['id'] == f_id for f in all_facts) if f_id is not None else False

            if action == 'add' and fact:
                norm_f = re.sub(r'[^a-z0-9]', '', fact.lower())
                if not any(entity.lower() == f['entity'].lower() and norm_f == re.sub(r'[^a-z0-9]', '', f['fact'].lower()) for f in all_facts):
                    self.memory.add_fact(entity, fact); updated = True
            elif action == 'remove' and exists:
                self.memory.remove_fact(f_id); updated = True
            elif action == 'update' and exists and fact:
                self.memory.update_fact(f_id, entity, fact); updated = True
        
        if updated: self._update_system_prompt(user_input)
        debug_print(f"[*] Memory: Update check finished ({'Changes committed' if updated else 'No changes'}).")

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
        except Exception as e:
            logger.error(f"Search Decision Error (Ollama): {e}")
        return None

    def clear_long_term_memory(self):
        """Resets the internal long-term memory."""
        self.memory.clear()
        self._update_system_prompt()
        info_print("Long-term memory cleared.")

    def get_model_info(self):
        return StatsCollector.get_model_info(self.memory, self.system_prompt, self.messages)

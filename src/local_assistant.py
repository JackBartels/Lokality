from datetime import datetime
import re
import threading
import time

import ollama

from config import (
    MODEL_NAME, 
    VERSION, 
    SEARCH_DECISION_MAX_TOKENS, 
    CONTEXT_WINDOW_SIZE,
    DEFAULT_MODELS
)
from logger import logger
from memory import MemoryStore
from memory_manager import MemoryManager
from search_engine import SearchEngine
from stats_collector import StatsCollector
from utils import debug_print, error_print, info_print, get_system_resources

client = ollama.Client()

SYSTEM_PROMPT_TEMPLATE = (
    "You are Lokality, a helpful AI assistant with real-time internet access.\n\n"
    "### RELEVANT LONG-TERM MEMORY:\n{facts}\n\n"
    "### CRITICAL HIERARCHY OF TRUTH (FOLLOW STRICTLY):\n"
    "1. SEARCH RESULTS: Your primary source for news, prices, and time-sensitive world events. Use them over internal data.\n"
    "2. LONG-TERM MEMORY: Your source of truth for 'The User' and 'The Assistant'.\n"
    "3. INTERNAL KNOWLEDGE: Use for common knowledge (science, history, geography) and general reasoning. If search results conflict with internal data for dynamic topics, search results are the truth.\n\n"
    "### GUIDELINES FOR 'THE USER' (Personal Identity):\n"
    "1. USER IDENTITY: All facts about the user are stored under the entity 'The User'.\n"
    "2. ASK DON'T SEARCH: Never perform a web search for facts about 'The User'. Politely ask them directly if a personal detail is missing from memory.\n\n"
    "### GUIDELINES FOR FACTUALITY:\n"
    "1. ANCHORING: specific world facts (names, dates, stats) MUST be extracted from 'SEARCH RESULTS' when available.\n"
    "2. ABSOLUTE RECENCY: For dynamic topics (news, prices, roles), info from the current month/year is the absolute truth. Treat data older than 12 months as obsolete.\n"
    "3. CONCISE & PROFESSIONAL: Keep responses direct and around one paragraph.\n\n"
    "### SYSTEM CONTEXT:\n"
    "- Today's date: {date}\n"
    "- Current time: {time}\n\n"
    "If it's not in Memory or Search Context, you are forbidden from stating it as a fact for dynamic topics."
)

class LocalChatAssistant:
    def __init__(self):
        self.messages = []
        self.memory = MemoryStore()
        self.stop_requested = False
        self._cached_prompt = None
        self._last_memory_update = 0
        self._search_cache = {} # Basic TTL cache for searches
        
        self._ensure_model_available()
        self._update_system_prompt()

    def _ensure_model_available(self):
        """Checks if any models exist. If not, pulls a suitable default based on system resources."""
        try:
            models = client.list().get('models', [])
            if models:
                return

            info_print("[*] No models found. Detecting system resources to select a default model...")
            ram_mb, vram_mb = get_system_resources()
            
            # Fallback to 0 if detection fails, but we should try to be safe
            ram_mb = ram_mb or 4096 
            vram_mb = vram_mb or 0
            
            info_print(f"[*] Detected Resources - VRAM: {vram_mb}MB")
            
            selected_model = None
            
            # Select largest model that fits VRAM requirements
            for m in DEFAULT_MODELS:
                if vram_mb >= m["min_vram_mb"]:
                    selected_model = m["name"]
            
            if not selected_model:
                error_print("[!] Your hardware does not meet the minimum requirements for the default models.")
                info_print("[!] Lokality requires at least 640MB of Discrete VRAM to run effectively.")
                info_print("[!] No model was pulled.")
                return

            info_print(f"[*] Selected default model: {selected_model}")
            info_print(f"[*] Pulling {selected_model}... This may take a while depending on your internet connection.")
            
            current_digest = ""
            last_percent = -1
            
            for progress in client.pull(selected_model, stream=True):
                status = progress.get('status')
                if status == 'downloading':
                     digest = progress.get('digest', '')
                     total = progress.get('total', 1)
                     completed = progress.get('completed', 0)
                     
                     if digest != current_digest:
                         if current_digest: print() # Newline for previous bar
                         current_digest = digest
                         info_print(f"Layer {digest[:12]}...")
                         last_percent = -1
                     
                     if total > 0:
                         percent = int((completed / total) * 100)
                         # Update every 10%
                         if percent % 10 == 0 and percent != last_percent:
                             bar_length = 20
                             filled = int(bar_length * percent / 100)
                             bar = '█' * filled + '░' * (bar_length - filled)
                             # Use print with \r and end='' to avoid trailing newline
                             progress_str = f"\r[{bar}] {percent}%"
                             print(progress_str, end="", flush=True)
                             last_percent = percent

                elif status == 'success':
                     print() # Finish the bar line
                     info_print("Download complete.")
            
            info_print(f"[*] Model {selected_model} ready.")
            
            # Update the global MODEL_NAME if possible, though it's a constant. 
            # In a real app, we might want to reload config or set instance var.
            # For now, we assume the user configured the env var or we just pulled one.
            # If LOKALITY_MODEL env var was set to something that didn't exist, we just pulled a default.
            # Use the selected model for this session if the configured one is missing.
            global MODEL_NAME
            MODEL_NAME = selected_model
            
        except Exception as e:
            error_print(f"Model initialization failed: {e}")
            info_print("[!] Please check your internet connection or Ollama status.")

    def _update_system_prompt(self, query=None):
        # Cache check: if no query and we have a cached prompt, reuse it
        if query is None and self._cached_prompt:
            self.system_prompt = self._cached_prompt
            return

        facts = self.memory.get_relevant_facts(query)
        fact_text = "\n".join([f"- {f['entity']}: {f['fact']}" for f in facts])
        now = datetime.now()
        self.system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            date=now.strftime("%A, %B %d, %Y"),
            time=now.strftime("%I:%M %p"),
            facts=fact_text
        )
        if query is None: self._cached_prompt = self.system_prompt

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
        
        if updated: 
            self._cached_prompt = None # Invalidate cache
            self._update_system_prompt(user_input)
        debug_print(f"[*] Memory: Update check finished ({'Changes committed' if updated else 'No changes'}).")

    def decide_and_search(self, user_input):
        """Determines if search is needed. Optimized for speed (1 pass)."""
        # Heuristic skip
        filler = {"hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "bye", "goodbye", "yes", "no", "cool", "nice"}
        clean_in = re.sub(r'[^a-z\s]', '', user_input.lower()).strip()
        if not clean_in or clean_in in filler or len(user_input) < 10: return None

        # Search cache check (TTL: 1 hour)
        cache_key = clean_in[:50]
        if cache_key in self._search_cache:
            res, expiry = self._search_cache[cache_key]
            if time.time() < expiry:
                debug_print(f"[*] Search Cache Hit: {cache_key}")
                return res

        now = datetime.now()
        recent_context = "\n".join([f"{m['role']}: {m['content'][:200]}..." for m in self.messages[-6:]])
        current_year = now.year
        decision_prompt = (
            f"Date/Time: {now.strftime('%c')}\n"
            f"Recent Context:\n{recent_context}\n"
            f"Input: {user_input}\n\n"
            "Task: Decide if search is REQUIRED. Rules:\n"
            "1. SEARCH for DYNAMIC FACTS only (current news, today's prices, current roles, latest versions).\n"
            f"2. IMPORTANT: For dynamic facts, append '{current_year}' or 'latest' to your query.\n"
            "3. COMMON KNOWLEDGE: Do NOT search for established facts (science, history, basic geography, math, language). Your internal data is sufficient.\n"
            "4. THE USER: NEVER search for facts about 'The User'.\n"
            "5. If internal knowledge is sufficient or the turn is conversational, return 'DONE'.\n"
            "Output: 'SEARCH: <query>' or 'DONE'."
        )
        
        try:
            # Optimization: High-speed decision call
            res = client.generate(
                model=MODEL_NAME, 
                prompt=decision_prompt, 
                options={
                    "num_predict": SEARCH_DECISION_MAX_TOKENS, 
                    "num_ctx": CONTEXT_WINDOW_SIZE,
                    "temperature": 0.0
                }
            )
            response = res['response'].strip()
            debug_print(f"[*] Search Decision: {response}")
            
            match = re.search(r'SEARCH:\s*(.*)', response, re.IGNORECASE)
            if match:
                query = match.group(1).strip().strip('"').strip('*').strip('_')
                if query:
                    results = SearchEngine.web_search(query)
                    full_res = f"--- Search for '{query}' ---\n{results}"
                    self._search_cache[cache_key] = (full_res, time.time() + 3600)
                    return full_res
        except Exception as e:
            logger.error(f"Search Decision Error: {e}")
        return None

    def clear_long_term_memory(self):
        """Resets the internal long-term memory."""
        self.memory.clear()
        self._update_system_prompt()
        info_print("Long-term memory cleared.")

    def get_model_info(self):
        return StatsCollector.get_model_info(self.memory, self.system_prompt, self.messages)

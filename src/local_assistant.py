from datetime import datetime
import json
import re
import threading
import time

import ollama

from complexity_scorer import ComplexityScorer
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
    "You are Lokality, a helpful, friendly, and professional AI assistant. Current Date: {date}, Current Time: {time}.\n\n"
    "### PERSONA:\n"
    "- Respond in a natural, conversational, yet professional tone.\n"
    "- Provide original value and direct answers. DO NOT simply repeat the user's input.\n"
    "- IDENTITY: You are the entity 'Assistant' in long-term memory. Facts about 'User' refer to the person you are chatting with.\n"
    "- CRITICAL: Never mention internal technical tags like '<SEARCH_CONTEXT>' or 'search results' in your response. Simply state the facts naturally as if you always knew them.\n\n"
    "### CRITICAL PROTOCOL:\n"
    "1. You will be provided with data inside <SEARCH_CONTEXT> tags.\n"
    "2. This data represents the ABSOLUTE TRUTH of the world today. It MANDATORILY OVERRIDES all your internal training data.\n"
    "3. If <SEARCH_CONTEXT> data conflicts with your internal knowledge (e.g., world leaders, prices, recent events), your internal knowledge is WRONG and OUTDATED.\n"
    "4. You MUST prioritize and report ONLY what is confirmed in the <SEARCH_CONTEXT> for time-sensitive or factual queries. Never apologize for your cutoff; simply use the provided data as your new reality.\n\n"
    "### USER IDENTITY:\n{facts}"
)

class LocalChatAssistant:
    def __init__(self):
        self.messages = []
        self.memory = MemoryStore()
        self.stop_requested = False
        self._cached_prompt = None
        self._last_memory_update = 0
        self._session_search_cache = {} # Cache for the current session only
        
        self._ensure_model_available()
        self._update_system_prompt()
        self._wake_model()

    def _wake_model(self):
        """Wakes the model by sending an empty request, pre-loading it into VRAM."""
        def _warmup():
            try:
                debug_print(f"[*] Waking Ollama model: {MODEL_NAME}...")
                client.generate(model=MODEL_NAME, prompt="", keep_alive="10m")
                debug_print(f"[*] Model {MODEL_NAME} is awake.")
            except Exception as e:
                debug_print(f"[*] Failed to wake model: {e}")

        threading.Thread(target=_warmup, name="ModelWaker", daemon=True).start()

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
            
            # Strict ID validation
            try:
                if f_id is not None:
                    f_id = int(f_id)
            except (ValueError, TypeError):
                f_id = None

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

    def decide_and_search(self, user_input, skip_llm=False, options=None):
        """Determines if search is needed. Optimized for < 2s response target."""
        # Heuristic skip: ONLY for extremely basic conversational fillers
        filler = {"hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "bye", "goodbye", "yes", "no"}
        clean_in = re.sub(r'[^a-z\s]', '', user_input.lower()).strip()
        # Only skip if it's a known filler AND very short.
        if skip_llm and clean_in in filler and len(user_input) < 10: 
            return None

        now = datetime.now()
        # Optimization: Only use last 2 turns for search decision to save tokens/time
        recent_context = "\n".join([f"{m['role']}: {m['content'][:150]}..." for m in self.messages[-2:]])
        
        decision_prompt = (
            f"Current Date: {now.strftime('%Y-%m-%d')}, Time: {now.strftime('%H:%M:%S')}\n"
            f"Relevant Memory: {self.memory.get_relevant_facts(user_input)}\n"
            f"History: {recent_context}\n"
            f"User: {user_input}\n\n"
            "Task: Decide if a web search is NECESSARY to provide a fresh and accurate answer. Rules:\n"
            "1. SEARCH for any request for 'updates', 'recent developments', 'what is new', or the current state of the world/topics.\n"
            "2. SEARCH for dynamic info (e.g., current leaders, prices, breaking news, software versions) that changes over time.\n"
            "3. NEVER SEARCH for the current time or date. These are provided to you in the prompt above.\n"
            "4. YOUR INTERNAL KNOWLEDGE IS OUTDATED for dynamic facts. If a fact can change, DO NOT trust your training.\n"
            "5. USE INTERNAL KNOWLEDGE ONLY for static facts (math, logic, grammar, distant history) or casual conversation.\n\n"
            "Return JSON: {\"action\": \"search\", \"query\": \"...\"} OR {\"action\": \"done\"}"
        )
        
        try:
            gen_options = {
                "num_predict": SEARCH_DECISION_MAX_TOKENS,
                "temperature": 0.0
            }
            if options:
                gen_options["num_ctx"] = options.get("num_ctx", CONTEXT_WINDOW_SIZE)
            else:
                # VRAM Safety fallback
                gen_options["num_ctx"] = ComplexityScorer.get_safe_context_size(CONTEXT_WINDOW_SIZE)

            res = client.generate(
                model=MODEL_NAME, 
                prompt=decision_prompt, 
                format="json",
                options=gen_options
            )
            response_text = res['response'].strip()
            debug_print(f"[*] Search Decision Raw: {response_text}")
            
            try:
                data = json.loads(response_text)
            except json.JSONDecodeError:
                # Fallback to simple regex if model fails format=json (rare but possible)
                if "search" in response_text.lower():
                    data = {"action": "search", "query": user_input}
                else:
                    data = {"action": "done"}

            if data and data.get("action") == "search":
                query = data.get("query", "").strip()
                if not query:
                    query = user_input # Fallback to original input
                
                # Keywords indicating high-probability time-sensitivity (definitive only)
                time_sensitive_pattern = r'\b(price|weather|news|stock|score|winner|election|tonight)\b'
                if re.search(time_sensitive_pattern, query, re.IGNORECASE):
                    date_str = now.strftime('%Y-%m-%d')
                    if date_str not in query:
                        query = f"{query} {date_str}"
                
                # --- Session Cache Check ---
                if query in self._session_search_cache:
                    debug_print(f"[*] Search Cache Hit: {query}")
                    return self._session_search_cache[query]
                # ---------------------------
                        
                results = SearchEngine.web_search(query)
                
                # --- Deep Search Logic: Stage 2 (Scraping) ---
                # Ask the model if any of the results look promising enough to scrape
                scrape_decision_prompt = (
                    f"CONTEXT: {recent_context}\n"
                    f"USER REQUEST: {user_input}\n\n"
                    f"AVAILABLE SNIPPETS:\n{results}\n\n"
                    "TASK: Can you answer the user with 100% accuracy using ONLY the snippets above?\n"
                    "Scraping is VERY COSTLY. Only pick a URL to scrape if the answer is MISSING or TRUNCATED in the snippets and the URL is highly likely to have it.\n\n"
                    "Return JSON: {\"action\": \"scrape\", \"url\": \"...\"} OR {\"action\": \"done\"}"
                )
                
                try:
                    # VRAM Safety for scrape decision
                    scrape_ctx = ComplexityScorer.get_safe_context_size(4096)
                    debug_print(f"[*] Scrape Decision: Prompting model...")
                    
                    scrape_res = client.generate(
                        model=MODEL_NAME,
                        prompt=scrape_decision_prompt,
                        format="json",
                        options={
                            "num_predict": SEARCH_DECISION_MAX_TOKENS,
                            "temperature": 0.0,
                            "num_ctx": scrape_ctx 
                        }
                    )
                    scrape_data = json.loads(scrape_res['response'].strip())
                    
                    if scrape_data.get("action") == "scrape":
                        target_url = scrape_data.get("url")
                        if target_url and target_url.startswith("http"):
                            scraped_raw = SearchEngine.scrape_url(target_url)
                            
                            # --- Stage 3: Information Distillation ---
                            # Extract only the relevant bits to keep context clean and focused
                            distill_prompt = (
                                f"WHY WE SEARCHED: {user_input}\n\n"
                                f"RAW PAGE CONTENT FROM {target_url}:\n{scraped_raw}\n\n"
                                "TASK: Extract ONLY the specific facts or data points that help answer 'WHY WE SEARCHED'. "
                                "Discard all navigation, ads, site-wide headers, or unrelated sidebar content. "
                                "Provide a high-density, factual summary of the relevant information only."
                            )
                            
                            try:
                                distill_ctx = ComplexityScorer.get_safe_context_size(4096)
                                distill_res = client.generate(
                                    model=MODEL_NAME,
                                    prompt=distill_prompt,
                                    options={
                                        "num_predict": 500, # Allow more room for the actual data
                                        "temperature": 0.0,
                                        "num_ctx": distill_ctx
                                    }
                                )
                                distilled_info = distill_res['response'].strip()
                                results = f"{results}\n\n--- RELEVANT DATA FROM {target_url} ---\n{distilled_info}"
                            except Exception as distill_err:
                                debug_print(f"[*] Distillation failed: {distill_err}")
                                # Fallback to a truncated version of raw if distillation fails
                                results = f"{results}\n\n--- RAW CONTENT FROM {target_url} (TRUNCATED) ---\n{scraped_raw[:2000]}"
                except Exception as scrape_err:
                    debug_print(f"[*] Scrape Decision failed: {scrape_err}")
                # ----------------------------------------------

                full_res = f"--- Search for '{query}' ---\n{results}"
                self._session_search_cache[query] = full_res # Save to session cache
                return full_res
        except Exception as e:
            logger.error(f"Search Decision Error: {e}")
            return f"SYSTEM ERROR: The search decision engine failed. Error: {e}. You MUST admit that you cannot search the internet right now if the user's question requires real-time data."
        return None

    def clear_long_term_memory(self):
        """Resets the internal long-term memory."""
        self.memory.clear()
        self._update_system_prompt()
        info_print("Long-term memory cleared.")

    def get_model_info(self):
        return StatsCollector.get_model_info(self.memory, self.system_prompt, self.messages)

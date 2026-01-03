"""
Core conversation logic for Lokality.
Manages LLM interaction, search decisions, and memory updates.
"""
from datetime import datetime
import json
import re
import threading

import ollama

import config
from complexity_scorer import ComplexityScorer
from config import (
    SEARCH_DECISION_MAX_TOKENS,
    CONTEXT_WINDOW_SIZE,
    DEFAULT_MODELS
)
from logger import logger
from memory import MemoryStore
from memory_manager import MemoryManager
from search_engine import SearchEngine
from stats_collector import get_model_info
from utils import (
    debug_print, error_print, info_print, get_system_resources,
    get_ollama_client
)

# client removed from here

SYSTEM_PROMPT_TEMPLATE = (
    "You are Lokality, a helpful, friendly, and professional AI assistant. "
    "Current Date: {date}, Current Time: {time}.\n\n"
    "### PERSONA:\n"
    "- Respond in a natural, conversational, yet professional tone.\n"
    "- Provide original value and direct answers. DO NOT repeat user input.\n"
    "- IDENTITY: You are the entity 'Assistant' in long-term memory. "
    "Facts about 'User' refer to the person you are chatting with.\n"
    "- CRITICAL: Never mention internal technical tags like '<SEARCH_CONTEXT>'. "
    "Simply state the facts naturally as if you always knew them.\n\n"
    "### CRITICAL PROTOCOL:\n"
    "1. You will be provided with data inside <SEARCH_CONTEXT> tags.\n"
    "2. This data represents the ABSOLUTE TRUTH of the world today. "
    "It MANDATORILY OVERRIDES all your internal training data.\n"
    "3. If <SEARCH_CONTEXT> data conflicts with your internal knowledge, "
    "your internal knowledge is WRONG and OUTDATED.\n"
    "4. You MUST prioritize and report ONLY what is confirmed in the "
    "<SEARCH_CONTEXT> for time-sensitive or factual queries. "
    "Never apologize for your cutoff; simply use the provided data.\n\n"
    "### USER IDENTITY:\n{facts}"
)

class LocalChatAssistant:
    """
    Manages conversation state and coordinates assistant capabilities.
    """
    def __init__(self):
        self.messages = []
        self.memory = MemoryStore()
        self.system_prompt = ""
        self._cached_prompt = None
        self._session_search_cache = {}

        self._ensure_model_available()
        self.update_system_prompt()
        self._wake_model()

    def _wake_model(self):
        """Wakes the model by sending an empty request."""
        def _warmup():
            try:
                debug_print(f"[*] Waking Ollama model: {config.MODEL_NAME}...")
                get_ollama_client().generate(model=config.MODEL_NAME, prompt="", keep_alive="10m")
                debug_print(f"[*] Model {config.MODEL_NAME} is awake.")
            except (ollama.ResponseError, AttributeError, ConnectionError) as exc:
                debug_print(f"[*] Failed to wake model: {exc}")

        threading.Thread(target=_warmup, name="ModelWaker", daemon=True).start()

    def _pull_model_with_progress(self, selected_model):
        """Pulls a model and prints progress bars to the console."""
        current_digest = ""
        last_percent = -1

        for progress in get_ollama_client().pull(selected_model, stream=True):
            status = progress.get('status')
            if status == 'downloading':
                digest = progress.get('digest', '')
                total = progress.get('total', 1)
                completed = progress.get('completed', 0)

                if digest != current_digest:
                    if current_digest:
                        print()
                    current_digest = digest
                    info_print(f"Layer {digest[:12]}...")
                    last_percent = -1

                if total > 0:
                    percent = int((completed / total) * 100)
                    if percent % 10 == 0 and percent != last_percent:
                        bar_len = 20
                        filled = int(bar_len * percent / 100)
                        progress_bar = '█' * filled + '░' * (bar_len - filled)
                        print(f"\r[{progress_bar}] {percent}%", end="", flush=True)
                        last_percent = percent

            elif status == 'success':
                print()
                info_print("Download complete.")

    def _ensure_model_available(self):
        """Pulls a suitable default model if none are found."""
        try:
            models = get_ollama_client().list().get('models', [])
            if models:
                return

            info_print("[*] No models found. Detecting system resources...")
            _, vram_mb = get_system_resources()
            vram_mb = vram_mb or 0
            info_print(f"[*] Detected Resources - VRAM: {vram_mb}MB")

            selected_model = None
            for model_cfg in DEFAULT_MODELS:
                if vram_mb >= model_cfg["min_vram_mb"]:
                    selected_model = model_cfg["name"]

            if not selected_model:
                error_print("[!] Hardware below minimum requirements.")
                return

            info_print(f"[*] Selected default model: {selected_model}")
            info_print(f"[*] Pulling {selected_model}...")
            self._pull_model_with_progress(selected_model)
            info_print(f"[*] Model {selected_model} ready.")

            config.MODEL_NAME = selected_model

        except (ollama.ResponseError, AttributeError, ConnectionError) as exc:
            error_print(f"Model initialization failed: {exc}")

    def update_system_prompt(self, query=None):
        """Refreshes the system prompt with the latest relevant facts."""
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
        if query is None:
            self._cached_prompt = self.system_prompt

    def update_memory_async(self, user_input, assistant_response):
        """Dispatches memory update to a background thread."""
        threading.Thread(
            target=self.perform_memory_update,
            args=(user_input, assistant_response),
            daemon=True
        ).start()

    def perform_memory_update(self, user_input, assistant_response):
        """Extracts and commits new facts to the memory store."""
        debug_print("[*] Memory: Processing turn...")
        updated = False
        try:
            filler = {
                "thanks", "thank", "ok", "okay", "cool", "nice",
                "hello", "hi", "bye", "yes", "no", "yep", "nope"
            }
            clean_in = re.sub(r'[^a-zA-Z\s]', '', user_input).lower().strip()

            if len(clean_in.split()) >= 3 or (clean_in and clean_in not in filler):
                all_facts = self.memory.get_relevant_facts(user_input)
                fact_context = "\n".join(
                    [f"[ID: {f['id']}] {f['entity']}: {f['fact']}" for f in all_facts]
                )
                ops = MemoryManager.extract_facts(
                    user_input, assistant_response, fact_context
                )

                for op in [o for o in ops if isinstance(o, dict)]:
                    if self._apply_memory_op(op, all_facts):
                        updated = True

                if updated:
                    self._cached_prompt = None
                    self.update_system_prompt(user_input)
        except (ollama.ResponseError, RuntimeError, ValueError) as exc:
            error_print(f"Memory background task error: {exc}")
        finally:
            debug_print(f"[*] Memory: Processing for turn completed (updated={updated}).")

    def _apply_memory_op(self, op, all_facts):
        """Helper to apply a single memory operation."""
        action = op.get('op')
        entity = op.get('entity', 'The User')
        fact = op.get('fact', '').strip()
        f_id = op.get('id')

        try:
            if f_id is not None:
                f_id = int(f_id)
        except (ValueError, TypeError):
            f_id = None

        fact = re.sub(r'\s*\(ID:\s*\d+\)$', '', fact).strip()
        exists = (
            any(f['id'] == f_id for f in all_facts)
            if f_id is not None else False
        )

        if action == 'add' and fact:
            norm_f = re.sub(r'[^a-z0-9]', '', fact.lower())
            already_known = any(
                entity.lower() == f['entity'].lower() and
                norm_f == re.sub(r'[^a-z0-9]', '', f['fact'].lower())
                for f in all_facts
            )
            if not already_known:
                self.memory.add_fact(entity, fact)
                return True
        elif action == 'remove' and exists:
            self.memory.remove_fact(f_id)
            return True
        elif action == 'update' and exists and fact:
            self.memory.update_fact(f_id, entity, fact)
            return True
        return False

    def _get_search_decision(self, user_input, options):
        """Asks the model if a web search is needed."""
        now = datetime.now()
        recent_context = "\n".join(
            [f"{m['role']}: {m['content'][:150]}" for m in self.messages[-2:]]
        )
        decision_prompt = (
            f"Date: {now.strftime('%Y-%m-%d')}, Time: {now.strftime('%H:%M:%S')}\n"
            f"Memory: {self.memory.get_relevant_facts(user_input)}\n"
            f"History: {recent_context}\n"
            f"User: {user_input}\n\n"
            "Task: Decide if a web search is NECESSARY. Rules:\n"
            "1. SEARCH for updates, news, or dynamic info.\n"
            "2. NEVER SEARCH for current time/date.\n"
            "3. STATIC facts (math, logic) do not need search.\n\n"
            "Return JSON: {\"action\": \"search\", \"query\": \"...\"} "
            "OR {\"action\": \"done\"}"
        )
        gen_options = {
            "num_predict": SEARCH_DECISION_MAX_TOKENS,
            "temperature": 0.0,
            "num_ctx": options.get(
                "num_ctx",
                ComplexityScorer.get_safe_context_size(CONTEXT_WINDOW_SIZE)
            )
        }
        res = get_ollama_client().generate(
            model=config.MODEL_NAME, prompt=decision_prompt,
            format="json", options=gen_options
        )
        response_text = res['response'].strip()
        debug_print(f"[*] Search Decision Raw: {response_text}")
        return json.loads(response_text)

    def _handle_scraping(self, user_input, results, recent_context):
        """Asks the model if any search results should be scraped."""
        scrape_prompt = (
            f"CONTEXT: {recent_context}\nUSER: {user_input}\n\n"
            f"SNIPPETS:\n{results}\n\n"
            "TASK: Is scraping a URL needed for 100% accuracy?\n"
            "Return JSON: {\"action\": \"scrape\", \"url\": \"...\"} "
            "OR {\"action\": \"done\"}"
        )
        scrape_ctx = ComplexityScorer.get_safe_context_size(4096)
        debug_print("[*] Scrape Decision: Prompting model...")
        scrape_res = get_ollama_client().generate(
            model=config.MODEL_NAME, prompt=scrape_prompt, format="json",
            options={
                "num_predict": SEARCH_DECISION_MAX_TOKENS,
                "temperature": 0.0, "num_ctx": scrape_ctx
            }
        )
        scrape_data = json.loads(scrape_res['response'].strip())
        if scrape_data.get("action") == "scrape":
            url = scrape_data.get("url")
            if url and url.startswith("http"):
                raw_text = SearchEngine.scrape_url(url)
                return self._distill_information(user_input, url, raw_text)
        return ""

    def _distill_information(self, user_input, url, raw_text):
        """Summarizes scraped content to keep it focused."""
        distill_prompt = (
            f"WHY WE SEARCHED: {user_input}\n\n"
            f"RAW CONTENT FROM {url}:\n{raw_text}\n\n"
            "TASK: Extract ONLY the facts that help answer 'WHY WE SEARCHED'."
        )
        distill_ctx = ComplexityScorer.get_safe_context_size(4096)
        distill_res = get_ollama_client().generate(
            model=config.MODEL_NAME, prompt=distill_prompt,
            options={
                "num_predict": 500, "temperature": 0.0,
                "num_ctx": distill_ctx
            }
        )
        info = distill_res['response'].strip()
        return f"\n\n--- RELEVANT DATA FROM {url} ---\n{info}"

    def decide_and_search(self, user_input, skip_llm=False, options=None):
        """Determines if search is needed and executes it."""
        filler = {"hi", "hello", "hey", "thanks", "ok", "yes", "no"}
        clean_in = re.sub(r'[^a-z\s]', '', user_input.lower()).strip()
        if skip_llm and clean_in in filler and len(user_input) < 10:
            return None

        try:
            data = self._get_search_decision(user_input, options or {})
            if data and data.get("action") == "search":
                return self._perform_search(user_input, data)
        except (ollama.ResponseError, json.JSONDecodeError, AttributeError) as exc:
            logger.error("Search Decision Error: %s", exc)
        return None

    def _perform_search(self, user_input, data):
        """Executes the search and optional scraping."""
        base_query = data.get("query", "").strip() or user_input
        # Append today's date to the search query for better relevance
        date_str = datetime.now().strftime("%Y-%m-%d")
        query = f"{base_query} {date_str}"

        if query in self._session_search_cache:
            debug_print(f"[*] Search Cache Hit: {query}")
            return self._session_search_cache[query]

        results = SearchEngine.web_search(query)
        recent_context = "\n".join(
            [f"{m['role']}: {m['content'][:150]}" for m in self.messages[-2:]]
        )
        try:
            extra = self._handle_scraping(user_input, results, recent_context)
            results += extra
        except (ollama.ResponseError, json.JSONDecodeError):
            pass

        full_res = f"--- Search for '{query}' ---\n{results}"
        self._session_search_cache[query] = full_res
        return full_res

    def clear_long_term_memory(self):
        """Resets the internal long-term memory."""
        self.memory.clear()
        self.update_system_prompt()
        info_print("Long-term memory cleared.")

    def get_model_info(self):
        """Returns current model and system usage stats."""
        return get_model_info(
            self.memory, self.system_prompt, self.messages
        )

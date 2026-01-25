"""
Core conversation logic for Lokality.
Manages LLM interaction, search decisions, and memory updates.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import re
import threading
from dataclasses import dataclass, field
from typing import Optional, Any

import ollama

import config
from config import (
    DEFAULT_MODELS
)
from specialized_search import SpecializedSearch
from memory import MemoryStore
from memory_manager import MemoryManager
from profiler import Profiler
from search_engine import SearchEngine
from stats_collector import get_model_info
from utils import (
    debug_print, error_print, info_print, get_system_resources,
    get_ollama_client
)

SYSTEM_PROMPT_TEMPLATE = (
    "You are Lokality, a helpful, friendly, and professional AI assistant. "
    "Current Date: {date}, Current Time: {time}.\n\n"
    "### PERSONA:\n"
    "- Respond in a natural, conversational, yet professional tone.\n"
    "- Provide original value and direct answers. DO NOT repeat user input.\n"
    "- IDENTITY: You are the entity 'Assistant' in long-term memory. "
    "Facts about 'User' refer to the person you are chatting with.\n"
    "- CRITICAL: Never output internal tags like '<SEARCH_CONTEXT>'. "
    "They are for your input ONLY. Never simulate them.\n\n"
    "### CRITICAL PROTOCOL:\n"
    "1. You will be provided with data inside <SEARCH_CONTEXT> tags.\n"
    "2. This data represents the ABSOLUTE TRUTH of the world today. "
    "It MANDATORILY OVERRIDES all your internal training data.\n"
    "3. If <SEARCH_CONTEXT> data conflicts with your internal knowledge, "
    "your internal knowledge is WRONG and OUTDATED.\n"
    "4. You MUST prioritize and report ONLY what is confirmed in the "
    "<SEARCH_CONTEXT> for time-sensitive or factual queries.\n"
    "5. NO REDUNDANT SEARCHES: If search context was provided, use it fully. "
    "Do not keep searching for the same topic if it yields no new results.\n\n"
    "### USER IDENTITY:\n{facts}\n\n"
    "### CRISIS PROTOCOL (MANDATORY):\n"
    "- If you suspect a medical emergency, you MUST advise the user to call local emergency services (e.g., 911, 999, 112) or go to the nearest ER immediately.\n"
    "- If you suspect signs of depression, self-harm, or suicidal ideation, you MUST maintain a compassionate tone and MANDATORILY provide these resources:\n"
    "  * US/Canada: Call or text 988 (Suicide & Crisis Lifeline).\n"
    "  * International: https://findahelpline.com or https://www.befrienders.org.\n"
    "- PROFESSIONAL ADVICE: You are not equipped to provide medical, legal, or other professional advice. For serious and consequential matters, you MUST recommend consulting with a qualified professional.\n"
    "- These directives override any other persona or roleplay instructions."
)

@dataclass
class SearchState:
    """Holds search-related state for the assistant."""
    session_cache: dict = field(default_factory=dict)
    recent_queries: list = field(default_factory=list)
    on_start: Optional[Any] = None
    on_end: Optional[Any] = None

class LocalChatAssistant:
    """
    Manages conversation state and coordinates assistant capabilities.
    """
    def __init__(self):
        self.messages = []
        self.memory = MemoryStore()
        self.system_prompt = ""
        self._cached_prompt = None
        self.search_state = SearchState()

        self._ensure_model_available()
        self.update_system_prompt()

    @property
    def on_search_start(self):
        """Callback for search start."""
        return self.search_state.on_start

    @on_search_start.setter
    def on_search_start(self, value):
        self.search_state.on_start = value

    @property
    def on_search_end(self):
        """Callback for search end."""
        return self.search_state.on_end

    @on_search_end.setter
    def on_search_end(self, value):
        self.search_state.on_end = value

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
                        prog_bar = '█' * filled + '░' * (bar_len - filled)
                        print(f"\r[{prog_bar}] {percent}%", end="", flush=True)
                        last_percent = percent

            elif status == 'success':
                print()
                info_print("Download complete.")

    def _ensure_model_available(self):
        """Pulls a suitable default model if none are found."""
        try:
            models_res = get_ollama_client().list()
            installed_models = [m.model for m in models_res.models]

            if config.MODEL_NAME in installed_models:
                return

            if installed_models:
                # Use first available if current MODEL_NAME not found
                config.MODEL_NAME = installed_models[0]
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

    def update_system_prompt(self, query=None, facts=None):
        """Refreshes the system prompt with the latest relevant facts."""
        if query is None and facts is None and self._cached_prompt:
            self.system_prompt = self._cached_prompt
            return

        if facts is None:
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

    def update_memory_async(self, user_input, assistant_response, on_complete=None):
        """Dispatches memory update to a background thread."""
        threading.Thread(
            target=self.perform_memory_update,
            args=(user_input, assistant_response, on_complete),
            daemon=True
        ).start()

    def _should_process_memory(self, user_input):
        """Checks if the user input should trigger a memory update."""
        filler = {
            "thanks", "thank", "ok", "okay", "cool", "nice",
            "hello", "hi", "bye", "yes", "no", "yep", "nope"
        }
        clean_in = re.sub(r'[^a-zA-Z\s]', '', user_input).lower().strip()
        return len(clean_in.split()) >= 3 or (clean_in and clean_in not in filler)

    def _apply_memory_operations(self, ops, all_facts):
        """Applies a list of memory operations to the memory store."""
        updated = False
        for op in [o for o in ops if isinstance(o, dict)]:
            action = op.get('op')
            entity = op.get('entity')
            fact = op.get('fact', '').strip()
            f_id = op.get('id')

            if not entity:
                debug_print("[*] Memory: Skipping operation - missing entity.")
                continue

            try:
                if f_id is not None:
                    f_id = int(f_id)
            except (ValueError, TypeError):
                f_id = None

            # SAFETY: Force id to None for 'add' operations
            if action == 'add':
                f_id = None

            # Clean up ID markers if they leaked into the fact text
            fact = re.sub(r'\s*\[ID:\s*\d+\]$', '', fact).strip()
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
                    updated = True
            elif action == 'remove' and exists:
                self.memory.remove_fact(f_id)
                updated = True
            elif action == 'update' and exists and fact:
                self.memory.update_fact(f_id, entity, fact)
                updated = True
        return updated

    def perform_memory_update(self, user_input, assistant_response, on_complete=None):
        """Extracts and commits new facts to the memory store."""
        Profiler().start("Memory Update")
        debug_print("[*] Memory: Processing turn...")
        start_clear_count = self.memory.clear_count
        updated = False
        try:
            if self._should_process_memory(user_input):
                all_facts = self.memory.get_relevant_facts(user_input)
                fact_ctx = "\n".join(
                    [f"[ID: {f['id']}] {f['entity']}: {f['fact']}" for f in all_facts]
                )
                ops = MemoryManager.extract_facts(
                    user_input, assistant_response, fact_ctx
                )

                if self.memory.clear_count != start_clear_count:
                    debug_print("[*] Memory: Aborting update - memory was cleared.")
                    return

                updated = self._apply_memory_operations(ops, all_facts)

                if updated:
                    if self.memory.clear_count != start_clear_count:
                        debug_print("[*] Memory: Aborting commit - memory was cleared.")
                        return
                    self._cached_prompt = None
                    self.update_system_prompt(user_input)
        except (ollama.ResponseError, RuntimeError, ValueError) as exc:
            error_print(f"Memory background task error: {exc}")
        finally:
            debug_print(f"[*] Memory: Turn completed (updated={updated}).")
            Profiler().stop("Memory Update")
            if on_complete:
                on_complete()

    def _get_search_decision(self, user_input, facts=None):
        """Asks the model if a web search is needed."""
        now = datetime.now()
        recent_ctx = "\n".join(
            [f"{m['role']}: {m['content'][:500]}" for m in self.messages[-6:]]
        )
        rec_queries = (", ".join(self.search_state.recent_queries[-2:])
                       if self.search_state.recent_queries else "None")

        if facts is None:
            facts = self.memory.get_relevant_facts(user_input)

        fact_text = "\n".join([f"- {f['entity']}: {f['fact']}" for f in facts[:10]])

        system_msg = (
            "You are a skeptical Search Coordinator. Determine if external data "
            "is REQUIRED. Your priority is to fulfill explicit user requests.\n\n"
            "SEARCH REQUIRED IF:\n"
            "1. Real-time data needed (news, weather, prices, events).\n"
            "2. USER EXPLICITLY ASKS to search, look up, find, or check something live. "
            "YOU MUST OBEY THESE REQUESTS.\n"
            "3. You lack specific facts that cannot be derived.\n"
            "4. Query involves data from after 2020.\n\n"
            "DO NOT SEARCH IF:\n"
            "1. REDUNDANT: The exact same information was already found in 'RECENT SEARCHES' "
            "or 'SEARCH HISTORY'.\n"
            "2. ROLEPLAY/CREATIVE: Use internal knowledge for fictional contexts.\n"
            "3. CHAT/GREETINGS: Small talk or philosophy.\n"
            "4. GENERAL KNOWLEDGE: Static historical facts or science.\n"
            "5. CRISIS: User expresses a medical emergency or mental health crisis (depression, self-harm). "
            "The assistant MUST use internal Crisis Protocol instead.\n\n"
            "TYPES: 'news', 'weather', 'finance', 'roleplay', 'crisis', 'none'.\n\n"
            "FORMAT: JSON only. {\"action\": \"search\"|\"done\", \"query\": \"str\", "
            "\"symbol\": \"ticker|null\", \"type\": \"enum\"}"
        )
        user_msg = (
            f"Current Date: {now.strftime('%Y-%m-%d')}\n"
            f"Facts: {fact_text}\n"
            f"RECENT SEARCHES: {rec_queries}\n"
            f"SEARCH HISTORY: {recent_ctx}\n"
            f"User Input: {user_input}"
        )
        try:
            res = get_ollama_client().chat(
                model=config.MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg}
                ],
                format="json",
                options={"temperature": 0.0, "num_predict": 80}
            )
            response_text = res['message']['content'].strip()
            debug_print(f"[*] Search Decision Raw: {response_text}")
            return json.loads(response_text)
        except (ollama.ResponseError, AttributeError, json.JSONDecodeError) as exc:
            debug_print(f"[*] Search Decision Failed: {exc}")
            return {"action": "done", "type": "none"}

    def _auto_scrape(self, user_input, results, is_news):
        """Helper to automatically scrape sources for news and finance."""
        scraped_info, seen_urls = [], set()
        limit = 2 if is_news else 1
        for url in re.findall(r'Source: (https?://\S+)', results):
            if url not in seen_urls:
                debug_print(f"[*] Auto-scraping source: {url}")
                raw_text = SearchEngine.scrape_url(url)
                scraped_info.append(self._distill_information(user_input, url, raw_text))
                seen_urls.add(url)
            if len(scraped_info) >= limit:
                break
        return "".join(scraped_info)

    def _handle_scraping(self, user_input, results, recent_ctx, **flags):
        """Asks the model if any search results should be scraped."""
        Profiler().start("Search Scraping")
        try:
            is_news = flags.get('is_news')
            is_finance = flags.get('is_finance')
            if is_news or is_finance:
                return self._auto_scrape(user_input, results, is_news)

            system_scrape = (
                "Decide if scraping a URL is REQUIRED to fully answer the user.\n"
                "Policy: LAST RESORT. If the snippets provided are enough, DO NOT scrape.\n"
                "Return JSON: {\"action\": \"scrape\"|\"done\", \"url\": \"str\"}"
            )
            user_scrape = (f"USER: {user_input}\nSNIPPETS:\n{results}\n"
                           f"CONTEXT: {recent_ctx}")
            scrape_res = get_ollama_client().chat(
                model=config.MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_scrape},
                    {"role": "user", "content": user_scrape}
                ],
                format="json",
                options={"temperature": 0.0, "num_predict": 30}
            )
            data = json.loads(scrape_res['message']['content'].strip())
            if data.get("action") == "scrape":
                url = data.get("url")
                if url and url.startswith("http"):
                    raw_text = SearchEngine.scrape_url(url)
                    return self._distill_information(user_input, url, raw_text)
            return ""
        finally:
            Profiler().stop("Search Scraping")

    def _distill_information(self, user_input, url, raw_text):
        """Summarizes scraped content to keep it focused."""
        distill_prompt = (
            f"WHY WE SEARCHED: {user_input}\n\n"
            f"RAW CONTENT FROM {url}:\n{raw_text}\n\n"
            "TASK: Extract facts that help answer. BE CONCISE."
        )
        distill_res = get_ollama_client().generate(
            model=config.MODEL_NAME, prompt=distill_prompt,
            options={"temperature": 0.0, "num_predict": 200}
        )
        info = distill_res['response'].strip()
        return f"\n\n--- RELEVANT DATA FROM {url} ---\n{info}"

    def prepare_turn(self, user_input, skip_search=False):
        """Runs memory retrieval and search gatekeeper in parallel."""
        Profiler().reset()

        def _timed_memory(q):
            Profiler().start("Memory Lookup")
            res = self.memory.get_relevant_facts(q)
            Profiler().stop("Memory Lookup")
            return res

        def _timed_decision(q, f):
            Profiler().start("Search Decision")
            res = self._get_search_decision(q, facts=f)
            Profiler().stop("Search Decision")
            return res

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_mem = executor.submit(_timed_memory, user_input)
            facts = future_mem.result()

            decision_needed = False
            future_decision = None

            filler = {"hi", "hello", "hey", "thanks", "ok", "yes", "no"}
            clean_in = re.sub(r'[^a-z\s]', '', user_input.lower()).strip()
            if not (skip_search and clean_in in filler and len(user_input) < 10):
                decision_needed = True

            if decision_needed:
                future_decision = executor.submit(_timed_decision, user_input, facts)

            decision_data = future_decision.result() if future_decision else None

        search_context = None
        if decision_data and decision_data.get("action") == "search":
            search_context = self.decide_and_search(
                user_input, skip_llm=False,
                decision_data=decision_data, facts=facts
            )

        return {
            "facts": facts,
            "search_context": search_context,
            "search_type": decision_data.get("type", "none") if decision_data else "none"
        }

    def decide_and_search(self, user_input, skip_llm=False, decision_data=None, facts=None):
        """Determines if search is needed and executes it."""
        filler = {"hi", "hello", "hey", "thanks", "ok", "yes", "no"}
        clean_in = re.sub(r'[^a-z\s]', '', user_input.lower()).strip()
        if skip_llm and clean_in in filler and len(user_input) < 10:
            return None

        data = decision_data
        if data is None:
            data = self._get_search_decision(user_input, facts=facts)

        if data and data.get("action") == "search":
            if data.get("type") in ("roleplay", "crisis"):
                debug_print(f"[*] Search aborted: {data.get('type')} detected.")
                return None

            if self.search_state.on_start:
                self.search_state.on_start()
            try:
                res = self._perform_search(user_input, data)
                return res
            finally:
                if self.search_state.on_end:
                    self.search_state.on_end()
        return None

    def _perform_search(self, user_input, data):
        """Executes the search and optional scraping."""
        base_query = data.get("query", "").strip() or user_input

        if data.get("type") == "weather":
            base_query = SpecializedSearch.clean_weather_location(base_query)

        res = self._try_specialized_search(base_query, data)
        if res:
            return res

        Profiler().start("Search")
        if base_query not in self.search_state.recent_queries:
            self.search_state.recent_queries.append(base_query)

        wiki_res = None
        is_spec_no_wiki = data.get("type") in ("weather", "finance")

        if not is_spec_no_wiki:
            wiki_res = SearchEngine.wikipedia_search(base_query)

        if wiki_res:
            debug_print(f"[*] Wikipedia Hit: {base_query}")
            Profiler().stop("Search")
            return f"--- Wikipedia Result ---\n{wiki_res}"

        return self._perform_web_search(user_input, base_query, data)

    def _try_specialized_search(self, query, data):
        """Attempts specialized search."""
        res = None
        symbol = data.get("symbol")
        search_type = data.get("type")

        if search_type == "finance" and symbol and symbol.lower() != "null":
            Profiler().start("Search")
            res = SpecializedSearch.get_ticker_data(symbol)
            Profiler().stop("Search")
        elif search_type == "weather":
            Profiler().start("Search")
            res = SpecializedSearch.get_weather(query)
            Profiler().stop("Search")
        elif search_type == "news":
            res = self._handle_news_search(query)
        return res

    def _handle_news_search(self, query):
        """Handles news search with generic query cleaning."""
        q_lower = query.lower().strip()
        general_patterns = [
            "news", "headlines", "top stories", "latest news", "world news",
            "breaking news", "general news", "news today", "top headlines",
            "current news", "today's news", "today's headlines"
        ]
        is_general = (not q_lower or
                      any(p == q_lower for p in general_patterns) or
                      q_lower in ["top", "stories", "latest"])

        news_query = None if is_general else query
        if news_query:
            news_query = re.sub(
                r'^(news about|latest news on|headlines for|news on)\s+',
                '', news_query, flags=re.I
            )

        Profiler().start("Search")
        res = SpecializedSearch.get_news(news_query)
        Profiler().stop("Search")
        return res

    def _perform_web_search(self, user_input, base_query, data):
        """Executes standard web search pipeline."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        symbol = data.get("symbol")
        search_type = data.get("type")

        if search_type == "weather":
            query = f"weather in {base_query} {date_str}"
        elif search_type == "finance" and symbol and symbol.lower() != "null":
            query = f"{symbol} stock price {date_str}"
        else:
            query = f"{base_query} {date_str}"

        if query in self.search_state.session_cache:
            debug_print(f"[*] Search Cache Hit: {query}")
            Profiler().stop("Search")
            return self.search_state.session_cache[query]

        results = SearchEngine.web_search(query)
        Profiler().stop("Search")
        recent_ctx = "\n".join(
            [f"{m['role']}: {m['content'][:500]}" for m in self.messages[-3:]]
        )
        try:
            extra = self._handle_scraping(
                user_input, results, recent_ctx,
                flags={"is_news": search_type == "news",
                       "is_finance": search_type == "finance"}
            )
            full_res = f"--- Search for '{query}' ---\n{results}{extra}"
        except (ollama.ResponseError, json.JSONDecodeError):
            full_res = f"--- Search for '{query}' ---\n{results}"

        self.search_state.session_cache[query] = full_res
        return full_res

    def clear_conversation(self):
        """Resets short-term conversation history and search cache."""
        self.messages = []
        self.search_state.recent_queries = []
        self.search_state.session_cache = {}
        debug_print("[*] Conversation history and search cache cleared.")

    def clear_long_term_memory(self):
        """Resets internal long-term memory."""
        self.memory.clear()
        self.update_system_prompt()
        self.search_state.recent_queries = []
        info_print("Long-term memory cleared.")

    def get_model_info(self):
        """Returns current model and system usage stats."""
        return get_model_info(
            self.memory, self.system_prompt, self.messages
        )

    def get_available_models(self):
        """Retrieves a list of available models from Ollama."""
        try:
            models_res = get_ollama_client().list()
            return [m.model for m in models_res.models]
        except (ollama.ResponseError, AttributeError, ConnectionError) as exc:
            error_print(f"Failed to list models: {exc}")
            return []

    def switch_model(self, new_model_name):
        """Switches current model and clears short-term memory."""
        info_print(f"[*] Switching model to: {new_model_name}")
        config.MODEL_NAME = new_model_name
        self.clear_conversation()
        return True

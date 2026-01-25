"""
Search engine integration for Lokality.
Handles web searching via DuckDuckGo and URL scraping.
"""
import time
import trafilatura
import wikipedia
try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        # Fallback for environments where neither is found during type checking/linting
        DDGS = None

from logger import logger
from utils import debug_print

class SearchEngine:
    """
    Provides methods for web search and content scraping.
    """
    @staticmethod
    def scrape_url(url):
        """Fetches a URL and extracts clean, readable text using Trafilatura."""
        start_time = time.time()
        logger.info("Scraping URL: %s", url)
        debug_print(f"[*] Scraping: {url}")
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded is None:
                raise ValueError("Failed to fetch content (empty response)")

            clean_text = trafilatura.extract(downloaded)
            if not clean_text:
                raise ValueError("Failed to extract text from content")

            duration = time.time() - start_time
            logger.info("Scraping finished in %.2fs. Length: %d chars",
                        duration, len(clean_text))

            # Limit to a reasonable amount of text for the LLM context
            return clean_text[:8000]

        except (ValueError, RuntimeError, ConnectionError) as exc:
            duration = time.time() - start_time
            logger.error("Scraping Error for '%s' after %.2fs: %s",
                         url, duration, exc)
            return f"Failed to scrape URL '{url}': {exc}"

    @staticmethod
    def wikipedia_search(query):
        """
        Performs a Wikipedia search and returns a summary.
        """
        start_time = time.time()
        logger.info("Wikipedia Search: %s", query)
        debug_print(f"[*] Wikipedia Search: {query}")
        try:
            # Try to get a specific page match first
            search_results = wikipedia.search(query, results=1)
            if not search_results:
                return None

            page = wikipedia.page(search_results[0], auto_suggest=False)
            duration = time.time() - start_time
            logger.info("Wikipedia: Found '%s' in %.2fs.", page.title, duration)

            return (
                f"Source: {page.url}\n"
                f"Title: {page.title}\n"
                f"Summary: {page.summary[:2000]}"
            )
        except (wikipedia.exceptions.DisambiguationError,
                wikipedia.exceptions.PageError,
                RuntimeError) as exc:
            debug_print(f"[*] Wikipedia search failed for '{query}': {exc}")
            return None

    @staticmethod
    def web_search(query):
        """Performs a DuckDuckGo search and returns the top results."""
        start_time = time.time()
        logger.info("Web Search: %s", query)
        debug_print(f"[*] Searching for: {query}")
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=8))
                duration = time.time() - start_time

                if not results:
                    logger.info("Web Search: No results found (took %.2fs).", duration)
                    return "No recent web results found."

                logger.info("Web Search: Found %d results in %.2fs.",
                            len(results), duration)
                formatted = []
                for i, res in enumerate(results, 1):
                    # Log the source URLs at DEBUG level to avoid log bloat
                    logger.debug("Search Result %d: %s", i, res.get('href'))
                    formatted.append(f"Source: {res['href']}\nSnippet: {res['body']}")
                return "\n\n".join(formatted)
        except (ValueError, RuntimeError, ConnectionError) as exc:
            duration = time.time() - start_time
            logger.error("Search Error for '%s' after %.2fs: %s", query, duration, exc)
            # Differentiate between no results and connection errors
            msg = str(exc).lower()
            if any(key in msg for key in ["connection", "timeout", "refused"]):
                return (
                    "CRITICAL: Web search failed due to a connectivity issue "
                    "(Internet might be down). You MUST inform the user you "
                    "cannot check real-time data right now."
                )
            return f"Search failed for query '{query}': {exc}"

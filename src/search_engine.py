from ddgs import DDGS

from logger import logger
from utils import debug_print

class SearchEngine:
    @staticmethod
    def web_search(query):
        """Performs a DuckDuckGo search and returns the top results."""
        logger.info(f"Web Search: {query}")
        debug_print(f"[*] Searching for: {query}")
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
                if not results:
                    logger.info("Web Search: No results found.")
                    return "No recent web results found."
                
                logger.info(f"Web Search: Found {len(results)} results.")
                formatted = []
                for i, r in enumerate(results, 1):
                    # Log the source URLs at DEBUG level to avoid log bloat
                    logger.debug(f"Search Result {i}: {r.get('href')}")
                    formatted.append(f"Source: {r['href']}\nSnippet: {r['body']}")
                return "\n\n".join(formatted)
        except Exception as e:
            logger.error(f"Search Error for '{query}': {e}")
            # Differentiate between no results and connection errors
            if "connection" in str(e).lower() or "timeout" in str(e).lower() or "refused" in str(e).lower():
                return f"CRITICAL: Web search failed due to a connectivity issue (Internet might be down). You MUST inform the user you cannot check real-time data right now."
            return f"Search failed for query '{query}': {e}"

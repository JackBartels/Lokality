"""
Search engine integration for Lokality.
Handles web searching via DuckDuckGo and URL scraping.
"""
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

from logger import logger
from utils import debug_print

class SearchEngine:
    """
    Provides methods for web search and content scraping.
    """
    @staticmethod
    def scrape_url(url):
        """Fetches a URL and extracts clean, readable text."""
        logger.info("Scraping URL: %s", url)
        debug_print(f"[*] Scraping: {url}")
        try:
            ua = (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/91.0.4472.124 Safari/537.36'
            )
            headers = {'User-Agent': ua}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Remove script and style elements
            for script_or_style in soup(["script", "style", "header", "footer", "nav"]):
                script_or_style.decompose()

            # Get text and clean up whitespace
            text = soup.get_text(separator=' ')
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = '\n'.join(chunk for chunk in chunks if chunk)

            # Limit to a reasonable amount of text for the LLM context
            return clean_text[:8000]

        except (requests.RequestException, ValueError) as e:
            logger.error("Scraping Error for '%s': %s", url, e)
            return f"Failed to scrape URL '{url}': {e}"

    @staticmethod
    def web_search(query):
        """Performs a DuckDuckGo search and returns the top results."""
        logger.info("Web Search: %s", query)
        debug_print(f"[*] Searching for: {query}")
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
                if not results:
                    logger.info("Web Search: No results found.")
                    return "No recent web results found."

                logger.info("Web Search: Found %d results.", len(results))
                formatted = []
                for i, r in enumerate(results, 1):
                    # Log the source URLs at DEBUG level to avoid log bloat
                    logger.debug("Search Result %d: %s", i, r.get('href'))
                    formatted.append(f"Source: {r['href']}\nSnippet: {r['body']}")
                return "\n\n".join(formatted)
        except (requests.RequestException, ValueError, RuntimeError) as e:
            logger.error("Search Error for '%s': %s", query, e)
            # Differentiate between no results and connection errors
            msg = str(e).lower()
            if any(k in msg for k in ["connection", "timeout", "refused"]):
                return (
                    "CRITICAL: Web search failed due to a connectivity issue "
                    "(Internet might be down). You MUST inform the user you "
                    "cannot check real-time data right now."
                )
            return f"Search failed for query '{query}': {e}"

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

from logger import logger
from utils import debug_print

class SearchEngine:
    @staticmethod
    def scrape_url(url):
        """Fetches a URL and extracts clean, readable text."""
        logger.info(f"Scraping URL: {url}")
        debug_print(f"[*] Scraping: {url}")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
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
            
        except Exception as e:
            logger.error(f"Scraping Error for '{url}': {e}")
            return f"Failed to scrape URL '{url}': {e}"

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

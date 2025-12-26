from ddgs import DDGS
from utils import debug_print

class SearchEngine:
    @staticmethod
    def web_search(query):
        """Performs a DuckDuckGo search and returns the top results."""
        debug_print(f"[*] Searching for: {query}")
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
                if not results:
                    return "No recent web results found."
                
                formatted = []
                for i, r in enumerate(results, 1):
                    formatted.append(f"Source: {r['href']}\nSnippet: {r['body']}")
                return "\n\n".join(formatted)
        except Exception as e:
            return f"Error during search: {e}"

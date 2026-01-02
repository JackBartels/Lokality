"""
Debug script for testing search functionality manually.
"""
from search_engine import SearchEngine

def test_query(query_text):
    """Run a test query and print results."""
    print(f"\n--- Testing Search for: '{query_text}' ---")
    results = SearchEngine.web_search(query_text)
    print(results)

if __name__ == "__main__":
    queries = [
        "current president of the United States 2025",
        "who was the president of the USA in 1995",
        "latest stock price of NVIDIA",
        "current weather in Tokyo",
        "who won the latest formula 1 race"
    ]
    for q in queries:
        test_query(q)

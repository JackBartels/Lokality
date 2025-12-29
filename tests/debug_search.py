import sys
import os

# Ensure src is in path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from search_engine import SearchEngine

def test_query(query):
    print(f"\n--- Testing Search for: '{query}' ---")
    results = SearchEngine.web_search(query)
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

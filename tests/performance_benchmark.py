import time
import sys
import os
import hashlib

# Ensure src is in path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from local_assistant import LocalChatAssistant
from complexity_scorer import ComplexityScorer
import local_assistant

def benchmark_prompt(assistant, text):
    print(f"\n--- BENCHMARKING: '{text}' ---")
    
    # 1. Scoring Time (App Side)
    start = time.time()
    complexity = ComplexityScorer.analyze(text)
    scoring_time = time.time() - start
    
    p = complexity['params']
    level = complexity['level']
    print(f"[*] Level: {level} (Score: {complexity['score']}, Creativity: {complexity['creativity']})")
    print(f"[*] App Side (Scoring): {scoring_time:.4f}s")

    # 2. Search Decision (Model Side - may be skipped)
    skip_search_llm = level == ComplexityScorer.LEVEL_MINIMAL
    start = time.time()
    search_context = assistant.decide_and_search(text, skip_llm=skip_search_llm)
    search_decision_time = time.time() - start
    
    if skip_search_llm:
        print(f"[*] Search Decision: SKIPPED (Heuristic)")
    else:
        print(f"[*] Model Side (Search Decision): {search_decision_time:.4f}s")
    
    if search_context:
        print(f"[*] Web Search Performed: YES")

    # 3. Final Chat Generation (Model Side)
    assistant._update_system_prompt(text)
    msgs = [{"role": "system", "content": assistant.system_prompt}] + assistant.messages
    if search_context:
        msgs.append({"role": "system", "content": f"### SEARCH RESULTS:\n{search_context}"})
    msgs.append({"role": "user", "content": text})

    start = time.time()
    # We measure first token and total time
    first_token_time = 0
    full_response = ""
    
    try:
        stream = local_assistant.client.chat(
            model=local_assistant.MODEL_NAME, 
            messages=msgs, 
            stream=True,
            options=p
        )
        for chunk in stream:
            if not first_token_time:
                first_token_time = time.time() - start
            full_response += chunk['message']['content']
    except Exception as e:
        print(f"[!] Generation Failed: {e}")
        return

    total_gen_time = time.time() - start
    print(f"[*] Model Side (TTFT - First Token): {first_token_time:.4f}s")
    print(f"[*] Model Side (Total Generation): {total_gen_time:.4f}s")
    print(f"[*] Total Round Trip: {scoring_time + search_decision_time + total_gen_time:.4f}s")
    print(f"[*] Response Length: {len(full_response)} chars")

if __name__ == "__main__":
    try:
        assistant = LocalChatAssistant()
        print(f"Benchmarking with model: {local_assistant.MODEL_NAME}")
        
        prompts = [
            "Hi",                                       # MINIMAL (Skip search LLM)
            "What is 2+2?",                             # SIMPLE (Run search LLM)
            "Write a short story about a neon cat.",    # CREATIVE (High sampling)
            "Analyze the following code for bugs: \n```python\ndef add(a,b): return a+c\n```"
        ] # COMPLEX
        
        for p in prompts:
            benchmark_prompt(assistant, p)
            
    except Exception as e:
        print(f"Benchmark setup failed: {e}")
        print("Ensure Ollama is running.")

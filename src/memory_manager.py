import json
import re
import ast
from config import MODEL_NAME, DEBUG
import ollama

client = ollama.Client()

class MemoryManager:
    @staticmethod
    def extract_facts(user_input, assistant_response, current_memory_text):
        """Delta-based memory update using structured operations."""
        system_instructions = (
            "You are a memory management module. Your job is to Extract and Record permanent facts (names, locations, jobs, pets, preferences, identity) from the conversation. "
            "If the User shares something personal, you MUST record it. "
            "Output ONLY a JSON list of objects. Example: [{'op': 'add', 'entity': 'The User', 'fact': 'Lives in New York'}]"
        )
        
        user_prompt = (
            f"### CURRENT MEMORY:\n{current_memory_text}\n\n"
            f"### NEW CONVERSATION TURN:\nUser: {user_input}\nAssistant: {assistant_response}\n\n"
            "Task: Did the user share something new about themselves? Did you receive a name or persona? "
            "Suggest ADD, REMOVE, or UPDATE operations in JSON format. Use 'The User' or 'The Assistant' or a specific name as the entity. "
            "If absolutely nothing permanent was learned, return []."
        )

        try:
            res = client.chat(model=MODEL_NAME, messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": user_prompt}
            ])
            response_text = res['message']['content'].strip()
            
            # Robust JSON extraction
            match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if match:
                content = match.group()
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    try:
                        return ast.literal_eval(content)
                    except (ValueError, SyntaxError) as e:
                        print(f"\033[91m[*] Memory Parse Failed: {e} | Content: {content}\033[0m")
        except Exception as e:
            print(f"\033[91m[*] Memory Update System Error: {e}\033[0m")
            
        return []

from config import MODEL_NAME
import ollama

client = ollama.Client()

class StatsCollector:
    @staticmethod
    def get_model_info(memory_store, system_prompt, messages):
        """Gathers statistics about the model and system."""
        stats = {
            "model": MODEL_NAME,
            "context_pct": 0,
            "memory_entries": memory_store.get_fact_count(),
            "ram_mb": 0,
            "vram_mb": 0
        }
        
        try:
            # Get VRAM/RAM info
            ps = client.ps()
            for m in ps.models:
                if m.model.split(":")[0] in MODEL_NAME or MODEL_NAME in m.model:
                    vram_bytes = getattr(m, 'size_vram', 0)
                    total_bytes = getattr(m, 'size', 0)
                    stats["vram_mb"] = vram_bytes // (1024 * 1024)
                    stats["ram_mb"] = max(0, (total_bytes - vram_bytes) // (1024 * 1024))
                    break
            
            # Context estimation
            show = client.show(MODEL_NAME)
            show_dict = show.model_dump()
            max_ctx = 8192 # Default fallback
            model_info = show_dict.get('modelinfo', {})
            for key, val in model_info.items():
                if 'context_length' in key:
                    max_ctx = val
                    break
            
            total_chars = len(system_prompt)
            for msg in messages:
                total_chars += len(msg['content'])
            
            estimated_tokens = total_chars // 3 # Heuristic
            stats["context_pct"] = min(100, (estimated_tokens / max_ctx) * 100)
            
        except Exception as e:
            print(f"Error gathering info: {e}")
            
        return stats

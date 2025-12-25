import sqlite3
import os
import re

class MemoryStore:
    def __init__(self, db_path="res/memory.db"):
        self.db_path = db_path
        # Ensure res directory exists just in case
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity TEXT,
                    fact TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entity ON memory(entity)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON memory(created_at)")
            conn.commit()

    def _get_conn(self):
        return sqlite3.connect(self.db_path, timeout=10)

    def get_all_facts(self):
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT entity, fact, id FROM memory ORDER BY entity, created_at")
            return [f"- {r[0]}: {r[1]} (ID: {r[2]})" for r in cursor.fetchall()]

    def get_relevant_facts(self, query):
        all_facts = []
        with self._get_conn() as conn:
            # 1. ALWAYS include Assistant identity/nickname
            assistant_cursor = conn.execute("SELECT entity, fact, id FROM memory WHERE entity LIKE '%Assistant%' OR entity LIKE '%Bot%'")
            all_facts.extend([f"- {r[0]}: {r[1]}" for r in assistant_cursor.fetchall()])

            # 2. Get most recent facts (Recency Buffer - Increased to 10)
            recent_cursor = conn.execute("SELECT entity, fact, id FROM memory ORDER BY created_at DESC LIMIT 10")
            all_facts.extend([f"- {r[0]}: {r[1]}" for r in recent_cursor.fetchall()])

            # 3. Contextual Keyword Search
            if query:
                clean_query = re.sub(r'[^a-zA-Z0-9\s]', '', query).lower()
                keywords = [k.strip() for k in clean_query.split() if len(k) >= 3]
                
                if any(k in ["i", "me", "my", "mine", "who", "am"] for k in query.lower().split()):
                    keywords.append("user")

                if keywords:
                    search_clause = " OR ".join(["fact LIKE ? OR entity LIKE ?" for _ in keywords])
                    params = []
                    for k in keywords:
                        params.extend([f"%{k}%", f"%{k}%"])
                    
                    cursor = conn.execute(f"SELECT entity, fact, id FROM memory WHERE {search_clause} ORDER BY created_at DESC LIMIT 15", params)
                    all_facts.extend([f"- {r[0]}: {r[1]}" for r in cursor.fetchall()])

        # Deduplicate while preserving order
        seen = set()
        unique_facts = []
        for f in all_facts:
            if f not in seen:
                unique_facts.append(f)
                seen.add(f)
                
        return unique_facts[:25] # Slightly larger limit

    def add_fact(self, entity, fact):
        with self._get_conn() as conn:
            conn.execute("INSERT INTO memory (entity, fact) VALUES (?, ?)", (entity, fact))
            conn.commit()

    def remove_fact(self, fact_id):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM memory WHERE id = ?", (fact_id,))
            conn.commit()

    def update_fact(self, fact_id, entity, fact):
        with self._get_conn() as conn:
            conn.execute("UPDATE memory SET entity = ?, fact = ? WHERE id = ?", (entity, fact, fact_id))
            conn.commit()

    def clear(self):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM memory")
            conn.commit()

    def get_fact_count(self):
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM memory")
            return cursor.fetchone()[0]

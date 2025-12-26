import sqlite3
import os
import re
import threading

class MemoryStore:
    def __init__(self, db_path=None):
        if db_path is None:
            # Use absolute path based on project root
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.db_path = os.path.join(base_dir, "res", "memory.db")
        else:
            self.db_path = db_path
            
        # Ensure res directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = None
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        try:
            with self._get_conn() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA cache_size=-2000") # 2MB cache
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS memory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        entity TEXT,
                        fact TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # FTS5 Virtual Table for optimized keyword search
                try:
                    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(entity, fact, content='memory', content_rowid='id')")
                    
                    # Triggers to keep FTS in sync with main table
                    conn.execute("""
                        CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memory BEGIN
                            INSERT INTO memory_fts(rowid, entity, fact) VALUES (new.id, new.entity, new.fact);
                        END;
                    """)
                    conn.execute("""
                        CREATE TRIGGER IF NOT EXISTS mem_ad AFTER DELETE ON memory BEGIN
                            INSERT INTO memory_fts(memory_fts, rowid, entity, fact) VALUES('delete', old.id, old.entity, old.fact);
                        END;
                    """)
                    conn.execute("""
                        CREATE TRIGGER IF NOT EXISTS mem_au AFTER UPDATE ON memory BEGIN
                            INSERT INTO memory_fts(memory_fts, rowid, entity, fact) VALUES('delete', old.id, old.entity, old.fact);
                            INSERT INTO memory_fts(rowid, entity, fact) VALUES (new.id, new.entity, new.fact);
                        END;
                    """)
                    
                    # BACKFILL: Ensure existing rows are in FTS (if we just created the table)
                    conn.execute("INSERT OR IGNORE INTO memory_fts(rowid, entity, fact) SELECT id, entity, fact FROM memory")
                    
                except sqlite3.OperationalError:
                    pass # FTS5 unavailable or other minor error
                    
                conn.execute("CREATE INDEX IF NOT EXISTS idx_entity ON memory(entity)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON memory(created_at)")
                conn.commit()
        except sqlite3.Error as e:
            print(f"\033[91m[*] Memory: Database error during init: {e}. Resetting...\033[0m")
            self._reset_corrupted_db()

    def _get_conn(self):
        with self._lock:
            if self._conn is None:
                self._conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
            return self._conn

    def close(self):
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    def get_all_facts(self):
        try:
            conn = self._get_conn()
            with self._lock:
                cursor = conn.execute("SELECT entity, fact, id FROM memory ORDER BY entity, created_at")
                return [{"id": r['id'], "entity": r['entity'], "fact": r['fact']} for r in cursor.fetchall()]
        except sqlite3.Error:
            return []

    def get_relevant_facts(self, query):
        all_facts = []
        try:
            conn = self._get_conn()
            with self._lock:
                # 1. ALWAYS include Assistant identity
                cursor = conn.execute("""
                    SELECT entity, fact, id FROM memory 
                    WHERE entity IN ('The Assistant', 'Lokality', 'Assistant') 
                    ORDER BY created_at DESC LIMIT 5
                """)
                for r in cursor.fetchall():
                    all_facts.append({"id": r['id'], "entity": r['entity'], "fact": r['fact']})

                # 2. Get most recent facts
                recent_cursor = conn.execute("SELECT entity, fact, id FROM memory ORDER BY created_at DESC LIMIT 3")
                for r in recent_cursor.fetchall():
                    all_facts.append({"id": r['id'], "entity": r['entity'], "fact": r['fact']})

                # 3. Contextual Keyword Search
                if query:
                    stop_words = {"the", "and", "you", "that", "was", "for", "are", "with", "his", "they", "this", "have", "from"}
                    clean_query = re.sub(r'[^a-zA-Z0-9\s]', '', query).lower()
                    keywords = [k.strip() for k in clean_query.split() if len(k) >= 3 and k not in stop_words]
                    
                    if any(k in ["i", "me", "my", "mine", "who", "am"] for k in query.lower().split()):
                        keywords.append("user")

                    if keywords:
                        try:
                            # Use FTS5 MATCH for instant retrieval
                            fts_query = " OR ".join(keywords)
                            cursor = conn.execute("""
                                SELECT entity, fact, id FROM memory_fts 
                                WHERE memory_fts MATCH ? 
                                ORDER BY rank LIMIT 10
                            """, (fts_query,))
                            for r in cursor.fetchall():
                                all_facts.append({"id": r['id'], "entity": r['entity'], "fact": r['fact']})
                        except:
                            # Fallback to LIKE
                            search_clause = " OR ".join(["fact LIKE ? OR entity LIKE ?" for _ in keywords])
                            params = []
                            for k in keywords: params.extend([f"%{k}%", f"%{k}%"])
                            cursor = conn.execute(f"SELECT entity, fact, id FROM memory WHERE {search_clause} ORDER BY created_at DESC LIMIT 10", params)
                            for r in cursor.fetchall():
                                all_facts.append({"id": r['id'], "entity": r['entity'], "fact": r['fact']})
        except sqlite3.Error as e:
            print(f"\033[91m[*] Memory: Runtime error: {e}\033[0m")
            return []

        # Deduplicate while preserving order
        seen = set()
        unique_facts = []
        for f in all_facts:
            norm = (f['entity'].lower(), f['fact'].lower())
            if norm not in seen:
                unique_facts.append(f)
                seen.add(norm)
                
        return unique_facts[:20]

    def is_name_fact(self, fact_id):
        """Efficiently checks if a fact ID refers to a name or nickname. O(log n)"""
        try:
            conn = self._get_conn()
            with self._lock:
                cursor = conn.execute("SELECT fact FROM memory WHERE id = ?", (fact_id,))
                row = cursor.fetchone()
                if row:
                    fact_lower = row['fact'].lower()
                    return "name" in fact_lower or "nickname" in fact_lower
        except sqlite3.Error:
            pass
        return False

    def add_fact(self, entity, fact):
        conn = self._get_conn()
        with self._lock:
            conn.execute("INSERT INTO memory (entity, fact) VALUES (?, ?)", (entity, fact))
            conn.commit()

    def remove_fact(self, fact_id):
        conn = self._get_conn()
        with self._lock:
            conn.execute("DELETE FROM memory WHERE id = ?", (fact_id,))
            conn.commit()

    def update_fact(self, fact_id, entity, fact):
        conn = self._get_conn()
        with self._lock:
            conn.execute("UPDATE memory SET entity = ?, fact = ? WHERE id = ?", (entity, fact, fact_id))
            conn.commit()

    def clear(self):
        """Deletes the database file entirely (including WAL/SHM) and re-initializes it."""
        self.close()
        try:
            # We must close any active connections if we were keeping them, 
            # but since we use context managers for every call, we just need to delete files.
            for ext in ["", "-wal", "-shm"]:
                path = self.db_path + ext
                if os.path.exists(path):
                    os.remove(path)
            print(f"[*] Memory: Database files cleared.")
        except Exception as e:
            print(f"[*] Memory: Failed to delete database files: {e}")
            # Fallback: at least try to clear the main table
            try:
                conn = self._get_conn()
                with self._lock:
                    conn.execute("DELETE FROM memory")
                    conn.commit()
            except:
                pass
        
        self._init_db()

    def get_fact_count(self):
        try:
            conn = self._get_conn()
            with self._lock:
                cursor = conn.execute("SELECT COUNT(*) FROM memory")
                return cursor.fetchone()[0]
        except sqlite3.Error:
            return 0

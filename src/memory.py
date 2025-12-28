import sqlite3
import os
import re
import threading
import time
from utils import debug_print, error_print

def retry_on_busy(max_retries=5, delay=0.1):
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exc = None
            for i in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e).lower() or "busy" in str(e).lower():
                        last_exc = e
                        time.sleep(delay * (i + 1))
                        continue
                    raise
            raise last_exc
        return wrapper
    return decorator

class MemoryStore:
    def __init__(self, db_path=None):
        if db_path is None:
            # Use absolute path based on project root
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.db_path = os.path.join(base_dir, "res", "memory.db")
        else:
            self.db_path = db_path
            
        # Ensure res directory exists (skip for in-memory DB)
        if self.db_path != ":memory:":
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                try:
                    os.makedirs(db_dir, exist_ok=True)
                except Exception as e:
                    debug_print(f"[*] Memory: Failed to create database directory: {e}")
        
        self._conn = None
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        try:
            with self._get_conn() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA cache_size=-2000")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS memory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        entity TEXT, fact TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                try:
                    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(entity, fact, content='memory', content_rowid='id')")
                    # Triggers to keep FTS in sync
                    conn.executescript("""
                        CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memory BEGIN
                            INSERT INTO memory_fts(rowid, entity, fact) VALUES (new.id, new.entity, new.fact);
                        END;
                        CREATE TRIGGER IF NOT EXISTS mem_ad AFTER DELETE ON memory BEGIN
                            INSERT INTO memory_fts(memory_fts, rowid, entity, fact) VALUES('delete', old.id, old.entity, old.fact);
                        END;
                        CREATE TRIGGER IF NOT EXISTS mem_au AFTER UPDATE ON memory BEGIN
                            INSERT INTO memory_fts(memory_fts, rowid, entity, fact) VALUES('delete', old.id, old.entity, old.fact);
                            INSERT INTO memory_fts(rowid, entity, fact) VALUES (new.id, new.entity, new.fact);
                        END;
                    """)
                    conn.execute("INSERT OR IGNORE INTO memory_fts(rowid, entity, fact) SELECT id, entity, fact FROM memory")
                except sqlite3.OperationalError: pass
                    
                conn.execute("CREATE INDEX IF NOT EXISTS idx_entity ON memory(entity)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON memory(created_at)")
                conn.commit()
        except sqlite3.Error as e:
            debug_print(f"[*] Memory: Database error: {e}. Resetting...")
            self._reset_corrupted_db()

    def _reset_corrupted_db(self):
        """Attempts to fix a corrupted database by renaming it and creating a new one."""
        try:
            self.close()
            if os.path.exists(self.db_path):
                bak_path = f"{self.db_path}.{int(time.time())}.bak"
                os.rename(self.db_path, bak_path)
                error_print(f"Database corruption detected. Original moved to {bak_path}")
            self._init_db()
        except Exception as e:
            debug_print(f"[*] Memory: CRITICAL: Could not reset database: {e}")

    def _get_conn(self):
        with self._lock:
            if self._conn is None:
                self._conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
            return self._conn

    def close(self):
        with self._lock:
            if self._conn:
                try: self._conn.close()
                except: pass
                self._conn = None

    @retry_on_busy()
    def get_all_facts(self):
        try:
            cursor = self._get_conn().execute("SELECT entity, fact, id FROM memory ORDER BY entity, created_at")
            return [{"id": r['id'], "entity": r['entity'], "fact": r['fact']} for r in cursor.fetchall()]
        except sqlite3.Error as e:
            debug_print(f"[*] Memory: Failed to fetch all facts: {e}")
            return []

    @retry_on_busy()
    def get_relevant_facts(self, query):
        all_facts = []
        try:
            conn = self._get_conn()
            # 1. ALWAYS include Assistant identity & most recent
            cursor = conn.execute("""
                SELECT entity, fact, id FROM memory 
                WHERE entity IN ('The Assistant', 'Lokality', 'Assistant') 
                OR id IN (SELECT id FROM memory ORDER BY created_at DESC LIMIT 3)
                ORDER BY created_at DESC LIMIT 8
            """)
            all_facts.extend([{"id": r['id'], "entity": r['entity'], "fact": r['fact']} for r in cursor.fetchall()])

            # 2. Contextual Keyword Search
            if query:
                stop_words = {"the", "and", "you", "that", "was", "for", "are", "with", "his", "they", "this", "have", "from"}
                clean_q = re.sub(r'[^a-z0-9\s]', '', query.lower())
                keywords = [k for k in clean_q.split() if len(k) >= 3 and k not in stop_words]
                if any(k in ["i", "me", "my", "mine", "who", "am"] for k in query.lower().split()): keywords.append("user")

                if keywords:
                    try:
                        cursor = conn.execute("SELECT entity, fact, id FROM memory_fts WHERE memory_fts MATCH ? ORDER BY rank LIMIT 10", (" OR ".join(keywords),))
                    except:
                        clause = " OR ".join(["fact LIKE ? OR entity LIKE ?" for _ in keywords])
                        params = [f"%{k}%" for k in keywords for _ in (0,1)]
                        cursor = conn.execute(f"SELECT entity, fact, id FROM memory WHERE {clause} ORDER BY created_at DESC LIMIT 10", params)
                    all_facts.extend([{"id": r['id'], "entity": r['entity'], "fact": r['fact']} for r in cursor.fetchall()])
        except sqlite3.Error as e:
            debug_print(f"[*] Memory: Error retrieving facts: {e}")

        seen, unique = set(), []
        for f in all_facts:
            if (f['entity'].lower(), f['fact'].lower()) not in seen:
                unique.append(f); seen.add((f['entity'].lower(), f['fact'].lower()))
        return unique[:20]

    @retry_on_busy()
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
        except sqlite3.Error as e:
            debug_print(f"[*] Memory: Error checking name fact: {e}")
        return False

    @retry_on_busy()
    def add_fact(self, entity, fact):
        try:
            conn = self._get_conn()
            with self._lock:
                conn.execute("INSERT INTO memory (entity, fact) VALUES (?, ?)", (entity, fact))
                conn.commit()
        except sqlite3.Error as e:
            debug_print(f"[*] Memory: Failed to add fact: {e}")

    @retry_on_busy()
    def remove_fact(self, fact_id):
        try:
            conn = self._get_conn()
            with self._lock:
                conn.execute("DELETE FROM memory WHERE id = ?", (fact_id,))
                conn.commit()
        except sqlite3.Error as e:
            debug_print(f"[*] Memory: Failed to remove fact: {e}")

    @retry_on_busy()
    def update_fact(self, fact_id, entity, fact):
        try:
            conn = self._get_conn()
            with self._lock:
                conn.execute("UPDATE memory SET entity = ?, fact = ? WHERE id = ?", (entity, fact, fact_id))
                conn.commit()
        except sqlite3.Error as e:
            debug_print(f"[*] Memory: Failed to update fact: {e}")

    def clear(self):
        """Deletes the database file entirely (including WAL/SHM) and re-initializes it."""
        try:
            self.close()
            for ext in ["", "-wal", "-shm"]:
                path = self.db_path + ext
                if os.path.exists(path):
                    os.remove(path)
            debug_print(f"[*] Memory: Database files cleared.")
        except Exception as e:
            debug_print(f"[*] Memory: Failed to delete database files: {e}")
            # Fallback: at least try to clear the main table
            try:
                conn = self._get_conn()
                with self._lock:
                    conn.execute("DELETE FROM memory")
                    conn.commit()
            except:
                pass
        
        self._init_db()

    @retry_on_busy()
    def get_fact_count(self):
        try:
            conn = self._get_conn()
            with self._lock:
                cursor = conn.execute("SELECT COUNT(*) FROM memory")
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            debug_print(f"[*] Memory: Error counting facts: {e}")
            return 0

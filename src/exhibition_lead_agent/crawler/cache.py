import os
import hashlib
import sqlite3
from typing import Optional, Tuple

class DiskCache:
    def __init__(self, cache_db: str = ".crawl_cache.db"):
        self.cache_db = cache_db
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.cache_db)
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS http_cache (
                    url_hash TEXT PRIMARY KEY,
                    url TEXT,
                    status_code INTEGER,
                    content BLOB,
                    headers_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.close()

    def _hash_url(self, url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def get(self, url: str) -> Optional[Tuple[int, bytes]]:
        url_hash = self._hash_url(url)
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()
        cursor.execute("SELECT status_code, content FROM http_cache WHERE url_hash = ?", (url_hash,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0], row[1]
        return None

    def set(self, url: str, status_code: int, content: bytes):
        url_hash = self._hash_url(url)
        conn = sqlite3.connect(self.cache_db)
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO http_cache (url_hash, url, status_code, content)
                VALUES (?, ?, ?, ?)
            """, (url_hash, url, status_code, content))
        conn.close()

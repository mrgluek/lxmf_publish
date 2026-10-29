"""SQLite state: subscribers and posts that were already announced."""
import sqlite3
import threading
import time


class Database:
    def __init__(self, path):
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        with self.lock, self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS subscribers (
                    hash TEXT PRIMARY KEY,
                    since REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS seen_posts (
                    guid TEXT PRIMARY KEY,
                    seen REAL NOT NULL
                );
            """)

    def subscribe(self, hash_hex):
        """True if the address was not subscribed before."""
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO subscribers (hash, since) VALUES (?, ?)", (hash_hex, time.time()))
            return cur.rowcount == 1

    def unsubscribe(self, hash_hex):
        """True if the address was subscribed."""
        with self.lock, self.conn:
            return self.conn.execute("DELETE FROM subscribers WHERE hash = ?", (hash_hex,)).rowcount == 1

    def is_subscribed(self, hash_hex):
        with self.lock:
            return self.conn.execute("SELECT 1 FROM subscribers WHERE hash = ?", (hash_hex,)).fetchone() is not None

    def subscribers(self):
        with self.lock:
            return [row[0] for row in self.conn.execute("SELECT hash FROM subscribers ORDER BY since")]

    def has_seen_any(self):
        with self.lock:
            return self.conn.execute("SELECT 1 FROM seen_posts LIMIT 1").fetchone() is not None

    def unseen(self, guids):
        with self.lock:
            return [g for g in guids if not self.conn.execute(
                "SELECT 1 FROM seen_posts WHERE guid = ?", (g,)).fetchone()]

    def mark_seen(self, guids):
        with self.lock, self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO seen_posts (guid, seen) VALUES (?, ?)", [(g, time.time()) for g in guids])

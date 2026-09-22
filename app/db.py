import sqlite3
import os
import time

DB_PATH = os.getenv("DB_PATH", "/home/ubuntu/8route/data/8route.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    cur = conn.cursor()
    
    # Enable WAL mode for high performance concurrency
    cur.execute("PRAGMA journal_mode=WAL;")
    
    # Providers Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS providers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT NOT NULL, -- 'openai_compatible', 'openrouter', 'antigravity', 'mistral'
        base_url TEXT,
        api_key TEXT,
        refresh_token TEXT,
        access_token TEXT,
        token_expires_at INTEGER DEFAULT 0,
        project_id TEXT,
        is_active INTEGER DEFAULT 1,
        created_at INTEGER
    );
    """)
    
    # Combos (Virtual Router Models)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS combos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL, -- e.g. '8r-flagship', 'hermes-wa'
        description TEXT,
        pipeline TEXT NOT NULL, -- JSON array: [{"provider_id": 1, "model": "claude-sonnet-4-6"}, ...]
        is_active INTEGER DEFAULT 1,
        created_at INTEGER
    );
    """)
    
    # API Tokens (for Reseller / Client)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        remain_quota INTEGER DEFAULT 5000000, -- in standard units
        unlimited_quota INTEGER DEFAULT 0,
        models_allowed TEXT DEFAULT '*', -- '*' or comma-separated
        status INTEGER DEFAULT 1,
        created_at INTEGER,
        expires_at INTEGER DEFAULT -1
    );
    """)
    
    # Usage Logs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS usage_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_id INTEGER,
        model TEXT,
        provider_name TEXT,
        prompt_tokens INTEGER,
        completion_tokens INTEGER,
        latency_ms INTEGER,
        status_code INTEGER,
        created_at INTEGER
    );
    """)
    
    conn.commit()
    conn.close()
    print("8Route Database Initialized (WAL Mode active).")

if __name__ == "__main__":
    init_db()

import sqlite3
import os
from pathlib import Path

def get_db(path: str = None) -> sqlite3.Connection:
    # Lê a env var em cada chamada — permite monkeypatch nos testes
    db_path = path or os.getenv("DATABASE_PATH", "users.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db(path: str = None):
    db = get_db(path)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL,
            username TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS credit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            delta INTEGER NOT NULL,
            motivo TEXT,
            ref_id TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS carrosseis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            nicho TEXT,
            tema TEXT,
            restricoes TEXT,
            cores_marca TEXT,
            logo_path TEXT,
            username_slide TEXT,
            plataforma TEXT DEFAULT 'Instagram',
            paleta_nome TEXT,
            pasta_path TEXT,
            status TEXT DEFAULT 'pendente',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            plano TEXT,
            valor REAL,
            creditos_comprados INTEGER,
            status TEXT DEFAULT 'pendente',
            mp_payment_id TEXT UNIQUE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.commit()
    db.close()

def creditos_disponiveis(user_id: int, db: sqlite3.Connection) -> int:
    row = db.execute(
        "SELECT COALESCE(SUM(delta), 0) FROM credit_events WHERE user_id=?",
        (user_id,)
    ).fetchone()
    return row[0]

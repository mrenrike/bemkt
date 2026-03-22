import sqlite3
import os
from pathlib import Path

def get_db(path: str = None) -> sqlite3.Connection:
    # Lê a env var em cada chamada — permite monkeypatch nos testes
    db_path = path or os.getenv("DATABASE_PATH", "users.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
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
            is_admin INTEGER DEFAULT 0,
            bloqueado_ate TIMESTAMP,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            ip TEXT NOT NULL,
            sucesso INTEGER DEFAULT 0,
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
            modelo TEXT DEFAULT '4',
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
    # Migrations para DBs existentes
    for migration in [
        "ALTER TABLE carrosseis ADD COLUMN modelo TEXT DEFAULT '4'",
        "ALTER TABLE users ADD COLUMN bloqueado_ate TIMESTAMP",
        "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0",
        "ALTER TABLE carrosseis ADD COLUMN finalidade TEXT",
        "ALTER TABLE carrosseis ADD COLUMN cta_objetivo TEXT",
        "ALTER TABLE carrosseis ADD COLUMN legenda_post TEXT",
        "ALTER TABLE carrosseis ADD COLUMN conteudo_manual TEXT",
        "ALTER TABLE carrosseis ADD COLUMN modo TEXT DEFAULT 'automatico'",
        "ALTER TABLE carrosseis ADD COLUMN sugestoes_tema TEXT",
        "ALTER TABLE carrosseis ADD COLUMN share_token TEXT",
    ]:
        try:
            db.execute(migration)
            db.commit()
        except Exception:
            pass
    db.close()


MAX_TENTATIVAS = 5
LOCKOUT_MINUTOS = 15

def registrar_tentativa_login(email: str, ip: str, sucesso: bool, db) -> None:
    db.execute(
        "INSERT INTO login_attempts (email, ip, sucesso) VALUES (?,?,?)",
        (email[:254], ip[:45], 1 if sucesso else 0)
    )
    if sucesso:
        # Limpa tentativas antigas e desbloqueia
        db.execute(
            "UPDATE users SET bloqueado_ate=NULL WHERE email=?", (email,)
        )
        db.execute(
            "DELETE FROM login_attempts WHERE email=? AND sucesso=0", (email,)
        )
    else:
        # Conta falhas recentes (última hora)
        falhas = db.execute(
            "SELECT COUNT(*) FROM login_attempts "
            "WHERE email=? AND sucesso=0 AND criado_em > datetime('now','-1 hour')",
            (email,)
        ).fetchone()[0]
        if falhas >= MAX_TENTATIVAS:
            db.execute(
                "UPDATE users SET bloqueado_ate=datetime('now','+? minutes') WHERE email=?",
                (LOCKOUT_MINUTOS, email)
            )

def conta_bloqueada(email: str, db) -> bool:
    row = db.execute(
        "SELECT bloqueado_ate FROM users WHERE email=?", (email,)
    ).fetchone()
    if not row or not row["bloqueado_ate"]:
        return False
    from datetime import datetime, timezone
    bloqueado = datetime.fromisoformat(row["bloqueado_ate"])
    if bloqueado.tzinfo is None:
        bloqueado = bloqueado.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < bloqueado

def creditos_disponiveis(user_id: int, db: sqlite3.Connection) -> int:
    row = db.execute(
        "SELECT COALESCE(SUM(delta), 0) FROM credit_events WHERE user_id=?",
        (user_id,)
    ).fetchone()
    return row[0]

import sqlite3
from app.database import init_db, get_db

def test_init_creates_all_tables(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"users", "credit_events", "carrosseis", "pagamentos"}.issubset(tables)
    conn.close()

def test_new_user_has_no_credits(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    db = get_db(db_path)
    db.execute("INSERT INTO users (nome, email, senha_hash) VALUES (?,?,?)", ("Test", "t@t.com", "hash"))
    db.commit()
    user_id = db.execute("SELECT id FROM users WHERE email=?", ("t@t.com",)).fetchone()[0]
    total = db.execute("SELECT COALESCE(SUM(delta),0) FROM credit_events WHERE user_id=?", (user_id,)).fetchone()[0]
    assert total == 0
    db.close()

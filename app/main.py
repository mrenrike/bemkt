# app/main.py
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.database import init_db, get_db, creditos_disponiveis
from app.auth import hash_senha, verificar_senha, criar_token, usuario_atual

# ── Startup hook ─────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = get_db()
    presos = db.execute(
        "SELECT id, user_id FROM carrosseis WHERE status = 'gerando'"
    ).fetchall()
    for job in presos:
        db.execute("UPDATE carrosseis SET status='erro' WHERE id=?", (job["id"],))
        db.execute(
            "INSERT INTO credit_events (user_id, delta, motivo, ref_id) VALUES (?,1,'reembolso',?)",
            (job["user_id"], str(job["id"]))
        )
    db.commit()
    db.close()
    yield

app = FastAPI(lifespan=lifespan)

# ── Static files ──────────────────────────────────────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Agência IA API"}

# ── Schemas ───────────────────────────────────────────────────────
class CadastroIn(BaseModel):
    nome: str
    email: str
    senha: str
    username: str = ""

class LoginIn(BaseModel):
    email: str
    senha: str

# ── Auth endpoints ────────────────────────────────────────────────
@app.post("/auth/cadastro")
def cadastro(data: CadastroIn):
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email=?", (data.email,)).fetchone()
    if existing:
        db.close()
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    h = hash_senha(data.senha)
    try:
        db.execute(
            "INSERT INTO users (nome, email, senha_hash, username) VALUES (?,?,?,?)",
            (data.nome, data.email, h, data.username)
        )
        db.commit()
        user_id = db.execute("SELECT id FROM users WHERE email=?", (data.email,)).fetchone()[0]
        db.execute(
            "INSERT INTO credit_events (user_id, delta, motivo) VALUES (?,1,'trial')",
            (user_id,)
        )
        db.commit()
    finally:
        db.close()
    token = criar_token({"sub": str(user_id)})
    return {"token": token, "nome": data.nome}

@app.post("/auth/login")
def login(data: LoginIn):
    db = get_db()
    user = db.execute(
        "SELECT id, nome, senha_hash FROM users WHERE email=?", (data.email,)
    ).fetchone()
    db.close()
    if not user or not verificar_senha(data.senha, user["senha_hash"]):
        raise HTTPException(status_code=401, detail="Email ou senha incorretos")
    token = criar_token({"sub": str(user["id"])})
    return {"token": token, "nome": user["nome"]}

@app.get("/me")
def me(user_id: int = Depends(usuario_atual)):
    db = get_db()
    user = db.execute("SELECT nome, email, username FROM users WHERE id=?", (user_id,)).fetchone()
    creditos = creditos_disponiveis(user_id, db)
    db.close()
    return {"nome": user["nome"], "email": user["email"], "username": user["username"], "creditos": creditos}

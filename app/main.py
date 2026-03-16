# app/main.py
import os
import asyncio, json, zipfile, shutil
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.database import init_db, get_db, creditos_disponiveis
from app.auth import hash_senha, verificar_senha, criar_token, usuario_atual
from app.chat import PERGUNTAS, proxima_pergunta, resumo_job
from app.carousel import gerar_carrossel

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

UPLOAD_DIR = Path("uploads")
CARROSSEIS_DIR = Path("carrosseis")
UPLOAD_DIR.mkdir(exist_ok=True)
CARROSSEIS_DIR.mkdir(exist_ok=True)

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

# ── Chat endpoints ────────────────────────────────────────────────
@app.post("/chat/iniciar")
def chat_iniciar(user_id: int = Depends(usuario_atual)):
    db = get_db()
    if creditos_disponiveis(user_id, db) <= 0:
        db.close()
        raise HTTPException(status_code=402, detail="Sem créditos")
    ativos = db.execute(
        "SELECT COUNT(*) FROM carrosseis WHERE user_id=? AND status IN ('pendente','gerando')",
        (user_id,)
    ).fetchone()[0]
    if ativos >= 3:
        db.close()
        raise HTTPException(status_code=429, detail="Máximo de 3 jobs simultâneos")
    db.execute("INSERT INTO carrosseis (user_id, status) VALUES (?, 'pendente')", (user_id,))
    db.commit()
    job_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.close()
    primeira = PERGUNTAS[0]
    return {"job_id": job_id, "pergunta": primeira["texto"], "campo": primeira["campo"], "upload": primeira.get("upload", False)}

@app.post("/chat/responder")
async def chat_responder(
    job_id: int,
    campo: str,
    resposta: str = "",
    arquivo: UploadFile | None = None,
    user_id: int = Depends(usuario_atual)
):
    db = get_db()
    job = db.execute("SELECT * FROM carrosseis WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    if not job:
        db.close()
        raise HTTPException(status_code=404, detail="Job não encontrado")

    valor = resposta.strip()

    # Upload de logo
    if arquivo and arquivo.filename:
        ext = Path(arquivo.filename).suffix.lower()
        if ext not in [".png", ".jpg", ".jpeg", ".svg"]:
            db.close()
            raise HTTPException(status_code=400, detail="Formato inválido. Use PNG, JPG ou SVG.")
        conteudo = await arquivo.read()
        if len(conteudo) > 5 * 1024 * 1024:
            db.close()
            raise HTTPException(status_code=400, detail="Arquivo maior que 5MB")
        logo_file = UPLOAD_DIR / f"{job_id}_{arquivo.filename}"
        logo_file.write_bytes(conteudo)
        valor = str(logo_file)

    colunas_validas = {"nicho", "tema", "logo_path", "cores_marca", "username_slide", "restricoes"}
    if campo in colunas_validas:
        db.execute(f"UPDATE carrosseis SET {campo}=? WHERE id=?", (valor, job_id))
        db.commit()

    # Monta estado: apenas campos já respondidos (NULL = não respondido ainda)
    job = db.execute("SELECT * FROM carrosseis WHERE id=?", (job_id,)).fetchone()
    estado = {k: job[k] for k in ["nicho", "tema", "logo_path", "cores_marca", "username_slide", "restricoes"] if job[k] is not None}

    db.close()
    prox, done = proxima_pergunta(estado)
    if done:
        return {"done": True, "resumo": resumo_job(estado)}
    return {"done": False, "pergunta": prox["texto"], "campo": prox["campo"], "upload": prox.get("upload", False)}

@app.post("/chat/confirmar")
def chat_confirmar(job_id: int, background_tasks: BackgroundTasks, user_id: int = Depends(usuario_atual)):
    db = get_db()
    job = db.execute("SELECT * FROM carrosseis WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    if not job:
        db.close()
        raise HTTPException(status_code=404)

    db.execute("BEGIN IMMEDIATE")
    try:
        creditos = db.execute(
            "SELECT COALESCE(SUM(delta),0) FROM credit_events WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        if creditos <= 0:
            db.execute("ROLLBACK")
            db.close()
            raise HTTPException(status_code=402, detail="Sem créditos")
        db.execute(
            "INSERT INTO credit_events (user_id, delta, motivo, ref_id) VALUES (?,?,'uso',?)",
            (user_id, -1, str(job_id))
        )
        db.execute("UPDATE carrosseis SET status='gerando' WHERE id=?", (job_id,))
        db.execute("COMMIT")
    except HTTPException:
        raise
    except Exception:
        db.execute("ROLLBACK")
        db.close()
        raise

    db.close()
    background_tasks.add_task(_executar_job, job_id, user_id, dict(job))
    return {"status": "gerando", "job_id": job_id}

async def _executar_job(job_id: int, user_id: int, job: dict):
    pasta = CARROSSEIS_DIR / str(user_id) / str(job_id)
    db = get_db()
    try:
        pngs = await gerar_carrossel(
            tema=job["tema"] or "",
            plataforma="Instagram",
            nicho=job["nicho"] or "",
            restricoes=job["restricoes"] or "",
            cores_marca=job["cores_marca"] or "",
            logo_path=job["logo_path"],
            username=job["username_slide"] or "",
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            pexels_key=os.getenv("PEXELS_API_KEY", ""),
            pasta_destino=pasta,
        )
        db.execute(
            "UPDATE carrosseis SET status='pronto', pasta_path=? WHERE id=?",
            (str(pasta), job_id)
        )
    except Exception as e:
        db.execute("UPDATE carrosseis SET status='erro' WHERE id=?", (job_id,))
        db.execute(
            "INSERT INTO credit_events (user_id, delta, motivo, ref_id) VALUES (?,1,'reembolso',?)",
            (user_id, str(job_id))
        )
    db.commit()
    db.close()

# ── Job status e download ──────────────────────────────────────────
@app.get("/job/{job_id}/status")
def job_status(job_id: int, user_id: int = Depends(usuario_atual)):
    db = get_db()
    job = db.execute("SELECT status FROM carrosseis WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    db.close()
    if not job:
        raise HTTPException(status_code=404)
    return {"status": job["status"]}

@app.get("/job/{job_id}/slides")
def job_slides(job_id: int, user_id: int = Depends(usuario_atual)):
    db = get_db()
    job = db.execute("SELECT status, pasta_path FROM carrosseis WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    db.close()
    if not job or job["status"] != "pronto":
        raise HTTPException(status_code=404, detail="Job não pronto")
    pasta = Path(job["pasta_path"])
    pngs = sorted(pasta.glob("slide_*.png"))
    return {"slides": [f"/job/{job_id}/slide/{p.name}" for p in pngs]}

@app.get("/job/{job_id}/slide/{filename}")
def servir_slide(job_id: int, filename: str, user_id: int = Depends(usuario_atual)):
    db = get_db()
    job = db.execute("SELECT pasta_path FROM carrosseis WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    db.close()
    if not job:
        raise HTTPException(status_code=404)
    pasta = Path(job["pasta_path"]).resolve()
    path = (pasta / filename).resolve()
    # Prevent path traversal: ensure file is within the job's directory
    if not str(path).startswith(str(pasta)):
        raise HTTPException(status_code=400, detail="Filename inválido")
    if not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(str(path))

@app.get("/job/{job_id}/download")
def job_download(job_id: int, user_id: int = Depends(usuario_atual)):
    db = get_db()
    job = db.execute("SELECT status, pasta_path FROM carrosseis WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    db.close()
    if not job or job["status"] != "pronto":
        raise HTTPException(status_code=404)
    pasta = Path(job["pasta_path"])
    zip_path = pasta / "carrossel.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for png in sorted(pasta.glob("slide_*.png")):
            zf.write(png, png.name)
    return FileResponse(str(zip_path), media_type="application/zip", filename=f"carrossel_{job_id}.zip")

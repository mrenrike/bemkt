# app/main.py
import sys, os
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
from dotenv import load_dotenv
load_dotenv()
import asyncio, json, zipfile, logging
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.FileHandler("agencia_ia.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator, EmailStr
from app.database import init_db, get_db, creditos_disponiveis, registrar_tentativa_login, conta_bloqueada
from app.auth import hash_senha, verificar_senha, criar_token, usuario_atual, admin_atual
from app.chat import PERGUNTAS, proxima_pergunta, resumo_job
from app.carousel import gerar_carrossel, gerar_carrossel_manual
from app.email_sender import criar_zip, enviar_email_zip, notificar_admin_cadastro
from app.pagamentos import PLANOS, criar_preferencia_mp, validar_assinatura_webhook, MP_WEBHOOK_SECRET
from app.security import (
    SecurityHeadersMiddleware, rate_limit,
    validar_email, sanitizar_texto, validar_magic_bytes
)

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

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

# ── Middlewares ────────────────────────────────────────────────────
app.add_middleware(SecurityHeadersMiddleware)

_ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:8000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)

# ── Static files ──────────────────────────────────────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

UPLOAD_DIR = Path("uploads")
CARROSSEIS_DIR = Path("carrosseis")
REFS_DIR = Path("uploads/refs_template")
UPLOAD_DIR.mkdir(exist_ok=True)
CARROSSEIS_DIR.mkdir(exist_ok=True)
REFS_DIR.mkdir(exist_ok=True)

@app.get("/")
def root():
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.get("/entrar")
def entrar():
    return FileResponse(os.path.join(static_dir, "entrar.html"))

@app.get("/sitemap.xml")
def sitemap():
    return FileResponse(os.path.join(static_dir, "sitemap.xml"), media_type="application/xml")

@app.get("/robots.txt")
def robots():
    return FileResponse(os.path.join(static_dir, "robots.txt"), media_type="text/plain")

# ── Schemas ───────────────────────────────────────────────────────
class CadastroIn(BaseModel):
    nome: str
    email: str
    senha: str
    username: str = ""

    @field_validator("nome")
    @classmethod
    def _nome(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 120:
            raise ValueError("Nome inválido")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        import re
        v = v.strip().lower()
        if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', v) or len(v) > 254:
            raise ValueError("Email inválido")
        return v

    @field_validator("senha")
    @classmethod
    def _senha(cls, v: str) -> str:
        if len(v) < 8 or len(v) > 128:
            raise ValueError("Senha deve ter entre 8 e 128 caracteres")
        return v

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        return v.strip()[:60]

class LoginIn(BaseModel):
    email: str
    senha: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.strip().lower()[:254]

    @field_validator("senha")
    @classmethod
    def _senha(cls, v: str) -> str:
        return v[:128]

class EmailIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        import re
        v = v.strip().lower()
        if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', v) or len(v) > 254:
            raise ValueError("Email inválido")
        if any(c in v for c in ['\r', '\n', '\0']):
            raise ValueError("Email inválido")
        return v

class PerfilIn(BaseModel):
    nome: str
    username: str = ""

    @field_validator("nome")
    @classmethod
    def _nome(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 120:
            raise ValueError("Nome inválido")
        return v

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        return v.strip()[:60]

class SenhaIn(BaseModel):
    senha_atual: str
    senha_nova: str

    @field_validator("senha_nova")
    @classmethod
    def _senha_nova(cls, v: str) -> str:
        if len(v) < 8 or len(v) > 128:
            raise ValueError("Senha deve ter entre 8 e 128 caracteres")
        return v

class PagamentoIn(BaseModel):
    plano: str

    @field_validator("plano")
    @classmethod
    def _plano(cls, v: str) -> str:
        return v.strip()[:30]

# ── Auth endpoints ────────────────────────────────────────────────
@app.post("/auth/cadastro")
def cadastro(data: CadastroIn, request: Request, background_tasks: BackgroundTasks):
    rate_limit(request, max_requests=5, window_seconds=300, scope="cadastro")
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
    background_tasks.add_task(notificar_admin_cadastro, data.nome, data.email, data.username or "")
    return {"token": token, "nome": data.nome}

@app.post("/auth/login")
def login(data: LoginIn, request: Request):
    rate_limit(request, max_requests=10, window_seconds=60, scope="login")
    ip = request.client.host if request.client else "unknown"
    db = get_db()
    try:
        # Verifica bloqueio de conta
        if conta_bloqueada(data.email, db):
            raise HTTPException(
                status_code=429,
                detail="Conta temporariamente bloqueada. Tente novamente em 15 minutos."
            )
        user = db.execute(
            "SELECT id, nome, senha_hash FROM users WHERE email=?", (data.email,)
        ).fetchone()
        if not user or not verificar_senha(data.senha, user["senha_hash"]):
            if user:
                registrar_tentativa_login(data.email, ip, False, db)
                db.commit()
            logger.warning("Login falhou email=%s ip=%s", data.email, ip)
            raise HTTPException(status_code=401, detail="Email ou senha incorretos")
        registrar_tentativa_login(data.email, ip, True, db)
        db.commit()
    finally:
        db.close()
    token = criar_token({"sub": str(user["id"])})
    return {"token": token, "nome": user["nome"]}

@app.get("/me")
def me(user_id: int = Depends(usuario_atual)):
    db = get_db()
    user = db.execute("SELECT nome, email, username FROM users WHERE id=?", (user_id,)).fetchone()
    creditos = creditos_disponiveis(user_id, db)
    db.close()
    return {"nome": user["nome"], "email": user["email"], "username": user["username"], "creditos": creditos}

# ── Perfil endpoints ──────────────────────────────────────────────
@app.get("/historico")
def historico(user_id: int = Depends(usuario_atual)):
    db = get_db()
    rows = db.execute(
        """SELECT id, tema, nicho, plataforma, modelo, status, criado_em
           FROM carrosseis WHERE user_id=?
           ORDER BY criado_em DESC LIMIT 50""",
        (user_id,)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.put("/perfil")
def atualizar_perfil(data: PerfilIn, user_id: int = Depends(usuario_atual)):
    db = get_db()
    db.execute("UPDATE users SET nome=?, username=? WHERE id=?", (data.nome, data.username, user_id))
    db.commit()
    db.close()
    return {"ok": True}

@app.put("/perfil/senha")
def trocar_senha(data: SenhaIn, user_id: int = Depends(usuario_atual)):
    db = get_db()
    user = db.execute("SELECT senha_hash FROM users WHERE id=?", (user_id,)).fetchone()
    if not user or not verificar_senha(data.senha_atual, user["senha_hash"]):
        db.close()
        raise HTTPException(status_code=401, detail="Senha atual incorreta")
    h = hash_senha(data.senha_nova)
    db.execute("UPDATE users SET senha_hash=? WHERE id=?", (h, user_id))
    db.commit()
    db.close()
    return {"ok": True}

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

@app.get("/chat/estado/{job_id}")
def chat_estado(job_id: int, user_id: int = Depends(usuario_atual)):
    """Retoma um chat em andamento — retorna a próxima pergunta pendente."""
    db = get_db()
    job = db.execute("SELECT * FROM carrosseis WHERE id=? AND user_id=? AND status='pendente'", (job_id, user_id)).fetchone()
    db.close()
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado ou já concluído")
    estado = {k: job[k] for k in ["nicho", "tema", "plataforma", "modelo", "logo_path",
              "cores_marca", "username_slide", "restricoes", "finalidade", "cta_objetivo"]
              if job[k] is not None}
    prox, done = proxima_pergunta(estado)
    if done:
        return {"done": True, "resumo": resumo_job(estado)}
    resp = {"job_id": job_id, "done": False, "pergunta": prox["texto"], "campo": prox["campo"], "upload": prox.get("upload", False)}
    # Reexibe sugestões armazenadas ao retomar na etapa de tema
    if prox["campo"] == "tema" and job["sugestoes_tema"]:
        try:
            sugestoes = json.loads(job["sugestoes_tema"])
            if sugestoes and estado.get("nicho"):
                sug_txt = "\n".join(f"{i+1}\ufe0f\u20e3 {s}" for i, s in enumerate(sugestoes))
                resp["pergunta"] = (
                    f"Qual o tema do carrossel?\n\n"
                    f"*Sugestões para o nicho {estado['nicho']}:*\n{sug_txt}\n\n"
                    f"Digite 1–5 para escolher ou escreva seu próprio tema."
                )
                resp["sugestoes"] = sugestoes
        except Exception:
            pass
    return resp

def _extrair_tema_de_url_sync(api_key: str, url: str) -> str:
    """Busca o conteúdo da URL e pede para Claude extrair o tema principal."""
    import requests, anthropic
    try:
        r = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (compatible; BEMKT/1.0)"
        })
        r.raise_for_status()
        # Extrai texto simples do HTML
        from html.parser import HTMLParser
        class _Strip(HTMLParser):
            def __init__(self):
                super().__init__()
                self.chunks = []
                self._skip = False
            def handle_starttag(self, tag, attrs):
                if tag in ("script","style","noscript"): self._skip = True
            def handle_endtag(self, tag):
                if tag in ("script","style","noscript"): self._skip = False
            def handle_data(self, data):
                if not self._skip:
                    t = data.strip()
                    if t: self.chunks.append(t)
        p = _Strip()
        p.feed(r.text[:40000])
        texto = " ".join(p.chunks)[:3000]
    except Exception:
        # Se não conseguiu buscar, usa a URL como tema direto
        return url

    client = anthropic.Anthropic(api_key=api_key)
    prompt = (
        f"A seguir está o conteúdo extraído de uma página web (URL: {url}).\n\n"
        f"Conteúdo:\n{texto}\n\n"
        f"Extraia e escreva em UMA única frase direta o tema principal desse conteúdo, "
        f"de forma que possa ser usado como tema de um carrossel para Instagram. "
        f"Responda APENAS com a frase do tema, sem explicações."
    )
    try:
        tema = anthropic.Anthropic(api_key=api_key).messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        ).content[0].text.strip().strip('"')
        return tema if tema else url
    except Exception:
        return url


def _gerar_sugestoes_tema_sync(api_key: str, nicho: str, plataforma: str) -> list:
    """Gera 5 sugestões de tema via Claude Haiku (rápido, barato)."""
    import anthropic, re, json as _json
    client = anthropic.Anthropic(api_key=api_key)
    prompt = (
        f"Você é um estrategista de conteúdo para redes sociais.\n"
        f"Sugira exatamente 5 ideias de tema para carrossel no nicho de '{nicho}' para {plataforma}.\n"
        f"Cada tema deve ser específico, direto e ter potencial de engajamento.\n"
        f"Responda APENAS com um JSON array de 5 strings, sem nenhuma explicação extra.\n"
        f'Exemplo: ["Tema 1", "Tema 2", "Tema 3", "Tema 4", "Tema 5"]'
    )
    try:
        texto = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        ).content[0].text.strip()
        m = re.search(r'\[.*?\]', texto, re.DOTALL)
        if m:
            return _json.loads(m.group(0))
    except Exception:
        pass
    return []


@app.post("/chat/responder")
async def chat_responder(
    job_id: int = Form(...),
    campo: str = Form(...),
    resposta: str = Form(""),
    arquivo: UploadFile | None = None,
    user_id: int = Depends(usuario_atual)
):
    db = get_db()
    job = db.execute("SELECT * FROM carrosseis WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    if not job:
        db.close()
        raise HTTPException(status_code=404, detail="Job não encontrado")

    valor = sanitizar_texto(resposta, max_len=4000)

    # Resolve shortcut numérico para sugestão de tema (1–5)
    if campo == "tema" and valor.strip() in {"1","2","3","4","5"}:
        row_sug = db.execute("SELECT sugestoes_tema FROM carrosseis WHERE id=?", (job_id,)).fetchone()
        if row_sug and row_sug["sugestoes_tema"]:
            try:
                sug_list = json.loads(row_sug["sugestoes_tema"])
                idx = int(valor.strip()) - 1
                if 0 <= idx < len(sug_list):
                    valor = sug_list[idx]
            except Exception:
                pass

    # Detecta URL no campo tema e extrai o tema via IA
    _url_extraindo = False
    if campo == "tema" and valor.strip().startswith(("http://", "https://")):
        _url_extraindo = True
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        try:
            valor = await asyncio.to_thread(_extrair_tema_de_url_sync, api_key, valor.strip())
        except Exception:
            pass  # mantém a URL como tema

    # Upload de logo
    if arquivo and arquivo.filename:
        # Sanitiza nome do arquivo — sem path traversal
        nome_seguro = Path(arquivo.filename).name
        ext = Path(nome_seguro).suffix.lower()
        if ext not in [".png", ".jpg", ".jpeg", ".svg"]:
            db.close()
            raise HTTPException(status_code=400, detail="Formato inválido. Use PNG, JPG ou SVG.")
        conteudo = await arquivo.read()
        if len(conteudo) > 5 * 1024 * 1024:
            db.close()
            raise HTTPException(status_code=400, detail="Arquivo maior que 5MB")
        # Valida magic bytes (conteúdo real da imagem)
        if not validar_magic_bytes(conteudo, nome_seguro):
            db.close()
            raise HTTPException(status_code=400, detail="Arquivo não é uma imagem válida.")
        logo_file = UPLOAD_DIR / f"{job_id}_{nome_seguro}"
        logo_file.write_bytes(conteudo)
        valor = str(logo_file)

    # Whitelist estrita de colunas — rejeita qualquer campo desconhecido
    COLUNAS_VALIDAS = {"nicho", "tema", "plataforma", "modelo", "logo_path", "cores_marca",
                       "username_slide", "restricoes", "finalidade", "cta_objetivo"}
    if campo not in COLUNAS_VALIDAS:
        db.close()
        raise HTTPException(status_code=422, detail="Campo inválido")

    # Limites de tamanho por campo
    LIMITES = {"tema": 2000, "nicho": 500, "restricoes": 1000, "cores_marca": 500,
               "username_slide": 60, "finalidade": 50, "cta_objetivo": 50}
    if campo in LIMITES:
        valor = valor[:LIMITES[campo]]

    db.execute(f"UPDATE carrosseis SET {campo}=? WHERE id=?", (valor, job_id))
    db.commit()

    # Monta estado: apenas campos já respondidos (NULL = não respondido ainda)
    job = db.execute("SELECT * FROM carrosseis WHERE id=?", (job_id,)).fetchone()
    estado = {k: job[k] for k in ["nicho", "tema", "plataforma", "modelo", "logo_path",
              "cores_marca", "username_slide", "restricoes", "finalidade", "cta_objetivo"]
              if job[k] is not None}

    db.close()
    prox, done = proxima_pergunta(estado)
    if done:
        return {"done": True, "resumo": resumo_job(estado)}

    resp: dict = {"done": False, "pergunta": prox["texto"], "campo": prox["campo"], "upload": prox.get("upload", False)}

    # Confirma tema extraído de URL para o usuário
    if _url_extraindo and campo == "tema":
        resp["tema_extraido"] = valor
        resp["aviso"] = f"🔗 Tema extraído do link: *{valor}*\n\nContinuando com esse tema..."

    # Ao transitar para o campo "tema", gera sugestões personalizadas via IA
    if prox["campo"] == "tema" and estado.get("nicho"):
        try:
            _PLAT_MAP = {"1": "Instagram", "2": "LinkedIn", "3": "TikTok", "4": "X (Twitter)"}
            plataforma = _PLAT_MAP.get(estado.get("plataforma", "1"), "Instagram")
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            sugestoes = await asyncio.to_thread(_gerar_sugestoes_tema_sync, api_key, estado["nicho"], plataforma)
            if sugestoes:
                db2 = get_db()
                db2.execute("UPDATE carrosseis SET sugestoes_tema=? WHERE id=?",
                            (json.dumps(sugestoes, ensure_ascii=False), job_id))
                db2.commit()
                db2.close()
                sug_txt = "\n".join(f"{i+1}\ufe0f\u20e3 {s}" for i, s in enumerate(sugestoes))
                resp["pergunta"] = (
                    f"Qual o tema do carrossel?\n\n"
                    f"*Sugestões para o nicho {estado['nicho']}:*\n{sug_txt}\n\n"
                    f"Digite 1–5 para escolher ou escreva seu próprio tema."
                )
                resp["sugestoes"] = sugestoes
        except Exception:
            pass  # Se falhar, retorna pergunta normal

    return resp

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


# ── Wizard form endpoints ─────────────────────────────────────────

@app.get("/minhas-preferencias")
def minhas_preferencias(user_id: int = Depends(usuario_atual)):
    """Retorna as preferências do último carrossel gerado pelo usuário."""
    db = get_db()
    row = db.execute(
        """SELECT plataforma, nicho, modelo, cores_marca, username_slide,
                  tema, finalidade, cta_objetivo
           FROM carrosseis WHERE user_id=? AND status='pronto'
           ORDER BY criado_em DESC LIMIT 1""",
        (user_id,)
    ).fetchone()
    db.close()
    if not row:
        return {}
    return {k: row[k] for k in row.keys() if row[k] is not None}


@app.post("/analisar-imagem")
async def analisar_imagem(
    arquivo: UploadFile = File(...),
    user_id: int = Depends(usuario_atual)
):
    """Recebe uma imagem e extrai o tema/assunto via Claude Vision."""
    conteudo = await arquivo.read()
    if len(conteudo) > 5 * 1024 * 1024:
        raise HTTPException(400, "Arquivo muito grande (máx 5MB)")
    nome = Path(arquivo.filename or "img.jpg").name
    if not validar_magic_bytes(conteudo, nome):
        raise HTTPException(400, "Arquivo não é uma imagem válida")
    import base64, anthropic
    mime = arquivo.content_type or "image/jpeg"
    b64 = base64.b64encode(conteudo).decode()
    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                    {"type": "text", "text": (
                        "Analise esta imagem e extraia o assunto/tema principal em 1-2 frases curtas e diretas em português. "
                        "O tema será usado para criar um carrossel para Instagram. "
                        "Responda APENAS com o tema, sem introdução, sem explicação."
                    )}
                ]
            }]
        )
        tema = resp.content[0].text.strip().strip('"')
        return {"tema": tema}
    except Exception as e:
        logger.error("Erro ao analisar imagem: %s", e)
        raise HTTPException(500, "Erro ao analisar imagem")


@app.post("/sugerir-tema")
async def sugerir_tema(
    nicho: str = Form(""),
    plataforma: str = Form(""),
    user_id: int = Depends(usuario_atual),
):
    """Sugere temas de carrossel com base no nicho e plataforma do usuário."""
    import anthropic as _ant
    nicho_s = sanitizar_texto(nicho, 200)
    plat_s  = sanitizar_texto(plataforma, 20)
    prompt = (
        f"Sugira 5 ideias de tema para carrossel de {'Instagram' if plat_s=='1' else 'redes sociais'} "
        f"no nicho: {nicho_s or 'geral'}. "
        "Retorne apenas uma lista numerada, cada linha com a ideia do tema (máx 15 palavras cada). "
        "Sem explicações extras."
    )
    try:
        client = _ant.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()
        # Extrai as linhas numeradas
        sugestoes = [
            line.lstrip("0123456789. )-").strip()
            for line in raw.splitlines()
            if line.strip() and line.strip()[0].isdigit()
        ][:5]
        return {"sugestoes": sugestoes}
    except Exception as e:
        logger.error("Erro ao sugerir tema: %s", e)
        raise HTTPException(500, "Erro ao sugerir tema")


@app.post("/gerar")
async def gerar_direto(
    background_tasks: BackgroundTasks,
    plataforma: str = Form(...),
    nicho: str = Form(""),
    tema: str = Form(...),
    finalidade: str = Form(""),
    cta_objetivo: str = Form(""),
    modelo: str = Form("1"),
    cores_marca: str = Form(""),
    username_slide: str = Form(""),
    restricoes: str = Form(""),
    uso_fotos: str = Form("fotos"),
    logo: UploadFile | None = File(None),
    user_id: int = Depends(usuario_atual),
):
    """Cria e inicia um job de geração a partir do wizard form."""
    db = get_db()

    # Verifica créditos + jobs simultâneos
    if creditos_disponiveis(user_id, db) <= 0:
        db.close()
        raise HTTPException(402, "Sem créditos")
    ativos = db.execute(
        "SELECT COUNT(*) FROM carrosseis WHERE user_id=? AND status IN ('pendente','gerando')",
        (user_id,)
    ).fetchone()[0]
    if ativos >= 3:
        db.close()
        raise HTTPException(429, "Máximo de 3 jobs simultâneos")

    # Logo upload
    logo_path = None
    if logo and logo.filename:
        nome_seguro = Path(logo.filename).name
        ext = Path(nome_seguro).suffix.lower()
        if ext not in [".png", ".jpg", ".jpeg", ".svg"]:
            db.close()
            raise HTTPException(400, "Logo: use PNG, JPG ou SVG")
        conteudo_logo = await logo.read()
        if len(conteudo_logo) > 5 * 1024 * 1024:
            db.close()
            raise HTTPException(400, "Logo maior que 5MB")
        if not validar_magic_bytes(conteudo_logo, nome_seguro):
            db.close()
            raise HTTPException(400, "Logo não é uma imagem válida")
        logo_file = UPLOAD_DIR / f"logo_{user_id}_{nome_seguro}"
        logo_file.write_bytes(conteudo_logo)
        logo_path = str(logo_file)

    # Sanitiza campos
    tema_s         = sanitizar_texto(tema, max_len=2000)
    nicho_s        = sanitizar_texto(nicho, max_len=500)
    uso_fotos_s    = "sem_fotos" if uso_fotos == "sem_fotos" else "fotos"
    restricoes_s   = sanitizar_texto(restricoes, max_len=1000)
    if uso_fotos_s == "sem_fotos":
        restricoes_s = ("sem fotos de fundo; use apenas tipografia e cores. " + restricoes_s).strip()
    cores_s        = sanitizar_texto(cores_marca, max_len=500)
    username_s     = sanitizar_texto(username_slide, max_len=60)
    finalidade_s   = sanitizar_texto(finalidade, max_len=50)
    cta_s          = sanitizar_texto(cta_objetivo, max_len=50)
    modelo_s       = modelo if modelo in {"1","2","3","4","5"} else "1"
    plataforma_s   = plataforma if plataforma in {"1","2","3","4"} else "1"

    # Cria job e já preenche todos os campos
    db.execute("BEGIN IMMEDIATE")
    try:
        creditos = db.execute(
            "SELECT COALESCE(SUM(delta),0) FROM credit_events WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        if creditos <= 0:
            db.execute("ROLLBACK")
            db.close()
            raise HTTPException(402, "Sem créditos")
        db.execute(
            """INSERT INTO carrosseis
               (user_id, status, plataforma, nicho, tema, finalidade, cta_objetivo,
                modelo, cores_marca, username_slide, restricoes, logo_path)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, "gerando", plataforma_s, nicho_s, tema_s, finalidade_s, cta_s,
             modelo_s, cores_s, username_s, restricoes_s, logo_path)
        )
        job_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute(
            "INSERT INTO credit_events (user_id, delta, motivo, ref_id) VALUES (?,?,'uso',?)",
            (user_id, -1, str(job_id))
        )
        db.execute("COMMIT")
    except HTTPException:
        raise
    except Exception:
        db.execute("ROLLBACK")
        db.close()
        raise

    job = db.execute("SELECT * FROM carrosseis WHERE id=?", (job_id,)).fetchone()
    db.close()

    background_tasks.add_task(_executar_job, job_id, user_id, dict(job))
    return {"status": "gerando", "job_id": job_id}


async def _executar_job(job_id: int, user_id: int, job: dict):
    pasta = CARROSSEIS_DIR / str(user_id) / str(job_id)
    print(f"\n>>> JOB {job_id} INICIADO tema={job.get('tema')}", flush=True)
    ok = False
    erro_msg = ""
    try:
        _PLAT_MAP = {"1": "Instagram", "2": "LinkedIn", "3": "TikTok", "4": "X (Twitter)"}
        plat_raw = job.get("plataforma") or "1"
        pngs = await gerar_carrossel(
            tema=job["tema"] or "",
            plataforma=_PLAT_MAP.get(plat_raw, plat_raw),
            nicho=job["nicho"] or "",
            restricoes=job["restricoes"] or "",
            cores_marca=job["cores_marca"] or "",
            logo_path=job["logo_path"],
            username=job["username_slide"] or "",
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            pexels_key=os.getenv("PEXELS_API_KEY", ""),
            pasta_destino=pasta,
            template=job.get("modelo") or "4",
            finalidade=job.get("finalidade") or "",
            cta_objetivo=job.get("cta_objetivo") or "",
        )
        print(f">>> JOB {job_id} SUCESSO {len(pngs)} slides", flush=True)
        ok = True
    except BaseException as e:
        import traceback as _tb
        erro_msg = _tb.format_exc()
        print(f">>> JOB {job_id} ERRO: {e}\n{erro_msg}", flush=True)
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            (pasta / "error.txt").write_text(erro_msg, encoding="utf-8")
        except Exception as we:
            print(f">>> erro ao salvar error.txt: {we}", flush=True)

    # Atualiza banco em bloco separado para garantir commit
    try:
        db = get_db()
        if ok:
            # Tenta ler legenda do metadata.json
            legenda_post = ""
            try:
                import json as _json2
                meta_path = pasta / "metadata.json"
                if meta_path.exists():
                    meta = _json2.loads(meta_path.read_text(encoding="utf-8"))
                    legenda_post = meta.get("legenda_instagram", "")
            except Exception:
                pass
            import secrets as _secrets
            share_token = _secrets.token_urlsafe(16)
            db.execute(
                "UPDATE carrosseis SET status='pronto', pasta_path=?, legenda_post=?, share_token=? WHERE id=?",
                (str(pasta), legenda_post, share_token, job_id)
            )
            logger.info("Job %s marcado como pronto", job_id)
            # Auto-email após geração
            try:
                user_row = db.execute("SELECT email FROM users WHERE id=?", (user_id,)).fetchone()
                if user_row and user_row["email"]:
                    import asyncio as _asyncio
                    from app.email_sender import criar_zip as _criar_zip, enviar_email_zip as _enviar_email_zip
                    _asyncio.create_task(
                        _asyncio.to_thread(_enviar_email_zip, user_row["email"], _criar_zip(pasta), job_id)
                    )
            except Exception as mail_err:
                logger.warning("Auto-email falhou job_id=%s: %s", job_id, mail_err)
        else:
            db.execute("UPDATE carrosseis SET status='erro' WHERE id=?", (job_id,))
            db.execute(
                "INSERT INTO credit_events (user_id, delta, motivo, ref_id) VALUES (?,1,'reembolso',?)",
                (user_id, str(job_id))
            )
            logger.info("Job %s erro, crédito reembolsado. Traceback: %s", job_id, erro_msg)
        db.commit()
        db.close()
    except Exception as db_err:
        logger.error("Erro ao salvar status job_id=%s: %s", job_id, db_err, exc_info=True)

# ── Job status e download ──────────────────────────────────────────
@app.post("/job/{job_id}/regenerar")
def job_regenerar(job_id: int, background_tasks: BackgroundTasks, user_id: int = Depends(usuario_atual)):
    db = get_db()
    job = db.execute("SELECT * FROM carrosseis WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    if not job:
        db.close()
        raise HTTPException(status_code=404)
    if job["status"] not in ("erro", "pendente"):
        db.close()
        raise HTTPException(status_code=400, detail="Só é possível regenerar carrosseis com erro.")
    # Cobra 1 crédito
    saldo = db.execute(
        "SELECT COALESCE(SUM(delta),0) AS s FROM credit_events WHERE user_id=?", (user_id,)
    ).fetchone()["s"]
    if saldo <= 0:
        db.close()
        raise HTTPException(status_code=402, detail="Sem créditos.")
    db.execute("INSERT INTO credit_events (user_id, delta, motivo, ref_id) VALUES (?,?,?,?)",
               (user_id, -1, "regenerar", str(job_id)))
    db.execute("UPDATE carrosseis SET status='gerando' WHERE id=?", (job_id,))
    db.commit()
    job_dict = dict(job)
    db.close()
    background_tasks.add_task(_executar_job, job_id, user_id, job_dict)
    return {"ok": True, "job_id": job_id}

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
    # Sanitiza filename — só permite slide_NN.png
    import re as _re
    if not _re.match(r'^slide_\d{2}\.png$', filename):
        raise HTTPException(status_code=400, detail="Filename inválido")
    db = get_db()
    job = db.execute("SELECT pasta_path FROM carrosseis WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    db.close()
    if not job:
        raise HTTPException(status_code=404)
    pasta = Path(job["pasta_path"]).resolve()
    path = (pasta / filename).resolve()
    # Double-check: path deve estar dentro da pasta do job
    try:
        path.relative_to(pasta)
    except ValueError:
        raise HTTPException(status_code=400, detail="Filename inválido")
    if not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(str(path), media_type="image/png")

@app.get("/job/{job_id}/conteudo")
def job_conteudo(job_id: int, user_id: int = Depends(usuario_atual)):
    """Retorna o metadata.json do carrossel (slides + accent + template)."""
    db = get_db()
    job = db.execute("SELECT pasta_path, user_id FROM carrosseis WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    db.close()
    if not job:
        raise HTTPException(status_code=404)
    meta_path = Path(job["pasta_path"]) / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Metadados não encontrados")
    import json as _json
    return _json.loads(meta_path.read_text(encoding="utf-8"))


@app.get("/job/{job_id}/share-token")
def job_share_token(job_id: int, user_id: int = Depends(usuario_atual)):
    """Retorna (ou cria) o share_token do carrossel."""
    import secrets as _secrets
    db = get_db()
    job = db.execute(
        "SELECT status, share_token FROM carrosseis WHERE id=? AND user_id=?", (job_id, user_id)
    ).fetchone()
    if not job or job["status"] != "pronto":
        db.close()
        raise HTTPException(status_code=404)
    token = job["share_token"]
    if not token:
        token = _secrets.token_urlsafe(16)
        db.execute("UPDATE carrosseis SET share_token=? WHERE id=?", (token, job_id))
        db.commit()
    db.close()
    app_url = os.getenv("APP_URL", "https://appcarrossel.bemkt.com.br")
    return {"token": token, "url": f"{app_url}/share/{token}"}


# ── Rotas públicas de compartilhamento (sem autenticação) ──────────
@app.get("/share/{token}")
def share_page(token: str):
    """Página pública de visualização do carrossel."""
    return FileResponse(os.path.join(static_dir, "share.html"))


@app.get("/share/{token}/info")
def share_info(token: str):
    """Metadados públicos do carrossel compartilhado."""
    import re as _re
    if not _re.match(r'^[A-Za-z0-9_\-]{10,30}$', token):
        raise HTTPException(status_code=400)
    db = get_db()
    job = db.execute(
        "SELECT id, tema, pasta_path, legenda_post FROM carrosseis WHERE share_token=? AND status='pronto'",
        (token,)
    ).fetchone()
    db.close()
    if not job:
        raise HTTPException(status_code=404)
    pasta = Path(job["pasta_path"])
    pngs  = sorted(pasta.glob("slide_*.png"))
    # Read hashtags from metadata.json if available
    hashtags = []
    meta_path = pasta / "metadata.json"
    if meta_path.exists():
        import json as _json
        try:
            meta = _json.loads(meta_path.read_text(encoding="utf-8"))
            hashtags = meta.get("hashtags") or []
        except Exception:
            pass
    return {
        "tema":      job["tema"] or "",
        "legenda":   job["legenda_post"] or "",
        "slides":    [p.name for p in pngs],
        "hashtags":  hashtags,
    }


@app.get("/share/{token}/slide/{filename}")
def share_slide(token: str, filename: str):
    """Serve slide PNG para visualização pública."""
    import re as _re
    if not _re.match(r'^[A-Za-z0-9_\-]{10,30}$', token):
        raise HTTPException(status_code=400)
    if not _re.match(r'^slide_\d{2}\.png$', filename):
        raise HTTPException(status_code=400)
    db = get_db()
    job = db.execute(
        "SELECT pasta_path FROM carrosseis WHERE share_token=? AND status='pronto'", (token,)
    ).fetchone()
    db.close()
    if not job:
        raise HTTPException(status_code=404)
    pasta = Path(job["pasta_path"]).resolve()
    path  = (pasta / filename).resolve()
    try:
        path.relative_to(pasta)
    except ValueError:
        raise HTTPException(status_code=400)
    if not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(str(path), media_type="image/png")


@app.post("/job/{job_id}/slide/{num}/reeditar")
async def reeditar_slide(job_id: int, num: int, data: dict, user_id: int = Depends(usuario_atual)):
    """Atualiza campos de um slide e re-renderiza apenas aquele PNG."""
    import json as _json
    from app.carousel import gerar_html_slide, _render_slide_async

    db = get_db()
    job = db.execute("SELECT * FROM carrosseis WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    db.close()
    if not job:
        raise HTTPException(status_code=404)

    pasta = Path(job["pasta_path"])
    meta_path = pasta / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Metadados não encontrados")

    meta = _json.loads(meta_path.read_text(encoding="utf-8"))
    slides = meta.get("slides", [])

    slide_idx = next((i for i, s in enumerate(slides) if s.get("numero") == num), None)
    if slide_idx is None:
        raise HTTPException(status_code=404, detail="Slide não encontrado")

    # Atualiza apenas os campos permitidos
    slide = dict(slides[slide_idx])
    for field in ["titulo", "corpo", "lista", "dado_destaque", "cta", "titulo_highlight", "categoria_label"]:
        if field in data:
            slide[field] = data[field]
    slides[slide_idx] = slide
    meta["slides"] = slides
    meta_path.write_text(_json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Monta parâmetros de renderização
    template  = meta.get("template", "4")
    accent    = meta.get("accent", "#8CFF2E")
    accent2   = meta.get("accent2", "#ff6a00")
    tema      = meta.get("tema", "")
    username  = job["username_slide"] or ""
    logo_url  = None
    if job["logo_path"] and Path(job["logo_path"]).exists():
        logo_url = f"file:///{job['logo_path'].replace(chr(92), '/')}"

    img_local = ""
    img_path = pasta / f"img_{num:02d}.jpg"
    if img_path.exists():
        img_local = str(img_path)

    html_content = gerar_html_slide(
        slide, len(slides), tema,
        accent, accent2, img_local, logo_url, username, template
    )
    pasta_html = pasta / "html"
    pasta_html.mkdir(exist_ok=True)
    html_path = pasta_html / f"slide_{num:02d}.html"
    html_path.write_text(html_content, encoding="utf-8")

    png_path = pasta / f"slide_{num:02d}.png"
    await _render_slide_async(str(html_path.absolute()), str(png_path))

    return {"ok": True, "slide": num}


@app.post("/job/{job_id}/email")
def job_email(job_id: int, data: EmailIn, request: Request, user_id: int = Depends(usuario_atual)):
    rate_limit(request, max_requests=3, window_seconds=300, scope="email")
    db = get_db()
    job = db.execute("SELECT status, pasta_path FROM carrosseis WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    db.close()
    if not job or job["status"] != "pronto":
        raise HTTPException(status_code=404)
    pasta = Path(job["pasta_path"])
    zip_path = criar_zip(pasta)
    try:
        enviar_email_zip(data.email, zip_path, job_id)
    except Exception:
        logger.error("Falha ao enviar email job_id=%s", job_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Falha ao enviar email. Tente novamente.")
    return {"ok": True}

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

# ── Legenda do post ───────────────────────────────────────────────
@app.get("/job/{job_id}/legenda")
def job_legenda(job_id: int, user_id: int = Depends(usuario_atual)):
    db = get_db()
    job = db.execute(
        "SELECT legenda_post, status FROM carrosseis WHERE id=? AND user_id=?",
        (job_id, user_id)
    ).fetchone()
    db.close()
    if not job or job["status"] != "pronto":
        raise HTTPException(status_code=404)
    return {"legenda": job["legenda_post"] or ""}

# ── Editor Manual ─────────────────────────────────────────────────
class EditorSlideIn(BaseModel):
    numero: int
    tipo: str = "conteudo"
    titulo: str = ""
    titulo_highlight: str = ""
    corpo: str = ""
    categoria_label: str = ""
    dado_destaque: str = ""
    cta: str = ""

class EditorIn(BaseModel):
    slides: list[EditorSlideIn]
    plataforma: str = "1"
    modelo: str = "4"
    tema: str = ""
    nicho: str = ""
    cores_marca: str = ""
    username: str = ""
    finalidade: str = ""
    cta_objetivo: str = ""
    usar_foto: bool = True


@app.post("/editor/sugestoes")
async def editor_sugestoes(data: dict, user_id: int = Depends(usuario_atual)):
    from app.carousel import construir_prompt, _gerar_conteudo_sync, parse_json_resposta
    tema = (data.get("tema") or "").strip()
    if not tema:
        raise HTTPException(status_code=400, detail="Tema obrigatório")
    _PLAT_MAP = {"1": "Instagram", "2": "LinkedIn", "3": "TikTok", "4": "X (Twitter)"}
    plataforma = _PLAT_MAP.get(data.get("plataforma", "1"), "Instagram")
    prompt = construir_prompt(
        tema=tema,
        plataforma=plataforma,
        nicho=data.get("nicho", ""),
        restricoes="",
        cores_marca=data.get("cores_marca", ""),
        template=data.get("modelo", "4"),
        username=data.get("username", ""),
        finalidade=data.get("finalidade", ""),
        cta_objetivo=data.get("cta_objetivo", ""),
    )
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    resposta = await asyncio.to_thread(_gerar_conteudo_sync, api_key, prompt)
    dados = parse_json_resposta(resposta)
    return {"slides": dados.get("slides", [])}

    @field_validator("tema")
    @classmethod
    def _tema(cls, v: str) -> str:
        return v.strip()[:500]

    @field_validator("nicho")
    @classmethod
    def _nicho(cls, v: str) -> str:
        return v.strip()[:200]

@app.post("/editor/gerar")
def editor_gerar(
    data: EditorIn,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(usuario_atual),
):
    _PLAT_MAP = {"1": "Instagram", "2": "LinkedIn", "3": "TikTok", "4": "X (Twitter)"}
    db = get_db()

    # Verifica créditos
    db.execute("BEGIN IMMEDIATE")
    try:
        creditos = db.execute(
            "SELECT COALESCE(SUM(delta),0) FROM credit_events WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        if creditos <= 0:
            db.execute("ROLLBACK")
            db.close()
            raise HTTPException(status_code=402, detail="Sem créditos")

        # Cria job manual
        import json as _json
        conteudo = _json.dumps(
            [s.model_dump() for s in data.slides], ensure_ascii=False
        )
        db.execute(
            """INSERT INTO carrosseis
               (user_id, tema, nicho, plataforma, modelo, cores_marca, username_slide,
                finalidade, cta_objetivo, conteudo_manual, modo, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,'manual','gerando')""",
            (user_id, data.tema, data.nicho, data.plataforma, data.modelo,
             data.cores_marca, data.username, data.finalidade, data.cta_objetivo, conteudo)
        )
        job_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute(
            "INSERT INTO credit_events (user_id, delta, motivo) VALUES (?,?,'uso')",
            (user_id, -1)
        )
        db.execute("COMMIT")
    except HTTPException:
        raise
    except Exception:
        db.execute("ROLLBACK")
        db.close()
        raise

    db.close()

    plataforma_str = _PLAT_MAP.get(data.plataforma, "Instagram")
    pasta = CARROSSEIS_DIR / str(user_id) / str(job_id)

    background_tasks.add_task(
        _executar_job_manual, job_id, user_id,
        [s.model_dump() for s in data.slides],
        plataforma_str, data.tema, data.nicho,
        data.cores_marca, data.username,
        data.modelo, data.finalidade, data.cta_objetivo,
        pasta, data.usar_foto,
    )
    return {"job_id": job_id, "status": "gerando"}


async def _executar_job_manual(
    job_id: int, user_id: int,
    slides_input: list[dict],
    plataforma: str, tema: str, nicho: str,
    cores_marca: str, username: str,
    template: str, finalidade: str, cta_objetivo: str,
    pasta: Path, usar_foto: bool = True,
):
    print(f"\n>>> JOB MANUAL {job_id} INICIADO tema={tema}", flush=True)
    ok = False
    legenda_post = ""
    try:
        pngs, legenda_post = await gerar_carrossel_manual(
            slides_input=slides_input,
            plataforma=plataforma,
            tema=tema,
            nicho=nicho,
            cores_marca=cores_marca,
            logo_path=None,
            username=username,
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            pexels_key=os.getenv("PEXELS_API_KEY", ""),
            pasta_destino=pasta,
            template=template,
            finalidade=finalidade,
            cta_objetivo=cta_objetivo,
            usar_foto=usar_foto,
        )
        print(f">>> JOB MANUAL {job_id} SUCESSO {len(pngs)} slides", flush=True)
        ok = True
    except BaseException as e:
        import traceback as _tb
        print(f">>> JOB MANUAL {job_id} ERRO: {e}\n{_tb.format_exc()}", flush=True)

    try:
        db = get_db()
        if ok:
            import secrets as _secrets
            share_token = _secrets.token_urlsafe(16)
            db.execute(
                "UPDATE carrosseis SET status='pronto', pasta_path=?, legenda_post=?, share_token=? WHERE id=?",
                (str(pasta), legenda_post, share_token, job_id)
            )
            logger.info("Job manual %s marcado como pronto", job_id)
            try:
                user_row = db.execute("SELECT email FROM users WHERE id=?", (user_id,)).fetchone()
                if user_row and user_row["email"]:
                    import asyncio as _asyncio
                    from app.email_sender import criar_zip as _criar_zip, enviar_email_zip as _enviar_email_zip
                    _asyncio.create_task(
                        _asyncio.to_thread(_enviar_email_zip, user_row["email"], _criar_zip(pasta), job_id)
                    )
            except Exception as mail_err:
                logger.warning("Auto-email falhou job_id=%s: %s", job_id, mail_err)
        else:
            db.execute("UPDATE carrosseis SET status='erro' WHERE id=?", (job_id,))
            db.execute(
                "INSERT INTO credit_events (user_id, delta, motivo, ref_id) VALUES (?,1,'reembolso',?)",
                (user_id, str(job_id))
            )
        db.commit()
        db.close()
    except Exception as db_err:
        logger.error("Erro ao salvar status job manual %s: %s", job_id, db_err, exc_info=True)

@app.get("/static/editor.html")
def editor_page():
    return FileResponse(os.path.join(static_dir, "editor.html"))

# ── Pagamentos ────────────────────────────────────────────────────
@app.get("/planos")
def listar_planos():
    return PLANOS

@app.post("/pagamento/criar")
def pagamento_criar(data: PagamentoIn, user_id: int = Depends(usuario_atual)):
    if data.plano not in PLANOS:
        raise HTTPException(status_code=400, detail="Plano inválido")
    plano = PLANOS[data.plano]
    db = get_db()
    db.execute(
        "INSERT INTO pagamentos (user_id, plano, valor, creditos_comprados) VALUES (?,?,?,?)",
        (user_id, data.plano, plano["valor"], plano["creditos"])
    )
    db.commit()
    pag_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.close()
    try:
        init_point = criar_preferencia_mp(pag_id, data.plano)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro Mercado Pago: {e}")
    return {"init_point": init_point}

@app.post("/webhook/mercadopago")
async def webhook_mp(request: Request):
    corpo = await request.body()
    if len(corpo) > 64 * 1024:  # 64KB max
        raise HTTPException(status_code=413, detail="Payload muito grande")
    sig = request.headers.get("x-signature", "")
    # Sempre valida se o secret estiver configurado (não permite bypass)
    if not MP_WEBHOOK_SECRET:
        logger.error("MP_WEBHOOK_SECRET não configurado — webhook rejeitado")
        raise HTTPException(status_code=503, detail="Webhook não configurado")
    if not validar_assinatura_webhook(sig, corpo, MP_WEBHOOK_SECRET):
        logger.warning("Webhook MP com assinatura inválida ip=%s", request.client.host if request.client else "?")
        raise HTTPException(status_code=400, detail="Assinatura inválida")
    import json as _json
    payload = _json.loads(corpo)
    mp_id = str(payload.get("data", {}).get("id", "") or payload.get("id", ""))
    if not mp_id:
        return {"ok": True}
    db = get_db()
    pag = db.execute("SELECT * FROM pagamentos WHERE mp_payment_id=?", (mp_id,)).fetchone()
    if pag:  # idempotente — já processado
        db.close()
        return {"ok": True}
    # Busca external_reference via API do MP (não vem no corpo do webhook)
    try:
        from app.pagamentos import MP_ACCESS_TOKEN
        import mercadopago as _mp
        sdk = _mp.SDK(MP_ACCESS_TOKEN)
        mp_payment = sdk.payment().get(mp_id)
        ext_ref = str(mp_payment.get("response", {}).get("external_reference", ""))
    except Exception:
        db.close()
        return {"ok": True}
    if not ext_ref:
        db.close()
        return {"ok": True}
    pag = db.execute("SELECT * FROM pagamentos WHERE id=? AND status='pendente'", (ext_ref,)).fetchone()
    if not pag:
        db.close()
        return {"ok": True}
    db.execute("UPDATE pagamentos SET status='aprovado', mp_payment_id=? WHERE id=?", (mp_id, pag["id"]))
    db.execute(
        "INSERT INTO credit_events (user_id, delta, motivo, ref_id) VALUES (?,?,'compra',?)",
        (pag["user_id"], pag["creditos_comprados"], str(pag["id"]))
    )
    db.commit()
    db.close()
    return {"ok": True}

# ══════════════════════════════════════════════════════════════════
# ADMIN — todos os endpoints exigem is_admin=1 no banco
# ══════════════════════════════════════════════════════════════════

class CreditoIn(BaseModel):
    user_id: int
    delta: int
    motivo: str = "admin"

class BloqueioIn(BaseModel):
    user_id: int
    bloquear: bool  # True = bloquear, False = desbloquear

@app.get("/admin/stats")
def admin_stats(_: int = Depends(admin_atual)):
    db = get_db()
    stats = {
        "usuarios":     db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "carrosseis":   db.execute("SELECT COUNT(*) FROM carrosseis").fetchone()[0],
        "prontos":      db.execute("SELECT COUNT(*) FROM carrosseis WHERE status='pronto'").fetchone()[0],
        "gerando":      db.execute("SELECT COUNT(*) FROM carrosseis WHERE status='gerando'").fetchone()[0],
        "erros":        db.execute("SELECT COUNT(*) FROM carrosseis WHERE status='erro'").fetchone()[0],
        "receita":      db.execute("SELECT COALESCE(SUM(valor),0) FROM pagamentos WHERE status='aprovado'").fetchone()[0],
        "pag_aprovados":db.execute("SELECT COUNT(*) FROM pagamentos WHERE status='aprovado'").fetchone()[0],
        "creditos_usados": abs(db.execute("SELECT COALESCE(SUM(delta),0) FROM credit_events WHERE delta<0").fetchone()[0]),
    }
    db.close()
    return stats

@app.get("/admin/usuarios")
def admin_usuarios(_: int = Depends(admin_atual)):
    db = get_db()
    rows = db.execute("""
        SELECT u.id, u.nome, u.email, u.username, u.is_admin, u.bloqueado_ate, u.criado_em,
               COALESCE(SUM(ce.delta),0) AS creditos,
               COUNT(DISTINCT c.id) AS carrosseis
        FROM users u
        LEFT JOIN credit_events ce ON ce.user_id = u.id
        LEFT JOIN carrosseis c ON c.user_id = u.id
        GROUP BY u.id
        ORDER BY u.criado_em DESC
        LIMIT 200
    """).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.get("/admin/carrosseis")
def admin_carrosseis(_: int = Depends(admin_atual)):
    db = get_db()
    rows = db.execute("""
        SELECT c.id, c.user_id, u.email, c.tema, c.plataforma, c.modelo,
               c.status, c.criado_em
        FROM carrosseis c
        JOIN users u ON u.id = c.user_id
        ORDER BY c.criado_em DESC
        LIMIT 300
    """).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.get("/admin/pagamentos")
def admin_pagamentos(_: int = Depends(admin_atual)):
    db = get_db()
    rows = db.execute("""
        SELECT p.id, u.email, p.plano, p.valor, p.creditos_comprados,
               p.status, p.mp_payment_id, p.criado_em
        FROM pagamentos p
        JOIN users u ON u.id = p.user_id
        ORDER BY p.criado_em DESC
        LIMIT 300
    """).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.post("/admin/creditos")
def admin_creditos(data: CreditoIn, _: int = Depends(admin_atual)):
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE id=?", (data.user_id,)).fetchone()
    if not user:
        db.close()
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    db.execute(
        "INSERT INTO credit_events (user_id, delta, motivo) VALUES (?,?,?)",
        (data.user_id, data.delta, data.motivo[:100])
    )
    db.commit()
    creditos = creditos_disponiveis(data.user_id, db)
    db.close()
    logger.info("Admin ajustou créditos user_id=%s delta=%s motivo=%s", data.user_id, data.delta, data.motivo)
    return {"ok": True, "creditos": creditos}

@app.post("/admin/bloqueio")
def admin_bloqueio(data: BloqueioIn, _: int = Depends(admin_atual)):
    db = get_db()
    if data.bloquear:
        db.execute(
            "UPDATE users SET bloqueado_ate=datetime('now','+10 years') WHERE id=?",
            (data.user_id,)
        )
    else:
        db.execute("UPDATE users SET bloqueado_ate=NULL WHERE id=?", (data.user_id,))
    db.commit()
    db.close()
    logger.info("Admin %s user_id=%s", "bloqueou" if data.bloquear else "desbloqueou", data.user_id)
    return {"ok": True}

@app.get("/admin")
def admin_page():
    return FileResponse(os.path.join(static_dir, "admin.html"))


# ── Template Exclusivo endpoints ──────────────────────────────────

@app.post("/pedido-template")
async def pedido_template(
    background_tasks: BackgroundTasks,
    plano: str = Form(...),
    valor: float = Form(...),
    briefing_nome: str = Form(""),
    briefing_nicho: str = Form(""),
    briefing_username: str = Form(""),
    briefing_cores: str = Form(""),
    briefing_fontes: str = Form(""),
    briefing_estilo: str = Form(""),
    briefing_refs_texto: str = Form(""),
    briefing_obs: str = Form(""),
    refs: list[UploadFile] = File(default=[]),
    user_id: int = Depends(usuario_atual),
):
    """Recebe briefing pós-compra e cria pedido de template exclusivo."""
    plano_s = plano if plano in {"starter", "pro", "agency"} else "starter"
    valor_f = round(float(valor), 2)

    # Salva arquivos de referência
    refs_paths = []
    for i, arquivo in enumerate(refs[:5]):  # máx 5 arquivos
        if not arquivo.filename:
            continue
        conteudo = await arquivo.read()
        if len(conteudo) > 10 * 1024 * 1024:  # 10MB por arquivo
            continue
        ext = Path(arquivo.filename).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"}:
            continue
        nome = f"ref_{user_id}_{int(__import__('time').time())}_{i}{ext}"
        caminho = REFS_DIR / nome
        caminho.write_bytes(conteudo)
        refs_paths.append(str(caminho))

    briefing_obs_s = sanitizar_texto(briefing_obs, 2000)
    briefing_estilo_s = sanitizar_texto(briefing_estilo, 2000)
    briefing_refs_s = sanitizar_texto(briefing_refs_texto, 1000)

    db = get_db()
    db.execute(
        """INSERT INTO pedidos_template
           (user_id, plano, valor, status, briefing_nome, briefing_cores,
            briefing_fontes, briefing_nicho, briefing_username, briefing_obs, refs_paths)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (user_id, plano_s, valor_f, "aguardando_producao",
         sanitizar_texto(briefing_nome, 200),
         sanitizar_texto(briefing_cores, 200),
         sanitizar_texto(briefing_fontes, 100),
         sanitizar_texto(briefing_nicho, 200),
         sanitizar_texto(briefing_username, 60),
         briefing_estilo_s + "\n" + briefing_refs_s + "\n" + briefing_obs_s,
         json.dumps(refs_paths))
    )
    pedido_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    user = db.execute("SELECT nome, email FROM users WHERE id=?", (user_id,)).fetchone()
    db.commit()
    db.close()

    # Notifica admin
    background_tasks.add_task(
        _notificar_pedido_template, pedido_id, dict(user), plano_s, valor_f
    )

    logger.info("Pedido template #%s user_id=%s plano=%s", pedido_id, user_id, plano_s)
    return {"ok": True, "pedido_id": pedido_id}


async def _notificar_pedido_template(pedido_id: int, user: dict, plano: str, valor: float):
    try:
        from app.email_sender import enviar_email
        corpo = f"""
        <h2>Novo pedido de template exclusivo #{pedido_id}</h2>
        <p><b>Cliente:</b> {user.get('nome')} ({user.get('email')})</p>
        <p><b>Plano:</b> {plano.title()} — R${valor:.2f}</p>
        <p>Acesse o painel admin para ver o briefing completo.</p>
        """
        enviar_email("bruno@bemkt.com.br", f"[BeContent] Novo pedido template #{pedido_id}", corpo)
    except Exception as e:
        logger.error("Erro ao notificar pedido template: %s", e)


@app.get("/admin/pedidos-template")
def admin_pedidos_template(_: int = Depends(admin_atual)):
    """Lista todos os pedidos de template exclusivo para o admin."""
    db = get_db()
    rows = db.execute(
        """SELECT pt.*, u.nome as user_nome, u.email as user_email
           FROM pedidos_template pt
           JOIN users u ON u.id = pt.user_id
           ORDER BY pt.criado_em DESC"""
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


@app.post("/admin/pedidos-template/{pedido_id}/status")
def admin_atualizar_status_template(
    pedido_id: int,
    status: str = Form(...),
    _: int = Depends(admin_atual),
):
    """Atualiza status de um pedido (aguardando_briefing/aguardando_producao/entregue)."""
    status_s = status if status in {"aguardando_briefing", "aguardando_producao", "em_producao", "entregue"} else "em_producao"
    db = get_db()
    db.execute(
        "UPDATE pedidos_template SET status=?, entregue_em=CASE WHEN ?='entregue' THEN CURRENT_TIMESTAMP ELSE entregue_em END WHERE id=?",
        (status_s, status_s, pedido_id)
    )
    db.commit()
    db.close()
    return {"ok": True}

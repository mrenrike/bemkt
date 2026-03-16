# Agência IA Web App — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Web app self-service onde clientes se cadastram, passam por chat guiado de 6 perguntas e recebem carrosséis 1080×1080px prontos para postar, com pagamento via Mercado Pago.

**Architecture:** FastAPI backend serving HTML/JS/CSS frontend, SQLite para dados, Playwright para render dos slides via extração do agencia_v2.py. Chat guiado de 6 perguntas armazena estado em `carrosseis` table. Créditos em ledger append-only.

**Tech Stack:** Python 3.14, FastAPI, uvicorn, SQLite, python-jose (JWT), passlib[bcrypt], Playwright, mercadopago SDK, smtplib, python-multipart, aiofiles, python-dotenv

---

## File Map

| File | Responsabilidade |
|------|-----------------|
| `app/database.py` | Conexão SQLite + criação de tabelas |
| `app/auth.py` | Hash de senha, geração/validação JWT, dependência FastAPI |
| `app/chat.py` | Estado do chat (6 perguntas), lógica de skip, resumo |
| `app/carousel.py` | Funções extraídas do agencia_v2.py + wrapper async |
| `app/pagamentos.py` | SDK Mercado Pago: criar preferência, validar webhook |
| `app/email_sender.py` | Criar ZIP dos PNGs, enviar por smtplib |
| `app/main.py` | FastAPI app, todos os endpoints, startup hook, serve static |
| `app/static/style.css` | Tema dark compartilhado entre todas as páginas |
| `app/static/index.html` | Login + cadastro |
| `app/static/chat.html` | Interface de chat guiado |
| `app/static/loading.html` | Polling de status com barra de progresso |
| `app/static/preview.html` | Grid dos 7 slides + download ZIP + campo email |
| `app/static/planos.html` | Seleção de plano + redirect para Mercado Pago |
| `app/static/conta.html` | Histórico de carrosséis e pagamentos |
| `tests/test_auth.py` | Testes de hash, JWT, endpoints de auth |
| `tests/test_chat.py` | Testes da máquina de estados do chat |
| `tests/test_carousel.py` | Testes do prompt builder e parse de JSON |
| `tests/test_pagamentos.py` | Testes do webhook handler |
| `requirements.txt` | Dependências do projeto |
| `.env.example` | Template de variáveis de ambiente |

---

## Chunk 1: Setup, Banco de Dados e Auth

### Task 1: Setup do projeto e dependências

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Criar requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
bcrypt==3.2.2
python-multipart==0.0.9
aiofiles==23.2.1
python-dotenv==1.0.1
mercadopago==2.2.2
anthropic==0.84.0
playwright==1.58.0
pytest==8.3.0
pytest-asyncio==0.23.0
httpx==0.27.0
```

- [ ] **Step 2: Criar .env.example**

```
ANTHROPIC_API_KEY=sk-ant-...
PEXELS_API_KEY=...
MP_ACCESS_TOKEN=TEST-...
MP_WEBHOOK_SECRET=...
JWT_SECRET=troque-por-string-aleatoria-longa
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=seu@email.com
EMAIL_PASSWORD=sua-senha-de-app
```

- [ ] **Step 3: Instalar dependências**

```bash
cd ~/agencia-ia
pip install -r requirements.txt
python -m playwright install chromium
```

Esperado: instalação sem erros; última linha do playwright: "Chromium ... downloaded to ...".

- [ ] **Step 4: Criar app/__init__.py e tests/__init__.py vazios**

```bash
touch app/__init__.py tests/__init__.py
```

- [ ] **Step 5: Criar tests/conftest.py**

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, get_db
import sqlite3, os, tempfile

@pytest.fixture(autouse=True)
def test_db(tmp_path, monkeypatch):
    """Banco de dados isolado para cada teste."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    init_db(db_path)
    yield db_path

@pytest.fixture
def client():
    return TestClient(app)
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .env.example app/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore: project setup and dependencies"
```

---

### Task 2: Banco de dados

**Files:**
- Create: `app/database.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Escrever testes**

```python
# tests/test_database.py
import sqlite3
from app.database import init_db, get_db

def test_init_creates_all_tables(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert tables == {"users", "credit_events", "carrosseis", "pagamentos"}
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
```

- [ ] **Step 2: Rodar testes para confirmar falha**

```bash
pytest tests/test_database.py -v
```

Esperado: `ModuleNotFoundError: No module named 'app.database'`

- [ ] **Step 3: Implementar app/database.py**

```python
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
            username_slide TEXT,   -- @handle para marca d'água (distinto de users.username)
            plataforma TEXT DEFAULT 'Instagram',  -- reservado para futuro suporte LinkedIn
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
```

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_database.py -v
```

Esperado: 2 testes PASS.

- [ ] **Step 5: Commit**

```bash
git add app/database.py tests/test_database.py
git commit -m "feat: database schema and helpers"
```

---

### Task 3: Auth (cadastro, login, JWT)

**Files:**
- Create: `app/auth.py`
- Create: `tests/test_auth.py`
- Create: `app/main.py` (esqueleto + endpoints de auth)

- [ ] **Step 1: Escrever testes de auth**

```python
# tests/test_auth.py
from app.auth import hash_senha, verificar_senha, criar_token, verificar_token

def test_hash_e_verifica_senha():
    h = hash_senha("minhasenha123")
    assert verificar_senha("minhasenha123", h)
    assert not verificar_senha("errada", h)

def test_token_round_trip():
    token = criar_token({"sub": "42"})
    payload = verificar_token(token)
    assert payload["sub"] == "42"

def test_token_invalido_retorna_none():
    assert verificar_token("token.invalido.aqui") is None
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_auth.py -v
```

Esperado: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implementar app/auth.py**

```python
import os
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 72

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer()

def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)

def verificar_senha(senha: str, hash: str) -> bool:
    return pwd_context.verify(senha, hash)

def criar_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)

def verificar_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return None

def usuario_atual(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> int:
    payload = verificar_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    return int(payload["sub"])
```

- [ ] **Step 4: Rodar testes de auth**

```bash
pytest tests/test_auth.py -v
```

Esperado: 3 testes PASS.

- [ ] **Step 5: Criar app/main.py com endpoints de auth**

```python
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
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def root():
    return FileResponse(os.path.join(static_dir, "index.html"))

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
```

- [ ] **Step 6: Escrever testes de integração dos endpoints**

```python
# Adicionar ao tests/test_auth.py
# O fixture `client` vem do conftest.py — não redefinir aqui (evita shadowing e perda de isolamento de DB)

def test_cadastro_cria_usuario_com_credito_trial(client):
    r = client.post("/auth/cadastro", json={
        "nome": "Ana", "email": "ana@test.com", "senha": "123456"
    })
    assert r.status_code == 200
    assert "token" in r.json()
    # verifica crédito trial
    token = r.json()["token"]
    me = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["creditos"] == 1

def test_login_retorna_token(client):
    client.post("/auth/cadastro", json={"nome": "Bob", "email": "bob@test.com", "senha": "abc123"})
    r = client.post("/auth/login", json={"email": "bob@test.com", "senha": "abc123"})
    assert r.status_code == 200
    assert "token" in r.json()

def test_login_senha_errada_retorna_401(client):
    client.post("/auth/cadastro", json={"nome": "Carol", "email": "carol@test.com", "senha": "certa"})
    r = client.post("/auth/login", json={"email": "carol@test.com", "senha": "errada"})
    assert r.status_code == 401

def test_me_sem_token_retorna_403(client):
    r = client.get("/me")
    assert r.status_code == 403
```

- [ ] **Step 7: Rodar todos os testes**

```bash
pytest tests/test_auth.py tests/test_database.py -v
```

Esperado: todos PASS.

- [ ] **Step 8: Commit**

```bash
git add app/auth.py app/main.py tests/test_auth.py
git commit -m "feat: auth endpoints (cadastro, login, JWT)"
```

---

## Chunk 2: Motor de Carrossel

### Task 4: Extrair funções do agencia_v2.py para carousel.py

**Files:**
- Create: `app/carousel.py`
- Create: `tests/test_carousel.py`

- [ ] **Step 1: Escrever testes**

```python
# tests/test_carousel.py
import pytest
from app.carousel import construir_prompt, parse_json_resposta, gerar_html_slide

def test_prompt_inclui_nicho_restricoes_e_cores():
    prompt = construir_prompt(
        tema="Marketing Digital",
        plataforma="Instagram",
        nicho="coaches de vida",
        restricoes="não mencionar concorrentes",
        cores_marca="#FF4D00 laranja vibrante"
    )
    assert "coaches de vida" in prompt
    assert "não mencionar concorrentes" in prompt
    assert "Marketing Digital" in prompt
    assert "#FF4D00 laranja vibrante" in prompt

def test_parse_json_resposta_extrai_slides():
    resposta = '''```json
{
  "titulo_serie": "Teste",
  "paleta": {"nome":"dark","bg":"#000","accent":"#fff","accent2":"#aaa","text":"#fff","overlay":"rgba(0,0,0,0.5)"},
  "hashtags": ["#test"],
  "melhor_horario": "19:00",
  "slides": [{"numero":1,"emoji":"🔥","titulo":"Titulo","texto":"Texto","query_imagem":"query"}]
}
```'''
    dados = parse_json_resposta(resposta)
    assert len(dados["slides"]) == 1
    assert dados["slides"][0]["titulo"] == "Titulo"

def test_parse_json_sem_backticks():
    import json
    dados_raw = {
        "titulo_serie": "T",
        "paleta": {"nome":"x","bg":"#000","accent":"#fff","accent2":"#aaa","text":"#fff","overlay":"x"},
        "hashtags": [],
        "melhor_horario": "18:00",
        "slides": []
    }
    dados = parse_json_resposta(json.dumps(dados_raw))
    assert dados["titulo_serie"] == "T"

PALETA_TESTE = {"bg":"#000","accent":"#FF0","accent2":"#F00","text":"#fff","overlay":"rgba(0,0,0,0.5)"}
SLIDE_TESTE = {"numero": 2, "emoji": "✨", "titulo": "Título", "texto": "Corpo do slide", "query_imagem": "q"}

def test_gerar_html_slide_sem_logo_sem_username():
    html = gerar_html_slide(SLIDE_TESTE, 7, "Tema", PALETA_TESTE)
    assert "Título" in html
    assert "Corpo do slide" in html
    assert "<img" not in html       # sem logo
    assert 'class="marca"' in html  # div marca existe mesmo vazia

def test_gerar_html_slide_com_logo_e_username():
    html = gerar_html_slide(
        SLIDE_TESTE, 7, "Tema", PALETA_TESTE,
        logo_url="file:///path/logo.png",
        username="@testhandle"
    )
    assert 'src="file:///path/logo.png"' in html
    assert "@testhandle" in html
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_carousel.py -v
```

Esperado: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implementar app/carousel.py**

```python
import os, re, json, asyncio
from pathlib import Path
import urllib.request, urllib.parse
import anthropic

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

# ── Prompt builder ────────────────────────────────────────────────
def construir_prompt(tema: str, plataforma: str, nicho: str = "", restricoes: str = "", cores_marca: str = "") -> str:
    contexto_nicho = f"\nNicho/segmento da marca: {nicho}" if nicho else ""
    contexto_restricoes = f"\nRESTRIÇÕES — nunca mencione: {restricoes}" if restricoes else ""
    contexto_cores = f"\nIdentidade visual / cores da marca: {cores_marca}" if cores_marca else ""
    return f"""Você é um estrategista de conteúdo viral especializado em {plataforma}.
{contexto_nicho}{contexto_cores}{contexto_restricoes}

Crie um carrossel de 7 slides sobre: "{tema}"

Regras:
- Slide 1: gancho impossível de ignorar
- Slides 2-6: 1 insight poderoso por slide, linguagem brasileira direta
- Slide 7: CTA com urgência real
- Cada slide: texto de 3 a 5 linhas, rico em detalhes
- Escolha a paleta de cores que melhor reflita a identidade visual descrita

Para cada slide, sugira um "query_imagem" em INGLÊS para buscar no Pexels.

Responda APENAS JSON válido:
{{
  "titulo_serie": "...",
  "paleta": {{"nome":"...","bg":"#...","accent":"#...","accent2":"#...","text":"#fff","overlay":"linear-gradient(...)"}},
  "hashtags": ["..."],
  "melhor_horario": "19:00",
  "slides": [{{"numero":1,"emoji":"🔥","titulo":"...","texto":"...","query_imagem":"..."}}]
}}

Paletas por tom:
- Urgente/impacto: accent #FF4D00, bg #0a0a0a
- Premium/luxo: accent #C9A84C, bg #0d0d0d
- Tech/futuro: accent #00E5FF, bg #050510
- Growth/verde: accent #00E676, bg #071a0e"""

# ── JSON parser ───────────────────────────────────────────────────
def parse_json_resposta(resposta: str) -> dict:
    s = resposta.strip()
    if "```" in s:
        s = re.sub(r'```(?:json)?', '', s).strip()
    try:
        return json.loads(s)
    except Exception:
        match = re.search(r'\{.*\}', s, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError("Não foi possível parsear JSON da resposta do Claude.")

# ── Download de imagem ────────────────────────────────────────────
def baixar_imagem(query: str, destino: Path, pexels_key: str = "", width=1080, height=1080) -> str:
    headers = {"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0"}
    if pexels_key:
        try:
            q = urllib.parse.quote(query)
            req = urllib.request.Request(
                f"https://api.pexels.com/v1/search?query={q}&per_page=5&orientation=square",
                headers={**headers, "Authorization": pexels_key}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                fotos = json.loads(resp.read()).get("photos", [])
                if fotos:
                    req2 = urllib.request.Request(fotos[0]["src"]["large2x"], headers=headers)
                    with urllib.request.urlopen(req2, timeout=15) as r:
                        destino.write_bytes(r.read())
                    return str(destino.absolute())
        except Exception:
            pass
    seed = abs(hash(query)) % 1000
    req = urllib.request.Request(f"https://picsum.photos/seed/{seed}/{width}/{height}", headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        destino.write_bytes(r.read())
    return str(destino.absolute())

# ── HTML de slide ─────────────────────────────────────────────────
def gerar_html_slide(
    slide: dict,
    total: int,
    tema: str,
    paleta: dict,
    img_local: str = "",
    logo_url: str | None = None,
    username: str = "",
) -> str:
    num = slide.get("numero", 1)
    titulo = slide.get("titulo", "")
    texto = slide.get("texto", "")
    emoji = slide.get("emoji", "✦")
    is_capa = (num == 1)
    is_cta = (num == total)

    img_url = f"file:///{img_local.replace(chr(92), '/')}" if img_local else ""
    logo_tag = f'<img src="{logo_url}" style="max-width:160px;max-height:80px;object-fit:contain">' if logo_url else ""
    marca = username if username else ""
    accent = paleta["accent"]
    accent2 = paleta["accent2"]
    bg = paleta["bg"]
    text_color = paleta["text"]
    overlay = paleta["overlay"]

    if is_capa:
        corpo = f'<div class="slide-inner capa"><div class="num-badge">01 / {total:02d}</div><div class="emoji-big">{emoji}</div><h1 class="titulo-capa">{titulo}</h1><div class="subtema">{tema.upper()}</div><div class="bar-accent"></div></div>'
    elif is_cta:
        corpo = f'<div class="slide-inner cta"><div class="num-badge">{num:02d} / {total:02d}</div><div class="emoji-big">{emoji}</div><h2 class="titulo-cta">{titulo}</h2><p class="texto-cta">{texto}</p><div class="cta-pill">SALVA ✦ COMPARTILHA ✦ SEGUE</div></div>'
    else:
        corpo = f'<div class="slide-inner conteudo"><div class="num-badge">{num:02d} / {total:02d}</div><div class="tag-topo">{emoji} {tema.upper()}</div><h2 class="titulo-slide">{titulo}</h2><div class="divider-line"></div><p class="texto-slide">{texto}</p></div>'

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:1080px;height:1080px;overflow:hidden;font-family:'DM Sans',sans-serif;background:{bg};position:relative}}
.bg-img{{position:absolute;inset:0;background:url('{img_url}') center/cover no-repeat;filter:saturate(1.1) brightness(0.85)}}
.overlay{{position:absolute;inset:0;background:{overlay};opacity:0.62}}
.side-bar{{position:absolute;left:0;top:0;bottom:0;width:8px;background:linear-gradient(to bottom,{accent},{accent2})}}
.logo-area{{position:absolute;top:40px;left:52px}}
.marca{{position:absolute;bottom:40px;right:48px;font-family:'Bebas Neue',sans-serif;font-size:18px;color:rgba(255,255,255,0.35);letter-spacing:3px}}
.slide-inner{{position:absolute;inset:0;padding:72px 72px 72px 88px;display:flex;flex-direction:column;justify-content:center;color:{text_color}}}
.num-badge{{position:absolute;top:44px;right:52px;font-family:'Bebas Neue',sans-serif;font-size:16px;letter-spacing:3px;color:rgba(255,255,255,0.5)}}
.capa{{justify-content:flex-end;padding-bottom:100px}}
.emoji-big{{font-size:64px;margin-bottom:24px;filter:drop-shadow(0 4px 12px rgba(0,0,0,0.4))}}
.titulo-capa{{font-family:'Bebas Neue',sans-serif;font-size:96px;line-height:0.95;color:#fff;text-shadow:0 4px 24px rgba(0,0,0,0.5);margin-bottom:20px;max-width:800px}}
.subtema{{font-size:14px;letter-spacing:5px;color:{accent};font-weight:600;margin-bottom:24px}}
.bar-accent{{width:80px;height:4px;background:linear-gradient(90deg,{accent},{accent2});border-radius:2px}}
.tag-topo{{font-size:13px;letter-spacing:4px;color:{accent};font-weight:600;text-transform:uppercase;margin-bottom:28px}}
.titulo-slide{{font-family:'Bebas Neue',sans-serif;font-size:72px;line-height:1.0;color:#fff;text-shadow:0 2px 20px rgba(0,0,0,0.6);margin-bottom:24px;max-width:820px}}
.divider-line{{width:56px;height:3px;background:linear-gradient(90deg,{accent},{accent2});border-radius:2px;margin-bottom:28px}}
.texto-slide{{font-size:26px;line-height:1.65;color:rgba(255,255,255,0.92);max-width:820px;font-weight:400;text-shadow:0 2px 12px rgba(0,0,0,0.7)}}
.cta{{align-items:center;text-align:center;padding:80px}}
.titulo-cta{{font-family:'Bebas Neue',sans-serif;font-size:80px;color:#fff;line-height:1.0;margin-bottom:24px}}
.texto-cta{{font-size:26px;color:rgba(255,255,255,0.8);max-width:700px;line-height:1.6;margin-bottom:40px;font-weight:300}}
.cta-pill{{background:linear-gradient(135deg,{accent},{accent2});color:#fff;font-family:'Bebas Neue',sans-serif;font-size:22px;letter-spacing:4px;padding:18px 48px;border-radius:100px}}
</style></head><body>
<div class="bg-img"></div><div class="overlay"></div>
<div class="side-bar"></div>
<div class="logo-area">{logo_tag}</div>
{corpo}
<div class="marca">{marca}</div>
</body></html>"""

# ── Render PNG (sync — chamado via asyncio.to_thread) ─────────────
def _render_slide_sync(html_path: str, png_path: str):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1080})
        page.goto(f"file:///{html_path.replace(chr(92), '/')}")
        page.wait_for_timeout(1500)
        page.screenshot(path=png_path, full_page=False)
        browser.close()

# ── Claude sync helper (chamado via asyncio.to_thread) ────────────
def _gerar_conteudo_sync(api_key: str, prompt: str) -> str:
    """Anthropic SDK síncrono — sempre chamar via asyncio.to_thread()."""
    client = anthropic.Anthropic(api_key=api_key)
    resposta = ""
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    ) as stream:
        for text in stream.text_stream:
            resposta += text   # sem sys.stdout.write — contexto web
    return resposta

# ── Main async entry point ────────────────────────────────────────
async def gerar_carrossel(
    tema: str,
    plataforma: str,
    nicho: str,
    restricoes: str,
    cores_marca: str,
    logo_path: str | None,
    username: str,
    api_key: str,
    pexels_key: str,
    pasta_destino: Path,
) -> list[Path]:
    pasta_destino.mkdir(parents=True, exist_ok=True)
    pasta_html = pasta_destino / "html"
    pasta_html.mkdir(exist_ok=True)

    # Gera conteúdo via Claude (em thread para não bloquear o event loop)
    prompt = construir_prompt(tema, plataforma, nicho, restricoes, cores_marca)
    resposta = await asyncio.to_thread(_gerar_conteudo_sync, api_key, prompt)

    dados = parse_json_resposta(resposta)
    slides = dados.get("slides", [])
    paleta = dados.get("paleta", {
        "bg": "#0a0a0a", "accent": "#FF4D00", "accent2": "#FF8C42",
        "text": "#ffffff", "overlay": "linear-gradient(160deg,rgba(0,0,0,0.75) 0%,rgba(10,10,10,0.92) 100%)"
    })

    logo_url = None
    if logo_path and Path(logo_path).exists():
        logo_url = f"file:///{logo_path.replace(chr(92), '/')}"

    pngs = []
    for slide in slides:
        num = slide.get("numero", 1)
        query = slide.get("query_imagem", tema)

        img_path = pasta_destino / f"img_{num:02d}.jpg"
        img_local = ""
        try:
            img_local = await asyncio.to_thread(baixar_imagem, query, img_path, pexels_key)
        except Exception:
            pass

        html_content = gerar_html_slide(slide, len(slides), tema, paleta, img_local, logo_url, username)
        html_path = pasta_html / f"slide_{num:02d}.html"
        html_path.write_text(html_content, encoding="utf-8")

        png_path = pasta_destino / f"slide_{num:02d}.png"
        await asyncio.to_thread(_render_slide_sync, str(html_path.absolute()), str(png_path))
        pngs.append(png_path)

    # Salva metadata
    import json as _json
    (pasta_destino / "metadata.json").write_text(
        _json.dumps({"tema": tema, "paleta": paleta, "slides": slides}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return pngs
```

- [ ] **Step 4: Rodar testes do carousel**

```bash
pytest tests/test_carousel.py -v
```

Esperado: 5 testes PASS.

- [ ] **Step 5: Commit**

```bash
git add app/carousel.py tests/test_carousel.py
git commit -m "feat: carousel engine extracted from agencia_v2.py"
```

---

## Chunk 3: Chat Flow e Job API

### Task 5: Máquina de estados do chat

**Files:**
- Create: `app/chat.py`
- Create: `tests/test_chat.py`

- [ ] **Step 1: Escrever testes**

```python
# tests/test_chat.py
from app.chat import PERGUNTAS, proxima_pergunta, chat_completo, resumo_job

def test_primeira_pergunta_e_nicho():
    assert "nicho" in PERGUNTAS[0]["campo"]

def test_proxima_pergunta_apos_resposta():
    estado = {}
    p, done = proxima_pergunta(estado)
    assert not done
    assert p["campo"] == "nicho"

def test_chat_completo_apos_6_respostas():
    estado = {}
    campos = ["nicho", "tema", "logo_path", "cores_marca", "username_slide", "restricoes"]
    for campo in campos:
        estado[campo] = "resposta teste"
    _, done = proxima_pergunta(estado)
    assert done

def test_skip_opcional_nao_bloqueia():
    estado = {"nicho": "tech", "tema": "IA", "logo_path": "", "cores_marca": "azul"}
    # username e restricoes são opcionais — skip com string vazia
    estado["username_slide"] = ""
    estado["restricoes"] = ""
    _, done = proxima_pergunta(estado)
    assert done

def test_resumo_formata_dados():
    estado = {"nicho": "fitness", "tema": "treino", "logo_path": "", "cores_marca": "verde", "username_slide": "@gym", "restricoes": ""}
    r = resumo_job(estado)
    assert "fitness" in r
    assert "@gym" in r
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_chat.py -v
```

Esperado: FAIL

- [ ] **Step 3: Implementar app/chat.py**

```python
# app/chat.py

PERGUNTAS = [
    {
        "campo": "nicho",
        "texto": "Qual o nicho ou segmento da sua marca? (ex: fitness, moda, tecnologia, serviços)",
        "opcional": False,
    },
    {
        "campo": "tema",
        "texto": "Qual o tema do carrossel? Pode descrever o assunto ou colar um texto que já tem.",
        "opcional": False,
    },
    {
        "campo": "logo_path",
        "texto": "Tem logo para incluir nos slides? Envie o arquivo PNG/JPG/SVG (até 5MB) ou pressione Enter para pular.",
        "opcional": True,
        "upload": True,
    },
    {
        "campo": "cores_marca",
        "texto": "Quais são as cores da marca? Pode informar o código hex (#FF4D00), descrever (azul royal) ou enviar uma imagem de referência.",
        "opcional": False,
    },
    {
        "campo": "username_slide",
        "texto": "Qual o seu @ para aparecer nos slides? (ex: @baladaroyalle — Enter para pular)",
        "opcional": True,
    },
    {
        "campo": "restricoes",
        "texto": "Tem alguma palavra, concorrente ou assunto que NÃO pode aparecer? (Enter para pular)",
        "opcional": True,
    },
]

def proxima_pergunta(estado: dict) -> tuple[dict | None, bool]:
    """Retorna (próxima pergunta, chat_concluido)."""
    for p in PERGUNTAS:
        if p["campo"] not in estado:
            return p, False
    return None, True

def chat_completo(estado: dict) -> bool:
    _, done = proxima_pergunta(estado)
    return done

def resumo_job(estado: dict) -> str:
    linhas = ["📋 *Resumo do seu carrossel:*\n"]
    labels = {
        "nicho": "Nicho",
        "tema": "Tema",
        "logo_path": "Logo",
        "cores_marca": "Cores",
        "username_slide": "Username",
        "restricoes": "Restrições",
    }
    for campo, label in labels.items():
        val = estado.get(campo, "")
        if val:
            linhas.append(f"• *{label}:* {val}")
        elif campo in ["logo_path", "username_slide", "restricoes"]:
            linhas.append(f"• *{label}:* (não informado)")
    linhas.append("\nTudo certo? Digite *confirmar* para gerar o carrossel.")
    return "\n".join(linhas)
```

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_chat.py -v
```

Esperado: 5 testes PASS.

- [ ] **Step 5: Commit**

```bash
git add app/chat.py tests/test_chat.py
git commit -m "feat: chat state machine (6 questions)"
```

---

### Task 6: Endpoints de job no main.py

**Files:**
- Modify: `app/main.py` — adicionar endpoints `/chat/*` e `/job/*`

- [ ] **Step 1: Adicionar imports e endpoints ao main.py**

Adicionar após os endpoints de auth existentes:

```python
# ── adicionar imports no topo ─────────────────────────────────────
import asyncio, json, zipfile, shutil
from pathlib import Path
from fastapi import UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
from app.chat import PERGUNTAS, proxima_pergunta, resumo_job
from app.carousel import gerar_carrossel

UPLOAD_DIR = Path("uploads")
CARROSSEIS_DIR = Path("carrosseis")
UPLOAD_DIR.mkdir(exist_ok=True)
CARROSSEIS_DIR.mkdir(exist_ok=True)

# ── Chat endpoints ────────────────────────────────────────────────
@app.post("/chat/iniciar")
def chat_iniciar(user_id: int = Depends(usuario_atual)):
    db = get_db()
    # verifica créditos
    from app.database import creditos_disponiveis
    if creditos_disponiveis(user_id, db) <= 0:
        db.close()
        raise HTTPException(status_code=402, detail="Sem créditos")
    # verifica jobs simultâneos
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

    # Salva no job
    colunas_validas = {"nicho", "tema", "logo_path", "cores_marca", "username_slide", "restricoes"}
    if campo in colunas_validas:
        db.execute(f"UPDATE carrosseis SET {campo}=? WHERE id=?", (valor, job_id))
        db.commit()

    # Monta estado atual — inclui apenas campos já respondidos (NULL = não respondido ainda)
    # Não pré-injeta opcionais: o usuário deve ver a pergunta e escolher pular explicitamente.
    # Quando o usuário submete vazio para um opcional, salva "" no DB e proxima_pergunta avança.
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
    # Verifica posse do job
    job = db.execute("SELECT * FROM carrosseis WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    if not job:
        db.close()
        raise HTTPException(status_code=404)

    # Debita crédito atomicamente com BEGIN IMMEDIATE (previne race condition em WAL mode)
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
    path = Path(job["pasta_path"]) / filename
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
```

- [ ] **Step 2: Testar endpoints com curl / TestClient**

```bash
pytest tests/test_auth.py tests/test_chat.py tests/test_carousel.py tests/test_database.py -v
```

Esperado: todos PASS.

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: chat and job endpoints (/chat/*, /job/*)"
```

---

## Chunk 4: Frontend

### Task 7: CSS compartilhado e página de login

**Files:**
- Create: `app/static/style.css`
- Create: `app/static/index.html`

- [ ] **Step 1: Criar style.css**

```css
/* app/static/style.css */
:root {
  --bg: #0a0a0a;
  --surface: #141414;
  --border: #2a2a2a;
  --accent: #FF4D00;
  --accent2: #FF8C42;
  --text: #ffffff;
  --muted: #888;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: var(--bg); color: var(--text); font-family: 'DM Sans', sans-serif; min-height: 100vh; }
a { color: var(--accent); text-decoration: none; }
.container { max-width: 480px; margin: 0 auto; padding: 40px 20px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 40px; }
h1 { font-size: 28px; font-weight: 700; margin-bottom: 8px; }
.subtitle { color: var(--muted); margin-bottom: 32px; font-size: 14px; }
.field { margin-bottom: 20px; }
label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 8px; letter-spacing: 1px; text-transform: uppercase; }
input[type=text], input[type=email], input[type=password] {
  width: 100%; padding: 14px 16px; background: #1e1e1e; border: 1px solid var(--border);
  border-radius: 10px; color: var(--text); font-size: 15px; outline: none;
  transition: border-color 0.2s;
}
input:focus { border-color: var(--accent); }
.btn { width: 100%; padding: 16px; background: linear-gradient(135deg, var(--accent), var(--accent2));
  color: #fff; border: none; border-radius: 10px; font-size: 16px; font-weight: 600;
  cursor: pointer; transition: opacity 0.2s; }
.btn:hover { opacity: 0.9; }
.btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--muted); }
.error { color: #ff4444; font-size: 13px; margin-top: 12px; display: none; }
.tabs { display: flex; gap: 4px; margin-bottom: 32px; background: #1e1e1e; border-radius: 10px; padding: 4px; }
.tab { flex: 1; padding: 10px; text-align: center; border-radius: 8px; cursor: pointer; font-size: 14px; color: var(--muted); border: none; background: none; }
.tab.active { background: var(--surface); color: var(--text); font-weight: 600; }
```

- [ ] **Step 2: Criar index.html**

```html
<!-- app/static/index.html -->
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agência IA — Login</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <div class="container" style="padding-top:80px">
    <div style="text-align:center;margin-bottom:40px">
      <div style="font-size:40px">🤖</div>
      <h1 style="font-size:32px;margin-top:12px">Agência IA</h1>
      <p class="subtitle">Carrosséis profissionais em minutos</p>
    </div>
    <div class="card">
      <div class="tabs">
        <button class="tab active" onclick="showTab('login')">Entrar</button>
        <button class="tab" onclick="showTab('cadastro')">Cadastrar</button>
      </div>

      <!-- Login -->
      <div id="form-login">
        <div class="field"><label>Email</label><input type="email" id="login-email" placeholder="seu@email.com"></div>
        <div class="field"><label>Senha</label><input type="password" id="login-senha" placeholder="••••••••"></div>
        <button class="btn" onclick="login()">Entrar</button>
        <p class="error" id="login-erro"></p>
      </div>

      <!-- Cadastro -->
      <div id="form-cadastro" style="display:none">
        <div class="field"><label>Nome</label><input type="text" id="cad-nome" placeholder="Seu nome"></div>
        <div class="field"><label>Email</label><input type="email" id="cad-email" placeholder="seu@email.com"></div>
        <div class="field"><label>Senha</label><input type="password" id="cad-senha" placeholder="mínimo 6 caracteres"></div>
        <div class="field"><label>@ Instagram/LinkedIn (opcional)</label><input type="text" id="cad-username" placeholder="@seuhandle"></div>
        <button class="btn" onclick="cadastrar()">Criar conta grátis</button>
        <p class="error" id="cad-erro"></p>
      </div>
    </div>
  </div>
<script>
function showTab(t){
  document.getElementById('form-login').style.display = t==='login'?'block':'none';
  document.getElementById('form-cadastro').style.display = t==='cadastro'?'block':'none';
  document.querySelectorAll('.tab').forEach((el,i)=>el.classList.toggle('active',(t==='login'&&i===0)||(t==='cadastro'&&i===1)));
}
async function login(){
  const email=document.getElementById('login-email').value;
  const senha=document.getElementById('login-senha').value;
  const r=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,senha})});
  const d=await r.json();
  if(!r.ok){document.getElementById('login-erro').style.display='block';document.getElementById('login-erro').textContent=d.detail;return;}
  localStorage.setItem('token',d.token);localStorage.setItem('nome',d.nome);
  window.location='/static/chat.html';
}
async function cadastrar(){
  const nome=document.getElementById('cad-nome').value;
  const email=document.getElementById('cad-email').value;
  const senha=document.getElementById('cad-senha').value;
  const username=document.getElementById('cad-username').value;
  const r=await fetch('/auth/cadastro',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nome,email,senha,username})});
  const d=await r.json();
  if(!r.ok){document.getElementById('cad-erro').style.display='block';document.getElementById('cad-erro').textContent=d.detail;return;}
  localStorage.setItem('token',d.token);localStorage.setItem('nome',d.nome);
  window.location='/static/chat.html';
}
// Já logado? vai direto pro chat
if(localStorage.getItem('token')) window.location='/static/chat.html';
</script>
</body>
</html>
```

- [ ] **Step 3: Iniciar servidor e testar login no browser**

```bash
cd ~/agencia-ia
python -m dotenv -f .env run -- uvicorn app.main:app --reload --port 8000
```

Abrir: `http://localhost:8000` — deve mostrar tela de login/cadastro.

- [ ] **Step 4: Commit**

```bash
git add app/static/style.css app/static/index.html
git commit -m "feat: login/signup page"
```

---

### Task 8: Chat, Loading e Preview

**Files:**
- Create: `app/static/chat.html`
- Create: `app/static/loading.html`
- Create: `app/static/preview.html`

- [ ] **Step 1: Criar chat.html**

```html
<!-- app/static/chat.html -->
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Agência IA — Chat</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css">
  <style>
    .chat-wrap{max-width:640px;margin:0 auto;padding:20px;height:100vh;display:flex;flex-direction:column}
    .chat-header{display:flex;justify-content:space-between;align-items:center;padding:16px 0;border-bottom:1px solid var(--border);margin-bottom:20px}
    .messages{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:16px;padding-bottom:20px}
    .msg{max-width:80%;padding:14px 18px;border-radius:16px;font-size:15px;line-height:1.6}
    .msg-bot{background:var(--surface);border:1px solid var(--border);align-self:flex-start;border-bottom-left-radius:4px}
    .msg-user{background:linear-gradient(135deg,var(--accent),var(--accent2));align-self:flex-end;border-bottom-right-radius:4px}
    .input-area{display:flex;gap:12px;padding:16px 0;border-top:1px solid var(--border)}
    .input-area input{flex:1;padding:14px 16px;background:#1e1e1e;border:1px solid var(--border);border-radius:10px;color:var(--text);font-size:15px;outline:none}
    .input-area input:focus{border-color:var(--accent)}
    .send-btn{padding:14px 24px;background:linear-gradient(135deg,var(--accent),var(--accent2));border:none;border-radius:10px;color:#fff;font-weight:600;cursor:pointer}
    .upload-hint{font-size:12px;color:var(--muted);margin-top:6px}
    .credits{font-size:13px;color:var(--muted)}
    .skip-btn{background:none;border:1px solid var(--border);color:var(--muted);padding:8px 16px;border-radius:8px;cursor:pointer;font-size:13px;margin-left:8px}
  </style>
</head>
<body>
<div class="chat-wrap">
  <div class="chat-header">
    <span style="font-weight:700;font-size:18px">🤖 Agência IA</span>
    <span class="credits" id="creditos-badge">— créditos</span>
  </div>
  <div class="messages" id="messages"></div>
  <div class="input-area">
    <input type="text" id="msg-input" placeholder="Digite sua resposta..." onkeydown="if(event.key==='Enter')enviar()">
    <input type="file" id="file-input" style="display:none" accept=".png,.jpg,.jpeg,.svg" onchange="enviarArquivo()">
    <button class="send-btn" onclick="enviar()">Enviar</button>
    <button class="skip-btn" id="skip-btn" style="display:none" onclick="pular()">Pular</button>
  </div>
</div>
<script>
const token = localStorage.getItem('token');
if(!token) window.location='/';
let jobId=null, campoAtual=null, isUpload=false;

function auth(){return{'Authorization':'Bearer '+token};}

function addMsg(texto,tipo){
  const d=document.createElement('div');
  d.className='msg msg-'+tipo;
  d.innerHTML=texto.replace(/\*([^*]+)\*/g,'<strong>$1</strong>').replace(/\n/g,'<br>');
  document.getElementById('messages').appendChild(d);
  d.scrollIntoView({behavior:'smooth'});
}

async function init(){
  const me=await fetch('/me',{headers:auth()});
  const d=await me.json();
  document.getElementById('creditos-badge').textContent=d.creditos+' crédito'+(d.creditos!==1?'s':'');
  if(d.creditos<=0){
    addMsg('Você não tem créditos. <a href="/static/planos.html">Ver planos →</a>','bot');
    return;
  }
  const r=await fetch('/chat/iniciar',{method:'POST',headers:auth()});
  if(!r.ok){addMsg('Erro ao iniciar. Tente novamente.','bot');return;}
  const d2=await r.json();
  jobId=d2.job_id;
  campoAtual=d2.campo;
  isUpload=d2.upload||false;
  addMsg(d2.pergunta,'bot');
  if(isUpload) document.getElementById('skip-btn').style.display='inline-block';
}

async function enviar(){
  const input=document.getElementById('msg-input');
  const texto=input.value.trim();
  if(!texto && !isUpload) return;
  if(isUpload && texto){
    document.getElementById('file-input').click();
    return;
  }
  input.value='';
  addMsg(texto||'(pulado)','user');
  await _enviarResposta(texto, null);
}

async function pular(){
  addMsg('(pulado)','user');
  await _enviarResposta('', null);
}

async function enviarArquivo(){
  const file=document.getElementById('file-input').files[0];
  if(!file) return;
  addMsg('📎 '+file.name,'user');
  await _enviarResposta('', file);
}

async function _enviarResposta(texto, arquivo){
  const fd=new FormData();
  fd.append('job_id',jobId);
  fd.append('campo',campoAtual);
  fd.append('resposta',texto);
  if(arquivo) fd.append('arquivo',arquivo);
  const r=await fetch('/chat/responder',{method:'POST',headers:auth(),body:fd});
  const d=await r.json();
  if(d.done){
    addMsg(d.resumo,'bot');
    campoAtual='confirmar';
    document.getElementById('skip-btn').style.display='none';
    document.getElementById('msg-input').placeholder='Digite "confirmar" para gerar';
  } else {
    campoAtual=d.campo;
    isUpload=d.upload||false;
    document.getElementById('skip-btn').style.display=isUpload?'inline-block':'none';
    addMsg(d.pergunta,'bot');
  }
}

document.getElementById('msg-input').addEventListener('keydown',async e=>{
  if(e.key==='Enter' && campoAtual==='confirmar'){
    if(document.getElementById('msg-input').value.trim().toLowerCase()==='confirmar'){
      addMsg('Gerando seu carrossel...🚀','user');
      const r=await fetch('/chat/confirmar?job_id='+jobId,{method:'POST',headers:auth()});
      if(r.ok){
        localStorage.setItem('job_id',jobId);
        window.location='/static/loading.html';
      }
    }
  }
});

init();
</script>
</body>
</html>
```

- [ ] **Step 2: Criar loading.html**

```html
<!-- app/static/loading.html -->
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Agência IA — Gerando</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css">
  <style>
    .center{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;text-align:center;gap:24px}
    .spinner{width:64px;height:64px;border:4px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin 1s linear infinite}
    @keyframes spin{to{transform:rotate(360deg)}}
    .progress-bar{width:320px;height:6px;background:var(--border);border-radius:3px;overflow:hidden}
    .progress-fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:3px;transition:width 1s ease;width:5%}
    .status-text{color:var(--muted);font-size:14px}
  </style>
</head>
<body>
<div class="center">
  <div style="font-size:48px">🤖</div>
  <h1>Criando seu carrossel</h1>
  <p class="status-text" id="status-text">Claude está escrevendo o conteúdo...</p>
  <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
  <div class="spinner"></div>
  <p style="color:var(--muted);font-size:13px">Isso leva cerca de 30-60 segundos</p>
</div>
<script>
const token=localStorage.getItem('token');
const jobId=localStorage.getItem('job_id');
if(!token||!jobId) window.location='/';

const mensagens=['Claude está escrevendo o conteúdo...','Buscando imagens na Pexels...','Renderizando slides com Playwright...','Finalizando os 7 slides...'];
let tick=0, tentativas=0;
const MAX=120; // 120 * 3s = 6 min timeout

const interval=setInterval(async()=>{
  tentativas++;
  tick=Math.min(tick+1,mensagens.length-1);
  document.getElementById('status-text').textContent=mensagens[tick];
  document.getElementById('progress-fill').style.width=Math.min(10+tentativas/MAX*85,95)+'%';

  if(tentativas>=MAX){
    clearInterval(interval);
    document.querySelector('h1').textContent='Tempo esgotado';
    document.getElementById('status-text').textContent='O job demorou demais. Tente novamente.';
    return;
  }
  let r, d;
  try {
    r=await fetch('/job/'+jobId+'/status',{headers:{'Authorization':'Bearer '+token}});
    if(!r.ok) return;
    d=await r.json();
  } catch(e) { return; }
  if(d.status==='pronto'){
    clearInterval(interval);
    document.getElementById('progress-fill').style.width='100%';
    setTimeout(()=>window.location='/static/preview.html',500);
  } else if(d.status==='erro'){
    clearInterval(interval);
    document.querySelector('h1').textContent='Erro na geração';
    document.getElementById('status-text').textContent='Ocorreu um erro. Seu crédito foi estornado.';
  }
},3000);
</script>
</body>
</html>
```

- [ ] **Step 3: Criar preview.html**

```html
<!-- app/static/preview.html -->
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Agência IA — Prévia</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css">
  <style>
    .header{display:flex;justify-content:space-between;align-items:center;padding:20px;border-bottom:1px solid var(--border)}
    .slides-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;padding:24px}
    .slide-card{border:1px solid var(--border);border-radius:12px;overflow:hidden;aspect-ratio:1}
    .slide-card img{width:100%;height:100%;object-fit:cover}
    .actions{padding:24px;display:flex;flex-direction:column;gap:12px;max-width:480px;margin:0 auto}
    .email-row{display:flex;gap:8px}
    .email-row input{flex:1;padding:14px;background:#1e1e1e;border:1px solid var(--border);border-radius:10px;color:var(--text)}
    .novo-btn{background:none;border:1px solid var(--border);color:var(--muted);padding:16px;border-radius:10px;cursor:pointer;font-size:15px;width:100%}
  </style>
</head>
<body>
<div class="header">
  <span style="font-weight:700;font-size:20px">🤖 Carrossel Pronto!</span>
  <a href="/static/chat.html" style="color:var(--muted);font-size:14px">+ Novo carrossel</a>
</div>
<div class="slides-grid" id="slides-grid">
  <p style="color:var(--muted);padding:24px">Carregando slides...</p>
</div>
<div class="actions">
  <a id="download-btn" class="btn" style="text-align:center;display:block">⬇ Baixar ZIP (7 slides)</a>
  <div class="email-row">
    <input type="email" id="email-field" placeholder="seu@email.com">
    <button class="btn" style="width:auto;padding:14px 20px" onclick="enviarEmail()">📧 Enviar</button>
  </div>
  <p id="email-status" style="color:var(--muted);font-size:13px;display:none"></p>
  <button class="novo-btn" onclick="window.location='/static/chat.html'">Gerar novo carrossel</button>
</div>
<script>
const token=localStorage.getItem('token');
const jobId=localStorage.getItem('job_id');
if(!token||!jobId) window.location='/';
const H={'Authorization':'Bearer '+token};

async function init(){
  const r=await fetch('/job/'+jobId+'/slides',{headers:H});
  if(!r.ok){document.getElementById('slides-grid').innerHTML='<p style="color:red;padding:24px">Erro ao carregar slides.</p>';return;}
  const d=await r.json();
  const grid=document.getElementById('slides-grid');
  grid.innerHTML='';
  d.slides.forEach(url=>{
    const card=document.createElement('div');
    card.className='slide-card';
    card.innerHTML=`<img src="${url}" loading="lazy">`;
    grid.appendChild(card);
  });
  document.getElementById('download-btn').href='/job/'+jobId+'/download';
  // preenche email do usuário
  const me=await fetch('/me',{headers:H});
  const md=await me.json();
  document.getElementById('email-field').value=md.email||'';
}

async function enviarEmail(){
  const email=document.getElementById('email-field').value.trim();
  if(!email) return;
  const r=await fetch('/job/'+jobId+'/email',{method:'POST',headers:{...H,'Content-Type':'application/json'},body:JSON.stringify({email})});
  const el=document.getElementById('email-status');
  el.style.display='block';
  el.textContent=r.ok?'✅ Email enviado com sucesso!':'❌ Falha ao enviar. Tente novamente.';
}

init();
</script>
</body>
</html>
```

- [ ] **Step 4: Testar fluxo completo no browser**

```bash
python -m uvicorn app.main:app --reload --port 8000
```

1. Abrir `http://localhost:8000` → cadastrar
2. Passar pelo chat de 6 perguntas
3. Confirmar → ver loading
4. Ver preview com os slides

- [ ] **Step 5: Commit**

```bash
git add app/static/
git commit -m "feat: chat, loading and preview pages"
```

---

## Chunk 5: Email, Planos e Pagamentos

### Task 9: Email sender e endpoint

**Files:**
- Create: `app/email_sender.py`
- Modify: `app/main.py` — adicionar endpoint `/job/{id}/email`

- [ ] **Step 1: Implementar app/email_sender.py**

```python
# app/email_sender.py
import os, smtplib, zipfile
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path

def criar_zip(pasta: Path) -> Path:
    zip_path = pasta / "carrossel.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for png in sorted(pasta.glob("slide_*.png")):
            zf.write(png, png.name)
    return zip_path

def enviar_email_zip(destinatario: str, zip_path: Path, job_id: int):
    host = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    port = int(os.getenv("EMAIL_PORT", "587"))
    user = os.getenv("EMAIL_USER", "")
    password = os.getenv("EMAIL_PASSWORD", "")

    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = destinatario
    msg["Subject"] = f"🤖 Seu carrossel #{job_id} está pronto!"

    msg.attach(MIMEText(
        "Olá!\n\nSeu carrossel foi gerado com sucesso. Os 7 slides estão em anexo.\n\nBom proveito! 🚀\n\nAgência IA",
        "plain", "utf-8"
    ))

    with open(zip_path, "rb") as f:
        part = MIMEBase("application", "zip")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="carrossel_{job_id}.zip"')
        msg.attach(part)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, destinatario, msg.as_string())
```

- [ ] **Step 2: Adicionar endpoint de email no main.py**

```python
# Adicionar ao main.py
from app.email_sender import criar_zip, enviar_email_zip

class EmailIn(BaseModel):
    email: str

@app.post("/job/{job_id}/email")
def job_email(job_id: int, data: EmailIn, user_id: int = Depends(usuario_atual)):
    db = get_db()
    job = db.execute("SELECT status, pasta_path FROM carrosseis WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
    db.close()
    if not job or job["status"] != "pronto":
        raise HTTPException(status_code=404)
    pasta = Path(job["pasta_path"])
    zip_path = criar_zip(pasta)
    try:
        enviar_email_zip(data.email, zip_path, job_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao enviar email: {str(e)}")
    return {"ok": True}
```

- [ ] **Step 3: Commit**

```bash
git add app/email_sender.py app/main.py
git commit -m "feat: email sender and /job/{id}/email endpoint"
```

---

### Task 10: Planos e pagamentos Mercado Pago

**Files:**
- Create: `app/pagamentos.py`
- Create: `app/static/planos.html`
- Create: `tests/test_pagamentos.py`
- Modify: `app/main.py` — adicionar endpoints de pagamento

- [ ] **Step 1: Escrever testes do webhook**

```python
# tests/test_pagamentos.py
import hmac, hashlib
from app.pagamentos import validar_assinatura_webhook

def test_assinatura_valida():
    secret = "meu-segredo"
    corpo = b'{"id":123}'
    sig = hmac.new(secret.encode(), corpo, hashlib.sha256).hexdigest()
    assert validar_assinatura_webhook(sig, corpo, secret)

def test_assinatura_invalida():
    assert not validar_assinatura_webhook("errada", b'{"id":1}', "segredo")
```

- [ ] **Step 2: Implementar app/pagamentos.py**

```python
# app/pagamentos.py
import os, hmac, hashlib
import mercadopago

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET", "")
APP_URL = os.getenv("APP_URL", "http://localhost:8000")

PLANOS = {
    "avulso": {"nome": "1 Carrossel", "valor": 19.90, "creditos": 1},
    "pack5":  {"nome": "Pack 5 Carrosséis", "valor": 79.90, "creditos": 5},
    "pack15": {"nome": "Pack 15 Carrosséis", "valor": 197.00, "creditos": 15},
}

def criar_preferencia_mp(pagamento_id: int, plano_key: str) -> str:
    plano = PLANOS[plano_key]
    sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
    pref = {
        "items": [{"title": plano["nome"], "quantity": 1, "unit_price": float(plano["valor"])}],
        "external_reference": str(pagamento_id),
        "back_urls": {
            "success": f"{APP_URL}/static/chat.html",
            "failure": f"{APP_URL}/static/planos.html",
        },
        "auto_return": "approved",
        "notification_url": f"{APP_URL}/webhook/mercadopago",
    }
    result = sdk.preference().create(pref)
    return result["response"]["init_point"]

def validar_assinatura_webhook(x_signature: str, corpo: bytes, secret: str) -> bool:
    esperado = hmac.new(secret.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, x_signature)
```

- [ ] **Step 3: Rodar testes**

```bash
pytest tests/test_pagamentos.py -v
```

Esperado: 2 PASS.

- [ ] **Step 4: Adicionar endpoints de pagamento no main.py**

```python
# Adicionar ao main.py
from app.pagamentos import PLANOS, criar_preferencia_mp, validar_assinatura_webhook, MP_WEBHOOK_SECRET
from fastapi import Request

class PagamentoIn(BaseModel):
    plano: str

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
    sig = request.headers.get("x-signature", "")
    if MP_WEBHOOK_SECRET and not validar_assinatura_webhook(sig, corpo, MP_WEBHOOK_SECRET):
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
```

- [ ] **Step 5: Criar planos.html**

```html
<!-- app/static/planos.html -->
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Agência IA — Planos</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/style.css">
  <style>
    .plans-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;padding:24px;max-width:900px;margin:0 auto}
    .plan-card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:32px;text-align:center}
    .plan-card.featured{border-color:var(--accent)}
    .plan-price{font-size:36px;font-weight:700;margin:16px 0 4px}
    .plan-sub{color:var(--muted);font-size:13px;margin-bottom:24px}
    .plan-credits{font-size:14px;margin-bottom:24px;color:var(--accent)}
  </style>
</head>
<body>
<div style="text-align:center;padding:48px 20px 24px">
  <h1>Escolha seu plano</h1>
  <p style="color:var(--muted);margin-top:8px">Pagamento via PIX ou cartão de crédito</p>
</div>
<div class="plans-grid" id="plans-grid">
  <p style="color:var(--muted)">Carregando...</p>
</div>
<script>
const token=localStorage.getItem('token');
if(!token) window.location='/';

async function init(){
  const r=await fetch('/planos');
  const planos=await r.json();
  const grid=document.getElementById('plans-grid');
  grid.innerHTML='';
  Object.entries(planos).forEach(([key,p],i)=>{
    const card=document.createElement('div');
    card.className='plan-card'+(i===1?' featured':'');
    card.innerHTML=`
      <h3>${p.nome}</h3>
      <div class="plan-price">R$ ${p.valor.toFixed(2).replace('.',',')}</div>
      <div class="plan-credits">🎯 ${p.creditos} carrossel${p.creditos>1?'s':''}</div>
      <div class="plan-sub">R$ ${(p.valor/p.creditos).toFixed(2).replace('.',',')} por carrossel</div>
      <button class="btn" onclick="comprar('${key}')">Comprar agora</button>
    `;
    grid.appendChild(card);
  });
}

async function comprar(plano){
  const r=await fetch('/pagamento/criar',{method:'POST',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({plano})});
  if(!r.ok){alert('Erro ao criar pagamento');return;}
  const d=await r.json();
  window.location=d.init_point;
}

init();
</script>
</body>
</html>
```

- [ ] **Step 6: Rodar todos os testes**

```bash
pytest tests/ -v
```

Esperado: todos PASS.

- [ ] **Step 7: Commit final**

```bash
git add app/pagamentos.py app/static/planos.html app/main.py tests/test_pagamentos.py
git commit -m "feat: Mercado Pago integration (planos, pagamento, webhook)"
```

---

## Fluxo de Teste Local Completo

```bash
# 1. Copiar e preencher .env
cp .env.example .env
# editar .env com suas chaves

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Rodar testes
pytest tests/ -v

# 4. Subir servidor
python -m uvicorn app.main:app --reload --port 8000

# 5. Para testar webhook do Mercado Pago localmente:
# Instalar ngrok: https://ngrok.com/download
ngrok http 8000
# Copiar URL do ngrok para APP_URL no .env e reconfigura preferência no MP dashboard
```

**Fluxo esperado:**
1. `http://localhost:8000` → login/cadastro (1 crédito trial)
2. Chat → 6 perguntas → confirmar
3. Loading → prévia dos 7 slides
4. Download ZIP ou receber por email
5. Sem créditos → `/static/planos.html` → pagar → créditos adicionados

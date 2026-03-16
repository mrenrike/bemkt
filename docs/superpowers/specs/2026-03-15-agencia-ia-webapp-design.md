# Agência IA — Web App Design Spec
**Data:** 2026-03-15
**Status:** v2 — revisado

---

## Visão Geral

Web app self-service onde o cliente final se cadastra, passa por um chat guiado de 5 perguntas, e recebe um carrossel de 7 slides 1080×1080px prontos para postar no Instagram ou LinkedIn. O motor de geração é extraído do `agencia_v2.py` em funções importáveis.

---

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Backend | FastAPI (Python) |
| Frontend | HTML + CSS + JS vanilla |
| Banco de dados | SQLite |
| Auth | JWT (python-jose + passlib[bcrypt]) |
| Render | Playwright (já instalado) |
| Imagens | Pexels API + Picsum fallback |
| Email | smtplib (nativo Python) |
| Pagamentos | Mercado Pago (PIX + cartão de crédito) |

---

## Refatoração do agencia_v2.py

O `agencia_v2.py` atual usa `input()`, `sys.stdout.write` e `sync_playwright` de forma bloqueante. Para uso no web app, as funções de geração serão extraídas para um módulo importável **sem alterar o CLI existente**:

**`app/carousel.py`** expõe:
```python
async def gerar_carrossel(
    tema: str,
    plataforma: str,
    nicho: str,
    restricoes: str,
    cores_marca: str,          # hex ou descrição
    logo_path: str | None,     # caminho local do logo enviado
    username: str,             # marca d'água (@handle do cliente)
    api_key: str,
    pexels_key: str,
    pasta_destino: Path,
) -> list[Path]:               # retorna lista de PNGs gerados
```

Internamente chama `gerar_conteudo_claude()` e o loop de render, rodando `sync_playwright` dentro de `asyncio.to_thread()` para não bloquear o event loop do FastAPI.

O `nicho` e `restricoes` são injetados no prompt do Claude junto com o `tema`.

**Logo nos slides:** a função `gerar_html_slide()` receberá dois novos parâmetros:

```python
def gerar_html_slide(
    slide: dict,
    total: int,
    tema: str,
    paleta: dict,
    img_local: str = "",
    logo_url: str | None = None,   # file:///caminho/logo.png para Playwright
    username: str = "",            # substitui @baladaroyalle
) -> str:
```

- `logo_url` é construído a partir de `logo_path` em disco: `f"file:///{logo_path.replace(chr(92), '/')}"` — mesmo padrão já usado para `img_local`.
- Quando presente, um `<img src="{logo_url}">` é renderizado no canto superior esquerdo com `max-width:160px; max-height:80px; object-fit:contain`.
- Arquivos SVG são suportados pelo Chromium do Playwright sem tratamento especial.
- A linha `<div class="marca">@baladaroyalle</div>` usa `{username}` no lugar do handle fixo.

**Remoção do I/O de streaming em `gerar_conteudo_claude()`:** ao extrair para `carousel.py`, o bloco `sys.stdout.write(text)` dentro do loop de streaming **deve ser removido**. O texto acumulado em `resposta` já é suficiente para o parse do JSON. Manter o `sys.stdout.write` em contexto web polui o stdout do servidor e pode interferir com loggers do uvicorn.

---

## Estrutura de Arquivos

```
agencia-ia/
├── agencia_v2.py              ← CLI existente, não muda
├── app/
│   ├── main.py                ← FastAPI, monta rotas, serve static
│   ├── auth.py                ← cadastro, login, JWT
│   ├── chat.py                ← lógica do chat guiado
│   ├── carousel.py            ← funções extraídas + wrapper async
│   ├── email_sender.py        ← envia ZIP por email
│   ├── database.py            ← SQLite, criação de tabelas
│   ├── pagamentos.py          ← integração Mercado Pago
│   └── static/
│       ├── index.html         ← login + cadastro
│       ├── chat.html          ← interface do chat guiado
│       ├── loading.html       ← tela de geração (~30s)
│       ├── preview.html       ← grid de slides + download + email
│       ├── planos.html        ← seleção de plano + pagamento
│       ├── conta.html         ← histórico de carrosséis e pagamentos
│       └── style.css
├── uploads/                   ← logos enviados (PNG/JPG/SVG, máx 5MB)
├── carrosseis/                ← PNGs gerados (por user_id/job_id)
├── .env
├── requirements.txt
└── users.db
```

---

## Banco de Dados (SQLite)

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    senha_hash TEXT NOT NULL,
    username TEXT,              -- handle para marca d'água (ex: @seuhandle)
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Ledger de créditos (append-only, mais confiável que contador)
CREATE TABLE credit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    delta INTEGER NOT NULL,    -- +1, +5, +15, -1
    motivo TEXT,               -- 'trial' | 'compra' | 'uso' | 'reembolso'
    ref_id TEXT,               -- job_id ou pagamento_id relacionado
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Carrosséis gerados
CREATE TABLE carrosseis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    nicho TEXT,
    tema TEXT,
    restricoes TEXT,
    cores_marca TEXT,
    logo_path TEXT,
    paleta_nome TEXT,          -- preenchido após geração
    pasta_path TEXT,           -- preenchido após geração
    status TEXT DEFAULT 'pendente',  -- pendente | gerando | pronto | erro
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pagamentos
CREATE TABLE pagamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    plano TEXT,                -- avulso | pack5 | pack15
    valor REAL,
    creditos_comprados INTEGER,
    status TEXT DEFAULT 'pendente',  -- pendente | aprovado | cancelado
    mp_payment_id TEXT UNIQUE, -- UNIQUE garante idempotência no webhook
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Crédito disponível** é calculado como `SUM(delta) FROM credit_events WHERE user_id = ?`. Reembolso em caso de erro = INSERT com `delta = +1, motivo = 'reembolso'`.

---

## Planos e Preços

| Plano | Créditos | Preço |
|-------|---------|-------|
| Trial | 1 (grátis ao cadastrar) | R$ 0 |
| Avulso | 1 | R$ 19,90 |
| Pack 5 | 5 | R$ 79,90 |
| Pack 15 | 15 | R$ 197,00 |

---

## Chat Guiado — 6 Perguntas

1. **Nicho:** "Qual o nicho ou segmento da sua marca?"
2. **Tema:** "Qual o tema do carrossel? Pode colar um texto que já tem ou descrever o assunto."
3. **Logo:** "Tem logo para incluir nos slides? (upload PNG/JPG/SVG até 5MB — pode pular com Enter)"
4. **Identidade visual:** "Quais são as cores da marca? (hex, descrição ou envie uma imagem de referência)"
5. **Username:** "Qual o seu @ para aparecer nos slides? (ex: @baladaroyalle — pode pular)"
6. **Restrições:** "Tem alguma palavra, concorrente ou assunto que **não** pode aparecer? (pode pular)"

Após a 6ª resposta: exibe resumo e pede confirmação antes de debitar crédito e gerar.

**Regras de skip:** perguntas 3, 5 e 6 são opcionais — resposta vazia avança sem salvar o campo. Se o usuário já tem `username` salvo no perfil, a pergunta 5 mostra o valor atual e oferece manter ou trocar.

---

## Endpoints da API

```
POST /auth/cadastro           ← { nome, email, senha, username? }
                                → cria usuário + INSERT credit_events (delta=+1, motivo='trial')
                                → retorna JWT

POST /auth/login              ← { email, senha } → JWT

GET  /me                      ← dados do usuário + créditos disponíveis (SUM credit_events)

POST /chat/iniciar            ← autenticado → cria carrossel com status='pendente'
                                → retorna { job_id, pergunta: "..." }

POST /chat/responder          ← { job_id, resposta } + arquivo opcional (multipart)
                                → salva resposta no job, retorna próxima pergunta ou resumo
                                → verifica job.user_id == current_user.id

POST /chat/confirmar          ← { job_id }
                                → BEGIN IMMEDIATE; verifica créditos > 0; debita;
                                  atualiza status='gerando'; COMMIT
                                → dispara gerar_carrossel() em background task
                                → verifica job.user_id == current_user.id

GET  /job/{job_id}/status     ← polling (intervalo 3s, timeout cliente 3min)
                                → { status, progresso? }
                                → verifica job.user_id == current_user.id

GET  /job/{job_id}/slides     ← lista URLs dos PNGs
                                → verifica job.user_id == current_user.id

GET  /job/{job_id}/download   ← serve ZIP
                                → verifica job.user_id == current_user.id

POST /job/{job_id}/email      ← { email } — deve ser o email do usuário autenticado
                                → envia ZIP por email
                                → verifica job.user_id == current_user.id

GET  /planos                  ← lista planos e preços (público)

POST /pagamento/criar         ← { plano } autenticado
                                → INSERT pagamentos (status='pendente')
                                → cria preferência no MP com external_reference = pagamento.id
                                → retorna { init_point: "https://mp.com/..." }

POST /webhook/mercadopago     ← notificação do MP
                                → valida assinatura HMAC-SHA256 (header x-signature)
                                  usando hmac.compare_digest
                                → busca pagamento por mp_payment_id (UNIQUE — idempotente)
                                → se já aprovado: retorna 200 sem ação
                                → se pendente: atualiza status='aprovado'
                                  + INSERT credit_events (delta=creditos_comprados, motivo='compra')
                                → external_reference mapeia para pagamento.id → user_id

GET  /minha-conta             ← histórico de carrosséis e pagamentos do usuário autenticado
```

---

## Tratamento de Erros

| Cenário | Ação |
|---------|------|
| Geração falha | status='erro' + INSERT credit_events (delta=+1, motivo='reembolso') |
| Pagamento não confirmado em 30min | status='cancelado', sem créditos |
| Upload inválido (tipo/tamanho) | rejeita antes de salvar; aceita PNG/JPG/SVG até 5MB via `UploadFile` do FastAPI com verificação de `content_type` e tamanho |
| Crédito insuficiente | 402 Payment Required + redirect para /planos |
| 3 jobs simultâneos por usuário | conta `carrosseis WHERE user_id=? AND status IN ('pendente','gerando')` antes de criar novo job; 429 se >= 3 |
| Webhook duplicado | `mp_payment_id UNIQUE` rejeita INSERT; retorna 200 |

---

## Integração Mercado Pago

```python
# pagamentos.py
import mercadopago
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

def criar_preferencia(pagamento_id: int, plano: dict) -> str:
    preference_data = {
        "items": [{"title": plano["nome"], "quantity": 1, "unit_price": plano["valor"]}],
        "external_reference": str(pagamento_id),  # mapeia webhook → user
        "back_urls": {"success": "/chat", "failure": "/planos"},
        "auto_return": "approved",
        "notification_url": "https://SEU_DOMINIO/webhook/mercadopago",
    }
    result = sdk.preference().create(preference_data)
    return result["response"]["init_point"]

def validar_webhook(x_signature: str, corpo: bytes, secret: str) -> bool:
    import hmac, hashlib
    esperado = hmac.new(secret.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, x_signature)
```

---

## Variáveis de Ambiente (.env)

```
ANTHROPIC_API_KEY=...
PEXELS_API_KEY=...
MP_ACCESS_TOKEN=...
MP_WEBHOOK_SECRET=...
JWT_SECRET=...
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=...
EMAIL_PASSWORD=...
```

---

## Para o Ambiente Local de Teste

```bash
pip install fastapi uvicorn python-jose passlib[bcrypt] mercadopago \
            python-multipart python-dotenv aiofiles
python -m uvicorn app.main:app --reload --port 8000
# Acessa: http://localhost:8000
# Webhook local: ngrok http 8000  →  usa a URL do ngrok em MP_WEBHOOK_SECRET
```

---

## Notas de Implementação

- **Google Fonts:** `gerar_html_slide()` precisa de acesso à internet durante o render no Playwright. Em produção, considerar embutir as fontes como base64 ou hospedar localmente.
- **Jobs travados:** se o servidor reiniciar com jobs em status `gerando`, um `@app.on_event("startup")` em `main.py` executa:
  ```python
  # 1. busca jobs presos
  presos = db.execute("SELECT id, user_id FROM carrosseis WHERE status = 'gerando'").fetchall()
  for job in presos:
      # 2. marca como erro
      db.execute("UPDATE carrosseis SET status='erro' WHERE id=?", (job["id"],))
      # 3. reembolsa crédito
      db.execute("INSERT INTO credit_events (user_id, delta, motivo, ref_id) VALUES (?,1,'reembolso',?)",
                 (job["user_id"], str(job["id"])))
  db.commit()
  ```
- **Concorrência Playwright:** múltiplos jobs simultâneos compartilham o mesmo processo; cada job abre e fecha o browser independentemente via `asyncio.to_thread()`.

# app/chat.py

PLATAFORMAS = {
    "1": "Instagram",
    "2": "LinkedIn",
    "3": "TikTok",
    "4": "X (Twitter)",
}

FINALIDADES = {
    "1": "educacional",
    "2": "vender",
    "3": "engajamento",
    "4": "awareness",
}

CTA_OBJETIVOS = {
    "1": "link_bio",
    "2": "seguir",
    "3": "compartilhar",
    "4": "comentar",
}

PERGUNTAS = [
    {
        "campo": "plataforma",
        "texto": (
            "Para qual rede social é o carrossel?\n\n"
            "1️⃣ *Instagram* — visual, emocional, salva e compartilha\n"
            "2️⃣ *LinkedIn* — profissional, dados, tom de negócios\n"
            "3️⃣ *TikTok* — jovem, direto, gancho explosivo\n"
            "4️⃣ *X (Twitter)* — conciso, provocativo, sem floreios\n\n"
            "Digite 1, 2, 3 ou 4."
        ),
        "opcional": False,
    },
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
        "campo": "finalidade",
        "texto": (
            "Qual a *finalidade* deste carrossel?\n\n"
            "1️⃣ *Educar* — ensinar algo valioso para a audiência\n"
            "2️⃣ *Vender* — apresentar produto ou serviço\n"
            "3️⃣ *Engajamento* — gerar comentários e compartilhamentos\n"
            "4️⃣ *Autoridade* — fortalecer posicionamento da marca\n\n"
            "Digite 1, 2, 3 ou 4."
        ),
        "opcional": False,
    },
    {
        "campo": "cta_objetivo",
        "texto": (
            "Qual ação você quer que as pessoas tomem no *slide final*?\n\n"
            "1️⃣ *Link na bio* — enviar para uma página, produto ou link\n"
            "2️⃣ *Seguir o perfil* — crescer sua audiência\n"
            "3️⃣ *Compartilhar/salvar* — aumentar o alcance do post\n"
            "4️⃣ *Comentar* — gerar debate e engajamento\n\n"
            "Digite 1, 2, 3 ou 4."
        ),
        "opcional": False,
    },
    {
        "campo": "modelo",
        "texto": (
            "Escolha o estilo visual:\n\n"
            "1️⃣ *Authority Dark* — fundo preto, Inter Black, acento neon. Premium e viral.\n"
            "2️⃣ *Clean Editorial* — fundo off-white, tipografia serif. Elegante e profissional.\n"
            "3️⃣ *Vibrant Gradient* — gradiente colorido, glassmorphism. Jovem e energético.\n"
            "4️⃣ *Foto Bold* — foto de fundo, overlay gradiente. Clássico e impactante.\n"
            "5️⃣ *Minimal Type* — só tipografia. Para frases, dados e perguntas de impacto.\n\n"
            "Digite 1, 2, 3, 4 ou 5."
        ),
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
        "texto": "Quais são as cores da marca? Informe o código hex (#8CFF2E), descreva (verde neon) ou Enter para usar a paleta padrão.",
        "opcional": True,
    },
    {
        "campo": "username_slide",
        "texto": "Qual o seu @ para aparecer nos slides? (ex: @bemkt — Enter para pular)",
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


MODELOS = {
    "1": "Authority Dark",
    "2": "Clean Editorial",
    "3": "Vibrant Gradient",
    "4": "Foto Bold",
    "5": "Minimal Type",
}

_FINALIDADE_LABEL = {
    "1": "Educar", "2": "Vender", "3": "Engajamento", "4": "Autoridade",
    "educacional": "Educar", "vender": "Vender",
    "engajamento": "Engajamento", "awareness": "Autoridade",
}

_CTA_LABEL = {
    "1": "Link na bio", "2": "Seguir o perfil",
    "3": "Compartilhar/salvar", "4": "Comentar",
    "link_bio": "Link na bio", "seguir": "Seguir o perfil",
    "compartilhar": "Compartilhar/salvar", "comentar": "Comentar",
}


def resumo_job(estado: dict) -> str:
    linhas = ["📋 *Resumo do seu carrossel:*\n"]
    modelo_val   = estado.get("modelo", "4")
    plat_val     = estado.get("plataforma", "1")
    final_val    = estado.get("finalidade", "")
    cta_val      = estado.get("cta_objetivo", "")
    labels = {
        "nicho":          "Nicho",
        "tema":           "Tema",
        "cores_marca":    "Cores",
        "username_slide": "Username",
        "restricoes":     "Restrições",
    }
    linhas.append(f"• *Rede social:* {PLATAFORMAS.get(plat_val, 'Instagram')}")
    linhas.append(f"• *Estilo:* {MODELOS.get(modelo_val, 'Foto Bold')}")
    if final_val:
        linhas.append(f"• *Finalidade:* {_FINALIDADE_LABEL.get(final_val, final_val)}")
    if cta_val:
        linhas.append(f"• *CTA:* {_CTA_LABEL.get(cta_val, cta_val)}")
    for campo, label in labels.items():
        val = estado.get(campo, "")
        if val:
            linhas.append(f"• *{label}:* {val}")
        elif campo in ["logo_path", "username_slide", "restricoes", "cores_marca"]:
            linhas.append(f"• *{label}:* (não informado)")
    linhas.append("\nTudo certo? Digite *confirmar* para gerar o carrossel.")
    return "\n".join(linhas)

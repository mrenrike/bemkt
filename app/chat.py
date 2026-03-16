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

"""
testar_templates.py — Gera 1 carrossel por template e envia por email.
Execute: python testar_templates.py
"""
import asyncio, os, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from app.carousel import gerar_carrossel
from app.email_sender import criar_zip, enviar_email_zip

EMAIL_DESTINO = "bruno@bemkt.com.br"
PASTA_TESTES  = Path("testes_templates")

TESTES = [
    {
        "template": "1",
        "nome":     "authority_dark",
        "tema":     "Os 5 erros que destroem sua autoridade no Instagram",
        "plataforma": "Instagram",
        "nicho":    "marketing digital",
        "cores_marca": "#8CFF2E",
        "username": "bemkt",
    },
    {
        "template": "2",
        "nome":     "clean_editorial",
        "tema":     "Como construir uma marca premium do zero",
        "plataforma": "LinkedIn",
        "nicho":    "branding e consultoria",
        "cores_marca": "#1a1a1a",
        "username": "bemkt",
    },
    {
        "template": "3",
        "nome":     "vibrant_gradient",
        "tema":     "3 hábitos que vão transformar seu treino em 30 dias",
        "plataforma": "Instagram",
        "nicho":    "fitness e saúde",
        "cores_marca": "#7c3aed #ec4899",
        "username": "bemkt",
    },
    {
        "template": "4",
        "nome":     "foto_bold",
        "tema":     "Por que 90% dos negócios falham nos primeiros 5 anos",
        "plataforma": "Instagram",
        "nicho":    "empreendedorismo",
        "cores_marca": "#FF4D00",
        "username": "bemkt",
    },
    {
        "template": "5",
        "nome":     "minimal_type",
        "tema":     "Produtividade falsa: o que parece trabalho mas não é",
        "plataforma": "LinkedIn",
        "nicho":    "gestão e produtividade",
        "cores_marca": "#8CFF2E",
        "username": "bemkt",
    },
]


async def gerar_e_enviar(teste: dict, idx: int):
    pasta = PASTA_TESTES / f"template_{teste['template']}_{teste['nome']}"
    print(f"\n[{idx+1}/5] Gerando Template {teste['template']} — {teste['nome'].upper()}")
    print(f"       Tema: {teste['tema']}")

    try:
        pngs = await gerar_carrossel(
            tema=teste["tema"],
            plataforma=teste["plataforma"],
            nicho=teste["nicho"],
            restricoes="",
            cores_marca=teste["cores_marca"],
            logo_path=None,
            username=teste["username"],
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            pexels_key=os.getenv("PEXELS_API_KEY", ""),
            pasta_destino=pasta,
            template=teste["template"],
        )
        print(f"       OK {len(pngs)} slides gerados")

        zip_path = criar_zip(pasta)
        enviar_email_zip(EMAIL_DESTINO, zip_path, int(f"{idx+1}0"))
        print(f"       OK Email enviado -> {EMAIL_DESTINO}")

    except Exception as e:
        print(f"       ERRO: {e}")
        import traceback
        traceback.print_exc()


async def main():
    PASTA_TESTES.mkdir(exist_ok=True)
    print(f"=== BEMKT — Teste dos 5 Templates ===")
    print(f"Destino: {EMAIL_DESTINO}\n")

    for i, teste in enumerate(TESTES):
        await gerar_e_enviar(teste, i)

    print(f"\n=== Concluído. Verifique {EMAIL_DESTINO} ===")


if __name__ == "__main__":
    asyncio.run(main())

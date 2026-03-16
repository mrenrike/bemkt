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
            resposta += text
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

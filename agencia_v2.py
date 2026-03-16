"""
🚀 AGÊNCIA DE CONTEÚDO — Powered by Claude AI
Gera carrosséis visuais prontos (PNG) para Instagram/LinkedIn.
Cada slide = imagem real do Unsplash + design moderno.
"""

import anthropic
import json
import time
import sys
import os
import re
import io
import urllib.request
import urllib.parse
import subprocess
from datetime import datetime
from pathlib import Path

# Força UTF-8 no terminal Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ── CORES ────────────────────────────────────────────────────────
RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
ORANGE = "\033[38;5;208m"; GREEN = "\033[38;5;82m"
CYAN = "\033[38;5;51m"; WHITE = "\033[97m"
GRAY = "\033[90m"; RED = "\033[38;5;196m"
PURPLE = "\033[38;5;135m"; YELLOW = "\033[38;5;226m"

def cls(): os.system('clear' if os.name != 'nt' else 'cls')

def slow_print(text, delay=0.022, end="\n"):
    for c in text:
        sys.stdout.write(c); sys.stdout.flush(); time.sleep(delay)
    sys.stdout.write(end); sys.stdout.flush()

def line(char="─", n=60, color=GRAY):
    print(f"{color}{char*n}{RESET}")

def spinner(label, duration=1.6):
    frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    end_t = time.time() + duration; i = 0
    while time.time() < end_t:
        sys.stdout.write(f"\r {CYAN}{frames[i%len(frames)]}{RESET} {WHITE}{label}{RESET} ")
        sys.stdout.flush(); time.sleep(0.08); i += 1
    sys.stdout.write(f"\r {GREEN}✓{RESET} {WHITE}{label}{RESET} \n")
    sys.stdout.flush()

def loading_bar(label, duration=2.0, color=CYAN):
    N = 32
    print(f" {color}{label}{RESET}")
    for i in range(N+1):
        filled = "█"*i; empty = "░"*(N-i); pct = int(i/N*100)
        sys.stdout.write(f"\r {GRAY}[{GREEN}{filled}{GRAY}{empty}] {WHITE}{pct}%{RESET} ")
        sys.stdout.flush(); time.sleep(duration/N)
    print()

# ── BAIXA IMAGEM DA PEXELS PARA DISCO ───────────────────────────
def baixar_imagem(query: str, destino: Path, pexels_key: str = "", width=1080, height=1080) -> str:
    headers_default = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }

    if pexels_key:
        try:
            q = urllib.parse.quote(query)
            api_url = f"https://api.pexels.com/v1/search?query={q}&per_page=5&orientation=square"
            req = urllib.request.Request(api_url, headers={
                **headers_default,
                "Authorization": pexels_key
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                fotos = data.get("photos", [])
                if fotos:
                    img_url = fotos[0]["src"]["large2x"]
                    req2 = urllib.request.Request(img_url, headers=headers_default)
                    with urllib.request.urlopen(req2, timeout=15) as resp2:
                        destino.write_bytes(resp2.read())
                    return str(destino.absolute())
        except Exception:
            pass

    seed = abs(hash(query)) % 1000
    img_url = f"https://picsum.photos/seed/{seed}/{width}/{height}"
    req = urllib.request.Request(img_url, headers=headers_default)
    with urllib.request.urlopen(req, timeout=15) as resp:
        destino.write_bytes(resp.read())
    return str(destino.absolute())

# ── GERA HTML DE UM SLIDE ────────────────────────────────────────
def gerar_html_slide(slide: dict, total: int, tema: str, paleta: dict, img_local: str = "") -> str:
    num = slide.get("numero", 1)
    titulo = slide.get("titulo", "")
    texto = slide.get("texto", "")
    emoji = slide.get("emoji", "✦")
    is_capa = (num == 1)
    is_cta = (num == total)

    img_url = f"file:///{img_local.replace(chr(92), '/')}" if img_local else ""

    bg_color = paleta["bg"]
    accent = paleta["accent"]
    accent2 = paleta["accent2"]
    text_color = paleta["text"]
    overlay_color = paleta["overlay"]

    if is_capa:
        corpo = f"""
<div class="slide-inner capa">
  <div class="num-badge">01 / {total:02d}</div>
  <div class="emoji-big">{emoji}</div>
  <h1 class="titulo-capa">{titulo}</h1>
  <div class="subtema">{tema.upper()}</div>
  <div class="bar-accent"></div>
</div>
"""
    elif is_cta:
        corpo = f"""
<div class="slide-inner cta">
  <div class="num-badge">{num:02d} / {total:02d}</div>
  <div class="emoji-big">{emoji}</div>
  <h2 class="titulo-cta">{titulo}</h2>
  <p class="texto-cta">{texto}</p>
  <div class="cta-pill">SALVA ✦ COMPARTILHA ✦ SEGUE</div>
</div>
"""
    else:
        corpo = f"""
<div class="slide-inner conteudo">
  <div class="num-badge">{num:02d} / {total:02d}</div>
  <div class="tag-topo">{emoji} {tema.upper()}</div>
  <h2 class="titulo-slide">{titulo}</h2>
  <div class="divider-line"></div>
  <p class="texto-slide">{texto}</p>
</div>
"""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&display=swap');
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  width: 1080px; height: 1080px;
  overflow: hidden;
  font-family: 'DM Sans', sans-serif;
  background: {bg_color};
  position: relative;
}}
.bg-img {{
  position: absolute; inset: 0;
  background: url('{img_url}') center/cover no-repeat;
  filter: saturate(1.1) brightness(0.85);
}}
.overlay {{
  position: absolute; inset: 0;
  background: {overlay_color};
  opacity: 0.62;
}}
.grain {{
  position: absolute; inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E");
  opacity: 0.35;
  pointer-events: none;
}}
.side-bar {{
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 8px;
  background: linear-gradient(to bottom, {accent}, {accent2});
}}
.marca {{
  position: absolute;
  bottom: 40px; right: 48px;
  font-family: 'Bebas Neue', sans-serif;
  font-size: 18px;
  color: rgba(255,255,255,0.35);
  letter-spacing: 3px;
}}
.slide-inner {{
  position: absolute; inset: 0;
  padding: 72px 72px 72px 88px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  color: {text_color};
}}
.num-badge {{
  position: absolute;
  top: 44px; right: 52px;
  font-family: 'Bebas Neue', sans-serif;
  font-size: 16px;
  letter-spacing: 3px;
  color: rgba(255,255,255,0.5);
}}
.capa {{ justify-content: flex-end; padding-bottom: 100px; }}
.emoji-big {{
  font-size: 64px;
  margin-bottom: 24px;
  filter: drop-shadow(0 4px 12px rgba(0,0,0,0.4));
}}
.titulo-capa {{
  font-family: 'Bebas Neue', sans-serif;
  font-size: 96px;
  line-height: 0.95;
  color: #fff;
  text-shadow: 0 4px 24px rgba(0,0,0,0.5);
  margin-bottom: 20px;
  max-width: 800px;
}}
.subtema {{
  font-size: 14px;
  letter-spacing: 5px;
  color: {accent};
  font-weight: 600;
  margin-bottom: 24px;
}}
.bar-accent {{
  width: 80px; height: 4px;
  background: linear-gradient(90deg, {accent}, {accent2});
  border-radius: 2px;
}}
.tag-topo {{
  font-size: 13px;
  letter-spacing: 4px;
  color: {accent};
  font-weight: 600;
  text-transform: uppercase;
  margin-bottom: 28px;
}}
.titulo-slide {{
  font-family: 'Bebas Neue', sans-serif;
  font-size: 72px;
  line-height: 1.0;
  color: #fff;
  text-shadow: 0 2px 20px rgba(0,0,0,0.6);
  margin-bottom: 24px;
  max-width: 820px;
}}
.divider-line {{
  width: 56px; height: 3px;
  background: linear-gradient(90deg, {accent}, {accent2});
  border-radius: 2px;
  margin-bottom: 28px;
}}
.texto-slide {{
  font-size: 26px;
  line-height: 1.65;
  color: rgba(255,255,255,0.92);
  max-width: 820px;
  font-weight: 400;
  text-shadow: 0 2px 12px rgba(0,0,0,0.7);
}}
.cta {{ align-items: center; text-align: center; padding: 80px; }}
.titulo-cta {{
  font-family: 'Bebas Neue', sans-serif;
  font-size: 80px;
  color: #fff;
  line-height: 1.0;
  margin-bottom: 24px;
  text-shadow: 0 4px 24px rgba(0,0,0,0.5);
}}
.texto-cta {{
  font-size: 26px;
  color: rgba(255,255,255,0.8);
  max-width: 700px;
  line-height: 1.6;
  margin-bottom: 40px;
  font-weight: 300;
}}
.cta-pill {{
  background: linear-gradient(135deg, {accent}, {accent2});
  color: #fff;
  font-family: 'Bebas Neue', sans-serif;
  font-size: 22px;
  letter-spacing: 4px;
  padding: 18px 48px;
  border-radius: 100px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}}
</style>
</head>
<body>
<div class="bg-img"></div>
<div class="overlay"></div>
<div class="grain"></div>
<div class="side-bar"></div>
{corpo}
<div class="marca">@baladaroyalle</div>
</body>
</html>"""
    return html

# ── RENDERIZA HTML → PNG usando Playwright ───────────────────────
def checar_dependencias():
    try:
        import playwright
        return "playwright"
    except ImportError:
        pass
    try:
        from selenium import webdriver
        return "selenium"
    except ImportError:
        pass
    return None

def html_para_png_playwright(html_path: str, png_path: str):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1080})
        page.goto(f"file:///{html_path.replace(chr(92), '/')}")
        page.wait_for_timeout(1500)
        page.screenshot(path=png_path, full_page=False)
        browser.close()

def html_para_png_selenium(html_path: str, png_path: str):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1080,1080")
    driver = webdriver.Chrome(options=opts)
    driver.get(f"file:///{html_path.replace(chr(92), '/')}")
    time.sleep(2)
    driver.save_screenshot(png_path)
    driver.quit()

def html_para_png(html_path: str, png_path: str, engine: str):
    if engine == "playwright":
        html_para_png_playwright(html_path, png_path)
    elif engine == "selenium":
        html_para_png_selenium(html_path, png_path)
    else:
        raise RuntimeError("Playwright ou Selenium necessário para renderizar PNGs.")

# ── CHAMA CLAUDE API ─────────────────────────────────────────────
def gerar_conteudo_claude(tema: str, plataforma: str, api_key: str) -> dict:
    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Você é um estrategista de conteúdo viral especializado em {plataforma}.

Crie um carrossel de 7 slides sobre: "{tema}"

Regras de conteúdo:
- Slide 1: gancho impossível de ignorar (número ou provocação forte)
- Slides 2-6: 1 insight poderoso por slide, linguagem brasileira direta
- Slide 7: CTA com urgência real
- Cada slide: texto corrido de 3 a 5 linhas, rico em detalhes e contexto. Não resuma demais — explique, exemplifique, provoque.

Para cada slide, sugira um "query_imagem" em INGLÊS para buscar no Pexels.
Ex: "dark moody technology city night", "person working laptop coffee"
O query deve combinar COM O TEMA do slide — seja específico e visual.

Responda APENAS JSON válido:
{{
  "titulo_serie": "...",
  "paleta": {{
    "nome": "dark-orange",
    "bg": "#0a0a0a",
    "accent": "#FF4D00",
    "accent2": "#FF8C42",
    "text": "#ffffff",
    "overlay": "linear-gradient(160deg, rgba(0,0,0,0.75) 0%, rgba(10,10,10,0.92) 100%)"
  }},
  "hashtags": ["...", "..."],
  "melhor_horario": "19:00",
  "slides": [
    {{
      "numero": 1,
      "emoji": "🔥",
      "titulo": "...",
      "texto": "...",
      "query_imagem": "..."
    }}
  ]
}}

Paletas sugeridas por tom:
- Urgente/impacto: accent #FF4D00, bg #0a0a0a
- Premium/luxo: accent #C9A84C, bg #0d0d0d
- Tech/futuro: accent #00E5FF, bg #050510
- Growth/verde: accent #00E676, bg #071a0e
Escolha a que melhor combina com o tema."""

    resposta = ""
    print(f"\n {PURPLE}▶ claude-sonnet-4-6 → streaming...{RESET}\n")
    print(f" {GRAY}{'─'*52}{RESET}")
    print(f" {DIM}", end="")

    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    ) as stream:
        for text in stream.text_stream:
            resposta += text
            sys.stdout.write(text)
            sys.stdout.flush()

    print(f"{RESET}\n {GRAY}{'─'*52}{RESET}\n")

    json_str = resposta.strip()
    if "```" in json_str:
        json_str = re.sub(r'```(?:json)?', '', json_str).strip()
    try:
        return json.loads(json_str)
    except Exception:
        match = re.search(r'\{.*\}', json_str, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError("Não foi possível parsear JSON da resposta do Claude.")

# ── MAIN ─────────────────────────────────────────────────────────
def main():
    cls()
    print()
    slow_print(f"{ORANGE}{BOLD} ╔══════════════════════════════════════════════════════╗{RESET}", 0.01)
    slow_print(f"{ORANGE}{BOLD} ║ 🤖 AGÊNCIA DE CONTEÚDO · CLAUDE AI · v2.0 ║{RESET}", 0.01)
    slow_print(f"{ORANGE}{BOLD} ║ Carrosséis visuais prontos para postar ║{RESET}", 0.01)
    slow_print(f"{ORANGE}{BOLD} ╚══════════════════════════════════════════════════════╝{RESET}", 0.01)
    print()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print(f" {YELLOW}🔑 Claude API Key:{RESET} ", end="")
        api_key = input().strip()
        if not api_key:
            print(f"\n {RED}✗ Configure ANTHROPIC_API_KEY{RESET}\n")
            sys.exit(1)

    pexels_key = os.environ.get("PEXELS_API_KEY", "")
    if not pexels_key:
        print(f"\n {YELLOW}📷 Pexels API Key {GRAY}(Enter para usar Picsum como fallback):{RESET} ", end="")
        pexels_key = input().strip()
        if pexels_key:
            print(f" {GREEN}✓{RESET} Pexels ativado — imagens temáticas de alta qualidade")
        else:
            print(f" {GRAY}→ Sem Pexels Key — usando Picsum (imagens genéricas bonitas)")

    print(f"\n {WHITE}📋 Tema do carrossel:{RESET}")
    print(f" {GRAY} (Enter = 'Como ganhar dinheiro com IA em 2026'){RESET}")
    print(f" {CYAN}▶ {RESET}", end="")
    tema = input().strip() or "Como ganhar dinheiro com IA em 2026"

    print(f"\n {WHITE}📱 Plataforma? {GRAY}[1] Instagram [2] LinkedIn [Enter=Instagram]{RESET}")
    print(f" {CYAN}▶ {RESET}", end="")
    plataforma = {"2": "LinkedIn"}.get(input().strip(), "Instagram")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_pasta = f"carrossel_{ts}"
    pasta = Path(nome_pasta)
    pasta.mkdir(exist_ok=True)
    pasta_html = pasta / "html"
    pasta_html.mkdir(exist_ok=True)

    print(f"\n {GREEN}✓{RESET} Salvando em: {CYAN}{BOLD}{pasta}/{RESET}\n")
    line()

    print()
    spinner("Verificando dependências de renderização...", 1.0)
    engine = checar_dependencias()

    if not engine:
        print(f"\n {YELLOW}⚠ Playwright não encontrado.{RESET}")
        engine = "html_only"

    print()
    loading_bar("🧠 Claude gerando estratégia e conteúdo...", 2.5)

    dados = gerar_conteudo_claude(tema, plataforma, api_key)

    slides = dados.get("slides", [])
    paleta = dados.get("paleta", {
        "bg": "#0a0a0a", "accent": "#FF4D00", "accent2": "#FF8C42",
        "text": "#ffffff",
        "overlay": "linear-gradient(160deg, rgba(0,0,0,0.75) 0%, rgba(10,10,10,0.92) 100%)"
    })
    hashtags = dados.get("hashtags", [])
    horario = dados.get("melhor_horario", "19:00")
    serie = dados.get("titulo_serie", tema)

    print(f" {GREEN}✓{RESET} {BOLD}{WHITE}{len(slides)} slides gerados{RESET}")
    print(f" {GREEN}✓{RESET} Paleta: {CYAN}{paleta.get('nome','custom')}{RESET}")
    print(f" {GREEN}✓{RESET} Série: {CYAN}{serie}{RESET}\n")
    line()

    print(f"\n {ORANGE}{BOLD} RENDERIZANDO SLIDES{RESET}\n")

    arquivos_png = []

    for slide in slides:
        num = slide.get("numero", 1)
        titulo = slide.get("titulo", "")
        query = slide.get("query_imagem", tema)

        print(f" {CYAN}[{num:02d}/{len(slides):02d}]{RESET} {WHITE}{titulo[:50]}{RESET}")
        print(f" {GRAY} 📷 baixando imagem: {query}{RESET}")

        img_path = pasta / f"img_{num:02d}.jpg"
        img_local = ""
        try:
            img_local = baixar_imagem(query, img_path, pexels_key)
            print(f" {GREEN} ✓ imagem salva localmente{RESET}")
        except Exception as e:
            print(f" {YELLOW} ⚠ falha ao baixar imagem: {e}{RESET}")

        html_content = gerar_html_slide(slide, len(slides), tema, paleta, img_local)
        html_path = pasta_html / f"slide_{num:02d}.html"
        html_path.write_text(html_content, encoding="utf-8")

        png_path = pasta / f"slide_{num:02d}.png"

        if engine != "html_only":
            try:
                spinner(f" Renderizando slide {num:02d}...", 2.5)
                html_para_png(str(html_path.absolute()), str(png_path), engine)
                arquivos_png.append(png_path)
                print(f" {GREEN} ✓ slide_{num:02d}.png{RESET}")
            except Exception as e:
                print(f" {YELLOW} ⚠ Erro ao renderizar: {e}{RESET}")
                print(f" {GRAY} → HTML salvo em html/slide_{num:02d}.html{RESET}")
        else:
            print(f" {YELLOW} → HTML: html/slide_{num:02d}.html{RESET}")

        time.sleep(0.2)

    meta = {
        "tema": tema,
        "plataforma": plataforma,
        "serie": serie,
        "gerado_em": datetime.now().isoformat(),
        "melhor_horario": horario,
        "hashtags": hashtags,
        "paleta": paleta,
        "slides": slides,
        "arquivos": [str(p) for p in arquivos_png]
    }
    (pasta / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    line("═")
    print(f"\n {GREEN}{BOLD} ✅ CARROSSEL PRONTO!{RESET}\n")
    print(f" {WHITE}📁 Pasta:{RESET} {CYAN}{BOLD}{pasta}/{RESET}")

    if arquivos_png:
        print(f" {WHITE}🖼️ PNGs:{RESET} {GREEN}{len(arquivos_png)} imagens 1080×1080px{RESET}")
    else:
        print(f" {WHITE}📄 HTMLs:{RESET} {YELLOW}{len(slides)} arquivos em html/{RESET}")

    print(f" {WHITE}⏰ Postar:{RESET} {CYAN}{horario}{RESET}")
    print(f" {WHITE}🏷️ Tags:{RESET} {GRAY}{' '.join('#'+h for h in hashtags[:6])}{RESET}")
    print()
    print(f" {ORANGE}{BOLD} 🤖 Powered by Claude AI · Anthropic{RESET}")
    print(f" {GRAY} @leolamerabr{RESET}\n")
    line("═")
    print()

if __name__ == "__main__":
    main()

import os, re, json, asyncio
from pathlib import Path
import urllib.request, urllib.parse
import anthropic

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PEXELS_API_KEY    = os.getenv("PEXELS_API_KEY", "")

# ── Color helpers ──────────────────────────────────────────────────
def _hex_rgb(h: str) -> str:
    h = h.lstrip("#")
    if len(h) == 6:
        try:
            return f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"
        except ValueError:
            pass
    return "140,255,46"

def _extract_colors(cores_marca: str):
    """Extract up to 2 hex colors. If only 1 provided, derives accent2 as a darker shade."""
    hexes = re.findall(r'#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', cores_marca or "")
    accent = hexes[0] if hexes else "#8CFF2E"
    if len(hexes) >= 2:
        accent2 = hexes[1]
    elif hexes:
        # Deriva accent2 como versão escurecida (55%) da cor primária
        h = accent.lstrip("#")
        if len(h) == 3:
            h = h[0]*2 + h[1]*2 + h[2]*2
        try:
            r = max(0, int(int(h[0:2], 16) * 0.55))
            g = max(0, int(int(h[2:4], 16) * 0.55))
            b = max(0, int(int(h[4:6], 16) * 0.55))
            accent2 = f"#{r:02x}{g:02x}{b:02x}"
        except ValueError:
            accent2 = "#444444"
    else:
        accent2 = "#ff6a00"
    return accent, accent2

def _apply_highlight(titulo: str, highlight: str, accent: str) -> str:
    """Wrap highlight substring in a colored span."""
    if highlight and highlight in titulo:
        return titulo.replace(
            highlight,
            f'<span style="color:{accent}">{highlight}</span>',
            1,
        )
    return titulo

def _font_size(titulo: str, sz_sm: int = 48, sz_md: int = 58, sz_lg: int = 72) -> int:
    n = len(titulo)
    if n < 30: return sz_lg
    if n < 50: return sz_md
    return sz_sm

# ── Prompt builder v2 ─────────────────────────────────────────────
_TEMPLATE_NAMES = {
    "1":  "authority_dark",
    "2":  "clean_editorial",
    "3":  "vibrant_gradient",
    "4":  "foto_bold",
    "5":  "minimal_type",
    "6":  "x_thread",
    "6d": "x_thread_dark",
    "7":  "linkedin_blur",
    "7d": "linkedin_blur_dark",
    "8":  "studio_shodwe",
    "9":  "serif_elegante",
    "10": "brands_decoded",
}
_TEMPLATE_HINTS = {
    "authority_dark":    "Títulos bold e curtos. Uma palavra/frase em titulo_highlight (substring exata). Tom: autoridade, premium. Sem emoji no corpo.",
    "clean_editorial":   "Linguagem elaborada. Listas numeradas são bem-vindas. Tom: profissional, refinado.",
    "vibrant_gradient":  "Energia alta. Verbos de ação. Emojis ocasionais no corpo. Tom: motivacional.",
    "foto_bold":         "Headline único e poderoso (máx 6 palavras). Corpo mínimo. A foto carrega o visual.",
    "minimal_type":      "Frases filosóficas, dados isolados ou perguntas provocadoras. Use dado_destaque para estatísticas. Máx 1 ideia por slide. Corpo curto.",
    "x_thread":          "Estilo tweet real. Cada slide = 1 tweet da thread. titulo é o gancho do tweet (max 8 palavras). corpo é o desenvolvimento (max 280 chars, linguagem conversacional, opinativa). Use lista para threads com bullets. Nada de formatação excessiva — texto limpo como um tweet real.",
    "x_thread_dark":     "Igual x_thread mas versão dark mode. Mesma linguagem de tweet real.",
    "linkedin_blur":     "Tom profissional LinkedIn. Título direto e de impacto (max 8 palavras). Corpo denso com dado/insight real. Use dado_destaque para estatísticas. Sem emoji. Slides limpos.",
    "linkedin_blur_dark":"Igual linkedin_blur mas versão dark. Mesmo tom profissional.",
    "studio_shodwe":     "Tom elegante e reflexivo. Frases com pausa — 'Eu digo não / para qualquer coisa'. Corpo complementa com contexto. Mistura peso na capa (frase light + palavra-chave bold italic). Espaço em branco é intencionado.",
    "serif_elegante":    "Tom suave, lifestyle, bem-estar. Títulos em caps display serif (Cormorant). Números como marcadores de passo. Corpo leve e conversacional. Use lista para passos numerados.",
    "brands_decoded":    "Tom direto, polêmico, confrontador. Títulos em ALL CAPS condensed. Use titulo_highlight para destacar a palavra mais impactante. Corpo tem 2 camadas: afirmação bold + explicação sublinhada. Linguagem de manifesto de marca.",
}
_PLAT_HINTS = {
    "Instagram": "Tom emocional, próximo, 'você'. Frases curtas. Hashtags no campo hashtags. Melhor horário: 19h-21h.",
    "LinkedIn":  "Tom profissional, primeira pessoa, autoridade. Dados e insights. Evite emoji em excesso. Melhor horário: 8h-10h.",
    "TikTok":    "Linguagem jovem, gírias, provocativo. Gancho BRUTAL no slide 1. Frases curtíssimas. Melhor horário: 18h-22h.",
    "X (Twitter)": "Conciso, opinativo, sem rodeios. Cada slide = tweet polêmico mas verdadeiro. Melhor horário: 12h-14h.",
}

_FINALIDADE_HINTS = {
    "1":           "Objetivo: EDUCAR. Entregue valor real e conhecimento prático.",
    "educacional": "Objetivo: EDUCAR. Entregue valor real e conhecimento prático.",
    "2":           "Objetivo: VENDER. Mostre o problema, a solução e o benefício claro.",
    "vender":      "Objetivo: VENDER. Mostre o problema, a solução e o benefício claro.",
    "3":           "Objetivo: ENGAJAMENTO. Provoque reações, discordâncias e discussões.",
    "engajamento": "Objetivo: ENGAJAMENTO. Provoque reações, discordâncias e discussões.",
    "4":           "Objetivo: AUTORIDADE. Posicione como referência máxima no nicho.",
    "awareness":   "Objetivo: AUTORIDADE. Posicione como referência máxima no nicho.",
}
_CTA_HINTS = {
    "1":           "CTA do slide 7: direcionar para o LINK NA BIO (produto, página ou recurso).",
    "link_bio":    "CTA do slide 7: direcionar para o LINK NA BIO (produto, página ou recurso).",
    "2":           "CTA do slide 7: pedir para SEGUIR O PERFIL para mais conteúdo assim.",
    "seguir":      "CTA do slide 7: pedir para SEGUIR O PERFIL para mais conteúdo assim.",
    "3":           "CTA do slide 7: pedir para SALVAR e COMPARTILHAR com quem precisa.",
    "compartilhar":"CTA do slide 7: pedir para SALVAR e COMPARTILHAR com quem precisa.",
    "4":           "CTA do slide 7: pedir para COMENTAR (pergunta específica para debate).",
    "comentar":    "CTA do slide 7: pedir para COMENTAR (pergunta específica para debate).",
}


def construir_prompt(
    tema: str,
    plataforma: str,
    nicho: str = "",
    restricoes: str = "",
    cores_marca: str = "",
    template: str = "4",
    username: str = "",
    finalidade: str = "",
    cta_objetivo: str = "",
) -> str:
    tname    = _TEMPLATE_NAMES.get(str(template), _TEMPLATE_NAMES.get(_NAME_TO_NUM.get(str(template).lower().strip(), "4"), "foto_bold"))
    plat_hint = _PLAT_HINTS.get(plataforma, _PLAT_HINTS["Instagram"])
    tpl_hint  = _TEMPLATE_HINTS.get(tname, "")

    ctx_nicho      = f"\nNicho/segmento: {nicho}"       if nicho       else ""
    ctx_restricoes = f"\nRESTRIÇÕES — nunca mencione: {restricoes}" if restricoes else ""
    ctx_cores      = f"\nCores da marca: {cores_marca}"  if cores_marca else ""
    ctx_user       = f"\nUsername: @{username}"          if username    else ""
    ctx_finalidade = f"\n{_FINALIDADE_HINTS.get(finalidade, '')}" if finalidade else ""
    ctx_cta        = f"\n{_CTA_HINTS.get(cta_objetivo, '')}"      if cta_objetivo else ""

    return f"""Você é o motor de copy estratégico do BEMKT — plataforma de carrosséis virais.

CONTEXTO:
- Tema: {tema}
- Plataforma: {plataforma}
- Template visual: {tname}{ctx_nicho}{ctx_cores}{ctx_user}{ctx_restricoes}{ctx_finalidade}{ctx_cta}

INSTRUÇÕES DE PLATAFORMA: {plat_hint}
ADAPTE AO TEMPLATE: {tpl_hint}

FRAMEWORK — 7 SLIDES:
- Slide 1 (gancho): Tensão irresistível. NUNCA entregue a resposta. Máx 8 palavras no título.
- Slide 2 (setup): Confirme o valor. Contextualize com dado/estatística.
- Slides 3-5 (conteudo): 1 ideia completa por slide. Dado específico + exemplo/analogia.
- Slide 6 (virada): Insight mais compartilhável. Inversão de crença ou conclusão contraintuitiva.
- Slide 7 (cta): 1 CTA apenas — use o CTA objetivo definido acima.

REGRAS ABSOLUTAS:
1. Títulos: máx 8 palavras, diretos.
2. corpo: máx 35 palavras por slide. Se precisar mais, o slide está errado.
3. titulo_highlight: palavra/frase EXATA do titulo que recebe cor de destaque (substring).
4. dado_destaque: use em slides de estatística (ex: "87%", "R$ 4.2bi").
5. lista: use quando houver 3+ itens estruturados, null nos demais.
6. query_pexels: termos em inglês para buscar foto no Pexels.
7. legenda_instagram: legenda completa para o post, adaptada à finalidade e ao CTA objetivo.

Responda APENAS JSON válido, sem markdown, sem texto fora do JSON:
{{
  "tema": "{tema}",
  "plataforma": "{plataforma}",
  "template": "{tname}",
  "slides": [
    {{
      "numero": 1,
      "tipo": "gancho",
      "layout": "hero",
      "categoria_label": "MÁXIMO 3 PALAVRAS",
      "titulo": "O título aqui",
      "titulo_highlight": "destaque",
      "corpo": "texto secundário (vazio no slide 1 é ok)",
      "lista": null,
      "dado_destaque": null,
      "cta": null
    }}
  ],
  "legenda_instagram": "legenda completa com emojis e hashtags",
  "hashtags": ["#tag1", "#tag2"],
  "query_pexels": "termos em inglês para pexels"
}}"""

# ── JSON parser ────────────────────────────────────────────────────
def parse_json_resposta(resposta: str) -> dict:
    s = resposta.strip()
    if "```" in s:
        s = re.sub(r'```(?:json)?', '', s).strip()
    try:
        return json.loads(s)
    except Exception:
        match = re.search(r'\{.*\}', s, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        raise ValueError("Não foi possível parsear JSON da resposta do Claude.")

# ── Download de imagem ─────────────────────────────────────────────
def baixar_imagem(query: str, destino: Path, pexels_key: str = "", width=1080, height=1080, slide_index: int = 0) -> str:
    headers = {"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0"}
    if pexels_key:
        try:
            q = urllib.parse.quote(query)
            req = urllib.request.Request(
                f"https://api.pexels.com/v1/search?query={q}&per_page=15&orientation=square",
                headers={**headers, "Authorization": pexels_key}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                fotos = json.loads(resp.read()).get("photos", [])
                if fotos:
                    foto = fotos[slide_index % len(fotos)]
                    req2 = urllib.request.Request(foto["src"]["large2x"], headers=headers)
                    with urllib.request.urlopen(req2, timeout=15) as r:
                        destino.write_bytes(r.read())
                    return str(destino.absolute())
        except Exception:
            pass
    seed = abs(hash(query + str(slide_index))) % 1000
    req = urllib.request.Request(f"https://picsum.photos/seed/{seed}/{width}/{height}", headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        destino.write_bytes(r.read())
    return str(destino.absolute())

# ── Avatar Instagram ───────────────────────────────────────────────
def buscar_avatar_instagram(username: str, destino: Path) -> str:
    """Busca avatar público do Instagram via scrape da página de perfil.
    Retorna caminho local do arquivo salvo, ou string vazia se falhar."""
    if not username:
        return ""
    handle = username.lstrip("@").strip()
    if not handle:
        return ""
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
        "Accept-Language": "pt-BR,pt;q=0.9",
    }
    try:
        url = f"https://www.instagram.com/{handle}/?__a=1&__d=dis"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
            pic_url = (
                data.get("graphql", {}).get("user", {}).get("profile_pic_url_hd")
                or data.get("graphql", {}).get("user", {}).get("profile_pic_url")
            )
            if pic_url:
                req2 = urllib.request.Request(pic_url, headers={"User-Agent": headers["User-Agent"]})
                with urllib.request.urlopen(req2, timeout=10) as r2:
                    destino.write_bytes(r2.read())
                return str(destino.absolute())
    except Exception:
        pass
    # Fallback: scrape da página HTML pública
    try:
        req = urllib.request.Request(f"https://www.instagram.com/{handle}/", headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            html = r.read().decode("utf-8", errors="ignore")
        match = re.search(r'"profile_pic_url_hd":"(https://[^"]+)"', html)
        if not match:
            match = re.search(r'"profile_pic_url":"(https://[^"]+)"', html)
        if match:
            pic_url = match.group(1).replace("\\u0026", "&")
            req2 = urllib.request.Request(pic_url, headers={"User-Agent": headers["User-Agent"]})
            with urllib.request.urlopen(req2, timeout=10) as r2:
                destino.write_bytes(r2.read())
            return str(destino.absolute())
    except Exception:
        pass
    return ""

# ── Font imports ───────────────────────────────────────────────────
_INTER   = "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');"
_SPACE   = "@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');"
_CORMO   = "@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600;700&family=DM+Sans:wght@300;400;500;600&display=swap');"
_POPPINS = "@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700;900&display=swap');"
_BEBAS   = "@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&display=swap');"
_SYNE    = "@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Inter:wght@400;500;600&display=swap');"

# ══════════════════════════════════════════════════════════════════
# TEMPLATE 1 — Authority Dark
# #080808, Inter Black 900, acento neon, espaço em branco dominante
# ══════════════════════════════════════════════════════════════════
def _html_authority_dark(
    slide: dict,
    total: int,
    tema: str,
    accent: str,
    accent2: str,
    logo_url: str | None,
    username: str,
) -> str:
    num      = slide.get("numero", 1)
    tipo     = slide.get("tipo", "conteudo")
    layout   = slide.get("layout", "hero")
    titulo   = slide.get("titulo", "")
    hl       = slide.get("titulo_highlight", "")
    corpo    = slide.get("corpo") or slide.get("texto", "")
    lista    = slide.get("lista") or []
    cat      = (slide.get("categoria_label") or tema).upper()[:24]
    dado     = slide.get("dado_destaque", "") or ""
    cta_txt  = slide.get("cta", "") or corpo

    is_capa = (num == 1)
    is_cta  = (num == total)

    a_rgb = _hex_rgb(accent)
    ts    = _font_size(titulo, 48, 60, 74)
    th    = _apply_highlight(titulo, hl, accent)

    logo_tag = (
        f'<img src="{logo_url}" style="max-height:38px;max-width:120px;'
        f'object-fit:contain;filter:brightness(0) invert(1);opacity:0.55">'
        if logo_url else ""
    )

    def _lista_items() -> str:
        if not lista:
            return ""
        lis = "".join(
            f'<li><span class="dot" style="background:{accent};'
            f'box-shadow:0 0 8px rgba({a_rgb},0.8)"></span>{item}</li>'
            for item in lista
        )
        return f'<ul class="lista">{lis}</ul>'

    # ── Layouts ──────────────────────────────────────────────────
    if is_capa:
        body = f"""
<div class="label" style="color:{accent}">{cat} · SLIDE 01</div>
<h1 class="titulo" style="font-size:{min(ts+16,90)}px">{th}</h1>
<div class="sep" style="background:{accent}"></div>
<p class="corpo">{corpo}</p>"""

    elif is_cta:
        body = f"""
<div class="label" style="color:{accent}">PRÓXIMO PASSO</div>
<h2 class="titulo" style="font-size:{ts}px">{th}</h2>
<div class="sep" style="background:{accent}"></div>
<p class="corpo">{cta_txt}</p>
<div class="cta-pill" style="background:{accent};color:#080808">
  SALVA &nbsp;·&nbsp; COMPARTILHA &nbsp;·&nbsp; SEGUE
</div>"""

    elif layout == "citacao":
        body = f"""
<div class="quote-mark" style="color:{accent}">"</div>
<p class="citacao-txt">{corpo}</p>
<div class="sep" style="background:{accent};width:40px"></div>
<div class="label" style="color:{accent}">{cat}</div>"""

    elif layout == "numero":
        body = f"""
<div class="layout-numero">
  <div class="num-giant" style="color:{accent};text-shadow:0 0 60px rgba({a_rgb},0.25)">{num:02d}</div>
  <div class="num-right">
    <h2 class="titulo" style="font-size:{ts}px">{th}</h2>
    <div class="sep" style="background:{accent}"></div>
    <p class="corpo">{corpo}</p>
    {_lista_items()}
  </div>
</div>"""

    elif layout == "split":
        body = f"""
<div class="layout-split">
  <div class="split-l">
    <div class="label" style="color:{accent}">{cat}</div>
    <h2 class="titulo" style="font-size:{ts}px">{th}</h2>
  </div>
  <div class="split-r">
    <p class="corpo">{corpo}</p>
    {_lista_items()}
  </div>
</div>"""

    else:  # hero (default)
        dado_block = (
            f'<div class="dado" style="color:{accent}">{dado}</div>'
            if dado else ""
        )
        body = f"""
<div class="label" style="color:{accent}">{cat} · {num:02d}</div>
<h2 class="titulo" style="font-size:{ts}px">{th}</h2>
<div class="sep" style="background:{accent}"></div>
{dado_block}
<p class="corpo">{corpo}</p>
{_lista_items()}"""

    css = f"""
{_INTER}
*{{margin:0;padding:0;box-sizing:border-box;list-style:none}}
body{{width:1080px;height:1080px;overflow:hidden;background:#080808;
     font-family:'Inter',sans-serif;color:#f0f0f0;position:relative}}
.logo-area{{position:absolute;top:44px;left:60px;z-index:20}}
.rodape{{position:absolute;bottom:48px;left:60px;right:60px;
         display:flex;justify-content:space-between;align-items:center;z-index:20}}
.username{{font-size:12px;color:#3a3a3a;font-weight:500;letter-spacing:0.5px}}
.pg{{font-size:12px;color:#2e2e2e;font-weight:600;font-variant-numeric:tabular-nums}}
.main{{position:absolute;top:110px;left:60px;right:60px;bottom:90px;
       display:flex;flex-direction:column;justify-content:center;z-index:5}}
.label{{font-size:12px;font-weight:600;letter-spacing:0.18em;
        text-transform:uppercase;margin-bottom:28px}}
.titulo{{font-weight:900;line-height:1.08;color:#fff;margin-bottom:22px;max-width:920px}}
.sep{{width:60px;height:2px;border-radius:1px;margin-bottom:22px}}
.corpo{{font-size:20px;font-weight:400;color:#888;line-height:1.65;max-width:860px}}
.dado{{font-size:72px;font-weight:900;line-height:1;letter-spacing:-2px;margin-bottom:8px}}
.lista{{display:flex;flex-direction:column;gap:16px;margin-top:20px;max-width:860px}}
.lista li{{display:flex;gap:14px;align-items:flex-start;
           font-size:19px;color:#999;line-height:1.55;font-weight:400}}
.dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0;margin-top:8px}}
.cta-pill{{display:inline-block;font-size:13px;font-weight:800;
           letter-spacing:0.2em;padding:18px 44px;border-radius:100px;margin-top:28px}}
/* citacao */
.quote-mark{{font-size:130px;line-height:0.7;font-weight:900;opacity:0.9;margin-bottom:8px}}
.citacao-txt{{font-size:30px;font-weight:500;color:#ddd;line-height:1.5;
              max-width:840px;margin-bottom:24px}}
/* layout-numero */
.layout-numero{{display:flex;gap:40px;align-items:flex-start}}
.num-giant{{font-size:190px;font-weight:900;line-height:0.82;
            flex-shrink:0;min-width:220px;opacity:0.9;font-variant-numeric:tabular-nums}}
.num-right{{display:flex;flex-direction:column;flex:1;padding-top:20px}}
/* layout-split */
.layout-split{{display:grid;grid-template-columns:1fr 1fr;gap:56px;align-items:start}}
.split-l{{display:flex;flex-direction:column;gap:20px}}
.split-r{{display:flex;flex-direction:column;gap:14px;padding-top:44px}}
"""

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>{css}</style></head><body>
<div class="logo-area">{logo_tag}</div>
<div class="main">{body}</div>
<div class="rodape">
  <span class="username">{'@' + username if username else ''}</span>
  <span class="pg">{num:02d} / {total:02d}</span>
</div>
</body></html>"""


# ══════════════════════════════════════════════════════════════════
# TEMPLATE 2 — Clean Editorial
# Off-white, Cormorant Garamond serif, detalhes finos em cor de marca
# ══════════════════════════════════════════════════════════════════
def _html_clean_editorial(
    slide: dict,
    total: int,
    tema: str,
    accent: str,
    logo_url: str | None,
    username: str,
) -> str:
    num     = slide.get("numero", 1)
    titulo  = slide.get("titulo", "")
    hl      = slide.get("titulo_highlight", "")
    corpo   = slide.get("corpo") or slide.get("texto", "")
    lista   = slide.get("lista") or []
    cat     = (slide.get("categoria_label") or tema).upper()[:24]
    dado    = slide.get("dado_destaque", "") or ""
    cta_txt = slide.get("cta", "") or corpo

    is_capa = (num == 1)
    is_cta  = (num == total)

    ts = _font_size(titulo, 52, 66, 80)
    th = _apply_highlight(titulo, hl, accent)

    logo_tag = (
        f'<img src="{logo_url}" style="max-height:38px;max-width:120px;object-fit:contain">'
        if logo_url else ""
    )

    def _lista_items() -> str:
        if not lista:
            return ""
        lis = "".join(
            f'<li><span class="item-n" style="color:{accent}">{str(i+1).zfill(2)}</span>'
            f'<span class="item-t">{item}</span></li>'
            for i, item in enumerate(lista)
        )
        return f'<ul class="lista">{lis}</ul>'

    if is_capa:
        body = f"""
<div class="accent-bar" style="background:{accent}"></div>
<div class="capa-wrap">
  <div class="capa-top">
    <div class="badge" style="color:{accent};border-color:{accent}">{cat}</div>
    <div class="pg">01 / {total:02d}</div>
  </div>
  <div class="capa-center">
    <h1 class="titulo" style="font-size:{min(ts+12,96)}px;color:#0d0d0d">{th}</h1>
    <div class="rule" style="background:{accent}"></div>
    <p class="corpo" style="color:#555">{corpo}</p>
  </div>
  <div class="capa-foot">
    <div class="serie">UMA SÉRIE EM {total:02d} PARTES</div>
  </div>
</div>"""

    elif is_cta:
        body = f"""
<div class="accent-bar" style="background:{accent}"></div>
<div class="cta-wrap">
  <div class="pg" style="text-align:right;margin-bottom:56px">{num:02d} / {total:02d}</div>
  <h2 class="titulo" style="font-size:{ts}px;color:#0d0d0d;text-align:center">{th}</h2>
  <div class="rule" style="background:{accent};margin:28px auto"></div>
  <p class="corpo" style="color:#555;text-align:center">{cta_txt}</p>
  <div class="cta-pill" style="background:#0d0d0d;color:#fff">
    SALVA · COMPARTILHA · SEGUE
  </div>
</div>"""

    else:
        dado_block = (
            f'<div class="dado" style="color:{accent}">{dado}</div>'
            if dado else ""
        )
        body = f"""
<div class="accent-bar" style="background:{accent}"></div>
<div class="content-wrap">
  <div class="content-top">
    <div class="badge" style="color:{accent};border-color:{accent}">{cat}</div>
    <div class="pg">{num:02d} / {total:02d}</div>
  </div>
  <div class="ghost-n" style="color:{accent};opacity:0.06">{num:02d}</div>
  <div class="content-body">
    <h2 class="titulo" style="font-size:{ts}px;color:#0d0d0d">{th}</h2>
    <div class="rule" style="background:{accent}"></div>
    {dado_block}
    <p class="corpo" style="color:#444">{corpo}</p>
    {_lista_items()}
  </div>
</div>"""

    css = f"""
{_CORMO}
*{{margin:0;padding:0;box-sizing:border-box;list-style:none}}
body{{width:1080px;height:1080px;overflow:hidden;background:#f7f6f4;
     font-family:'DM Sans',sans-serif;color:#0d0d0d;position:relative}}
.logo-area{{position:absolute;top:44px;left:60px;z-index:20}}
.marca{{position:absolute;bottom:44px;right:60px;font-size:11px;
        letter-spacing:4px;color:#bbb;font-weight:500;text-transform:uppercase;z-index:20}}
.accent-bar{{position:absolute;top:0;left:0;right:0;height:5px;z-index:10}}
.pg{{font-size:12px;letter-spacing:3px;color:#bbb;font-weight:500}}
.badge{{font-size:10px;letter-spacing:5px;font-weight:600;text-transform:uppercase;
        border:1px solid;padding:6px 14px;border-radius:2px}}
.rule{{height:2px;width:64px;border-radius:1px;margin-bottom:20px}}
.titulo{{font-family:'Cormorant Garamond',serif;font-weight:700;
         line-height:1.0;max-width:880px;margin-bottom:20px}}
.corpo{{font-size:21px;line-height:1.65;max-width:840px;font-weight:400}}
.dado{{font-size:68px;font-weight:700;font-family:'Cormorant Garamond',serif;
       line-height:1;letter-spacing:-1px;margin-bottom:10px}}
/* Capa */
.capa-wrap{{position:absolute;inset:0;padding:72px 72px 64px;
            display:flex;flex-direction:column;justify-content:space-between;z-index:5}}
.capa-top{{display:flex;justify-content:space-between;align-items:center}}
.capa-center{{display:flex;flex-direction:column;align-items:flex-start;
              flex:1;justify-content:center}}
.capa-foot{{display:flex;justify-content:flex-end}}
.serie{{font-size:10px;letter-spacing:5px;color:#bbb;font-weight:500;text-transform:uppercase}}
/* Content */
.content-wrap{{position:absolute;inset:0;padding:72px 72px 64px;
               display:flex;flex-direction:column;z-index:5}}
.content-top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}}
.ghost-n{{position:absolute;bottom:-40px;right:40px;
          font-family:'Cormorant Garamond',serif;font-weight:700;
          font-size:380px;line-height:1;pointer-events:none}}
.content-body{{display:flex;flex-direction:column;flex:1;justify-content:center;padding:20px 0}}
/* Lista */
.lista{{display:flex;flex-direction:column;gap:18px;margin-top:24px;max-width:840px}}
.lista li{{display:flex;gap:18px;align-items:flex-start}}
.item-n{{font-size:11px;font-weight:700;letter-spacing:2px;flex-shrink:0;margin-top:5px}}
.item-t{{font-size:21px;line-height:1.6;color:#3a3a3a;font-weight:400}}
/* CTA */
.cta-wrap{{position:absolute;inset:0;padding:72px;
           display:flex;flex-direction:column;align-items:center;z-index:5}}
.cta-pill{{font-size:14px;font-weight:600;letter-spacing:4px;
           padding:20px 56px;border-radius:2px;margin-top:28px}}
"""

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>{css}</style></head><body>
<div class="logo-area">{logo_tag}</div>
{body}
<div class="marca">{'@' + username if username else ''}</div>
</body></html>"""


# ══════════════════════════════════════════════════════════════════
# TEMPLATE 3 — Vibrant Gradient
# Gradiente vibrante, Poppins 900, glassmorphism card
# ══════════════════════════════════════════════════════════════════
def _html_vibrant_gradient(
    slide: dict,
    total: int,
    tema: str,
    accent: str,
    accent2: str,
    logo_url: str | None,
    username: str,
) -> str:
    num     = slide.get("numero", 1)
    titulo  = slide.get("titulo", "")
    hl      = slide.get("titulo_highlight", "")
    corpo   = slide.get("corpo") or slide.get("texto", "")
    lista   = slide.get("lista") or []
    cat     = (slide.get("categoria_label") or tema).upper()[:24]
    dado    = slide.get("dado_destaque", "") or ""
    cta_txt = slide.get("cta", "") or corpo

    is_capa = (num == 1)
    is_cta  = (num == total)

    a_rgb  = _hex_rgb(accent)
    a2_rgb = _hex_rgb(accent2)
    ts     = _font_size(titulo, 52, 66, 82)
    th     = _apply_highlight(titulo, hl, "rgba(255,255,255,0.9)")

    logo_tag = (
        f'<img src="{logo_url}" style="max-height:38px;max-width:120px;'
        f'object-fit:contain;filter:brightness(0) invert(1);opacity:0.8">'
        if logo_url else ""
    )

    def _lista_items() -> str:
        if not lista:
            return ""
        lis = "".join(
            f'<li><span class="dot">✦</span>{item}</li>'
            for item in lista
        )
        return f'<ul class="lista">{lis}</ul>'

    if is_capa:
        body = f"""
<div class="capa-wrap">
  <div class="top-row">
    <div class="tag">{cat}</div>
    <div class="pg">{num:02d} / {total:02d}</div>
  </div>
  <div class="capa-center">
    <h1 class="titulo capa-ts" style="font-size:{min(ts+12,96)}px">{th}</h1>
    <div class="dots-row">● ● ●</div>
  </div>
  <div class="capa-foot">
    <div class="serie">SÉRIE EM {total:02d} SLIDES</div>
  </div>
</div>"""

    elif is_cta:
        body = f"""
<div class="cta-wrap">
  <div class="pg" style="align-self:flex-end;margin-bottom:40px">{num:02d} / {total:02d}</div>
  <h2 class="titulo" style="font-size:{ts}px;text-align:center">{th}</h2>
  <p class="corpo cta-corpo">{cta_txt}</p>
  <div class="cta-pill">SALVA ✦ COMPARTILHA ✦ SEGUE</div>
</div>"""

    else:
        dado_block = (
            f'<div class="dado">{dado}</div>'
            if dado else ""
        )
        body = f"""
<div class="content-wrap">
  <div class="top-row">
    <div class="tag">{cat}</div>
    <div class="pg">{num:02d} / {total:02d}</div>
  </div>
  <div class="glass-card">
    <div class="ghost-em">{num:02d}</div>
    <h2 class="titulo" style="font-size:{ts}px">{th}</h2>
    <div class="divider"></div>
    {dado_block}
    <p class="corpo">{corpo}</p>
    {_lista_items()}
  </div>
</div>"""

    css = f"""
{_POPPINS}
*{{margin:0;padding:0;box-sizing:border-box;list-style:none}}
body{{width:1080px;height:1080px;overflow:hidden;font-family:'Poppins',sans-serif;
     color:#fff;position:relative;
     background:linear-gradient(145deg,{accent} 0%,{accent2} 100%)}}
.mesh{{position:absolute;inset:0;
  background:radial-gradient(ellipse 70% 50% at 10% 20%,rgba(255,255,255,0.12) 0%,transparent 60%),
             radial-gradient(ellipse 50% 70% at 90% 80%,rgba(0,0,0,0.2) 0%,transparent 60%);
  pointer-events:none}}
.logo-area{{position:absolute;top:44px;left:52px;z-index:20}}
.marca{{position:absolute;bottom:40px;right:52px;font-size:11px;
        letter-spacing:5px;color:rgba(255,255,255,0.35);font-weight:600;
        text-transform:uppercase;z-index:20}}
.pg{{font-size:12px;letter-spacing:4px;color:rgba(255,255,255,0.45);font-weight:600}}
.tag{{font-size:11px;letter-spacing:6px;font-weight:700;text-transform:uppercase;
      color:rgba(255,255,255,0.7)}}
.top-row{{display:flex;justify-content:space-between;align-items:center}}
.titulo{{font-weight:900;line-height:0.95;color:#fff;max-width:900px;margin-bottom:20px;
         text-shadow:0 4px 40px rgba(0,0,0,0.25)}}
.corpo{{font-size:21px;line-height:1.6;color:rgba(255,255,255,0.82);
        max-width:840px;font-weight:400}}
.dado{{font-size:80px;font-weight:900;line-height:1;letter-spacing:-2px;
       color:rgba(255,255,255,0.95);margin-bottom:8px}}
/* Capa */
.capa-wrap{{position:absolute;inset:0;padding:56px 64px;
            display:flex;flex-direction:column;justify-content:space-between;z-index:5}}
.capa-center{{display:flex;flex-direction:column;align-items:flex-start}}
.capa-ts{{margin-bottom:24px}}
.dots-row{{font-size:20px;letter-spacing:16px;opacity:0.4}}
.serie{{font-size:10px;letter-spacing:6px;font-weight:600;
        text-transform:uppercase;opacity:0.4}}
.capa-foot{{display:flex;justify-content:flex-end}}
/* Content */
.content-wrap{{position:absolute;inset:0;padding:56px 64px;
               display:flex;flex-direction:column;gap:24px;z-index:5}}
.glass-card{{background:rgba(0,0,0,0.2);backdrop-filter:blur(24px);
             -webkit-backdrop-filter:blur(24px);
             border:1px solid rgba(255,255,255,0.14);border-radius:24px;
             padding:48px 52px;flex:1;display:flex;flex-direction:column;
             justify-content:center;position:relative;overflow:hidden}}
.glass-card::before{{content:'';position:absolute;inset:0;
                      background:linear-gradient(135deg,rgba(255,255,255,0.07) 0%,transparent 50%);
                      pointer-events:none}}
.ghost-em{{position:absolute;top:-20px;right:16px;font-size:200px;font-weight:900;
           opacity:0.06;pointer-events:none;font-variant-numeric:tabular-nums}}
.divider{{width:44px;height:3px;background:rgba(255,255,255,0.4);
          border-radius:2px;margin-bottom:22px}}
.lista{{display:flex;flex-direction:column;gap:14px;margin-top:16px;max-width:840px}}
.lista li{{display:flex;gap:14px;align-items:flex-start;
           font-size:20px;line-height:1.55;color:rgba(255,255,255,0.85);font-weight:400}}
.dot{{flex-shrink:0;font-size:9px;margin-top:7px;opacity:0.55}}
/* CTA */
.cta-wrap{{position:absolute;inset:0;padding:56px 64px;
           display:flex;flex-direction:column;align-items:center;
           justify-content:center;text-align:center;z-index:5}}
.cta-corpo{{margin-bottom:36px;text-align:center}}
.cta-pill{{background:rgba(255,255,255,0.16);backdrop-filter:blur(12px);
           -webkit-backdrop-filter:blur(12px);
           border:2px solid rgba(255,255,255,0.3);color:#fff;
           font-size:15px;font-weight:700;letter-spacing:5px;
           padding:20px 56px;border-radius:100px}}
"""

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>{css}</style></head><body>
<div class="mesh"></div>
<div class="logo-area">{logo_tag}</div>
{body}
<div class="marca">{'@' + username if username else ''}</div>
</body></html>"""


# ══════════════════════════════════════════════════════════════════
# TEMPLATE 4 — Foto Bold (atualizado)
# Foto full-bleed, overlay gradiente sutil, Inter Black, badge no canto
# ══════════════════════════════════════════════════════════════════
def _html_foto_bold(
    slide: dict,
    total: int,
    tema: str,
    accent: str,
    accent2: str,
    img_local: str,
    logo_url: str | None,
    username: str,
) -> str:
    num     = slide.get("numero", 1)
    titulo  = slide.get("titulo", "")
    hl      = slide.get("titulo_highlight", "")
    corpo   = slide.get("corpo") or slide.get("texto", "")
    lista   = slide.get("lista") or []
    cat     = (slide.get("categoria_label") or tema).upper()[:24]
    dado    = slide.get("dado_destaque", "") or ""
    cta_txt = slide.get("cta", "") or corpo

    is_capa = (num == 1)
    is_cta  = (num == total)

    ts = _font_size(titulo, 52, 64, 76)
    th = _apply_highlight(titulo, hl, accent)

    img_url  = f"file:///{img_local.replace(chr(92), '/')}" if img_local else ""
    logo_tag = (
        f'<img src="{logo_url}" style="max-width:140px;max-height:56px;object-fit:contain">'
        if logo_url else ""
    )

    def _lista_items() -> str:
        if not lista:
            return ""
        lis = "".join(
            f'<li><span class="dot" style="background:{accent}"></span>{item}</li>'
            for item in lista
        )
        return f'<ul class="lista">{lis}</ul>'

    if is_capa:
        body = f"""
<div class="inner capa">
  <div class="badge" style="background:{accent};color:#080808">{num:02d} / {total:02d}</div>
  <div class="capa-content">
    <div class="cat-label" style="color:{accent}">{cat}</div>
    <h1 class="titulo capa-t" style="font-size:{min(ts+16,92)}px">{th}</h1>
    <div class="bar" style="background:linear-gradient(90deg,{accent},{accent2})"></div>
  </div>
</div>"""

    elif is_cta:
        body = f"""
<div class="inner cta">
  <div class="badge" style="background:{accent};color:#080808">{num:02d} / {total:02d}</div>
  <h2 class="titulo" style="font-size:{ts}px">{th}</h2>
  <p class="corpo">{cta_txt}</p>
  <div class="cta-pill" style="background:{accent};color:#080808">
    SALVA ✦ COMPARTILHA ✦ SEGUE
  </div>
</div>"""

    else:
        dado_block = (
            f'<div class="dado" style="color:{accent}">{dado}</div>'
            if dado else ""
        )
        body = f"""
<div class="inner conteudo">
  <div class="badge" style="background:{accent};color:#080808">{num:02d} / {total:02d}</div>
  <div class="cat-label" style="color:{accent}">{cat}</div>
  <h2 class="titulo" style="font-size:{ts}px">{th}</h2>
  <div class="bar" style="background:linear-gradient(90deg,{accent},{accent2})"></div>
  {dado_block}
  <p class="corpo">{corpo}</p>
  {_lista_items()}
</div>"""

    css = f"""
{_INTER}
*{{margin:0;padding:0;box-sizing:border-box;list-style:none}}
body{{width:1080px;height:1080px;overflow:hidden;font-family:'Inter',sans-serif;
     background:#0a0a0a;position:relative}}
.bg-img{{position:absolute;inset:0;
         background:url('{img_url}') center/cover no-repeat;
         filter:saturate(1.1) brightness(0.9)}}
.overlay{{position:absolute;inset:0;
          background:linear-gradient(180deg,rgba(0,0,0,0.18) 0%,rgba(0,0,0,0.78) 100%)}}
.logo-area{{position:absolute;top:40px;left:52px;z-index:20}}
.marca{{position:absolute;bottom:40px;right:52px;font-size:12px;
        letter-spacing:3px;color:rgba(255,255,255,0.3);font-weight:600;z-index:20}}
.inner{{position:absolute;inset:0;padding:60px 72px;
        display:flex;flex-direction:column;justify-content:flex-end;color:#fff;z-index:5}}
.badge{{position:absolute;top:44px;right:52px;font-size:13px;font-weight:700;
        letter-spacing:2px;padding:8px 18px;border-radius:100px;z-index:20}}
.capa-content{{display:flex;flex-direction:column;gap:0}}
.cat-label{{font-size:13px;font-weight:600;letter-spacing:4px;
            text-transform:uppercase;margin-bottom:16px}}
.titulo{{font-weight:900;line-height:1.0;color:#fff;max-width:860px;margin-bottom:20px;
         text-shadow:0 2px 30px rgba(0,0,0,0.5)}}
.capa-t{{text-shadow:0 2px 40px rgba(0,0,0,0.6)}}
.bar{{width:72px;height:4px;border-radius:2px;margin-bottom:20px}}
.corpo{{font-size:24px;line-height:1.6;color:rgba(255,255,255,0.88);
        max-width:820px;font-weight:400;text-shadow:0 2px 12px rgba(0,0,0,0.7)}}
.dado{{font-size:68px;font-weight:900;line-height:1;letter-spacing:-2px;margin-bottom:8px}}
.lista{{display:flex;flex-direction:column;gap:14px;margin-top:16px;max-width:820px}}
.lista li{{display:flex;gap:14px;align-items:flex-start;
           font-size:21px;color:rgba(255,255,255,0.9);line-height:1.55;font-weight:400;
           text-shadow:0 1px 8px rgba(0,0,0,0.6)}}
.dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0;margin-top:9px}}
.cta{{align-items:center;text-align:center;padding:80px}}
.cta-pill{{background:transparent;font-size:15px;font-weight:800;letter-spacing:5px;
           padding:20px 52px;border-radius:100px;margin-top:28px;
           border:2px solid rgba(255,255,255,0.5);color:#fff}}
"""

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>{css}</style></head><body>
<div class="bg-img"></div>
<div class="overlay"></div>
<div class="logo-area">{logo_tag}</div>
{body}
<div class="marca">{'@' + username if username else ''}</div>
</body></html>"""


# ══════════════════════════════════════════════════════════════════
# TEMPLATE 5 — Minimal Type
# Só tipografia. Fundo neutro. Para frases de impacto, dados, perguntas.
# ══════════════════════════════════════════════════════════════════
def _html_minimal_type(
    slide: dict,
    total: int,
    tema: str,
    accent: str,
    logo_url: str | None,
    username: str,
) -> str:
    num     = slide.get("numero", 1)
    tipo    = slide.get("tipo", "conteudo")
    titulo  = slide.get("titulo", "")
    hl      = slide.get("titulo_highlight", "")
    corpo   = slide.get("corpo") or slide.get("texto", "")
    lista   = slide.get("lista") or []
    dado    = slide.get("dado_destaque", "") or ""
    cat     = (slide.get("categoria_label") or tema).upper()[:24]
    cta_txt = slide.get("cta", "") or corpo

    is_capa = (num == 1)
    is_cta  = (num == total)

    a_rgb = _hex_rgb(accent)
    ts    = _font_size(titulo, 56, 72, 92)
    th    = _apply_highlight(titulo, hl, accent)

    logo_tag = (
        f'<img src="{logo_url}" style="max-height:36px;max-width:110px;object-fit:contain">'
        if logo_url else ""
    )

    # Decide slide variant
    is_dado    = bool(dado)
    is_pergunta= titulo.strip().endswith("?") or tipo in ("gancho",)
    is_frase   = not is_dado and not is_pergunta

    # Background: alternates between light and dark for visual rhythm
    bg_color  = "#F0EEE8" if (num % 2 == 1) else "#1A1A1A"
    txt_color = "#111111" if (num % 2 == 1) else "#F0F0F0"
    muted     = "#888888" if (num % 2 == 1) else "#666666"

    if is_capa and is_dado:
        body = f"""
<div class="cat-label" style="color:{accent}">{cat}</div>
<div class="dado-giant" style="color:{accent};text-shadow:0 0 80px rgba({a_rgb},0.2)">{dado}</div>
<h1 class="titulo-dado" style="color:{txt_color};font-size:{ts}px">{th}</h1>
<div class="sep" style="background:{accent}"></div>
<p class="corpo" style="color:{muted}">{corpo}</p>"""

    elif is_dado and not is_capa and not is_cta:
        body = f"""
<div class="slide-num" style="color:{accent}">{num:02d}</div>
<div class="dado-giant" style="color:{accent};text-shadow:0 0 80px rgba({a_rgb},0.15)">{dado}</div>
<h2 class="titulo-dado" style="color:{txt_color};font-size:{ts}px">{th}</h2>
<div class="sep" style="background:{accent}"></div>
<p class="corpo" style="color:{muted}">{corpo}</p>"""

    elif is_pergunta and not is_capa and not is_cta:
        body = f"""
<div class="layout-pergunta">
  <div class="q-mark" style="color:{accent}">&quest;</div>
  <div class="q-right">
    <div class="cat-label" style="color:{accent}">{cat} · {num:02d}</div>
    <h2 class="titulo-pergunta" style="color:{txt_color}">{th}</h2>
    <div class="sep" style="background:{accent}"></div>
    <p class="corpo" style="color:{muted}">{corpo}</p>
  </div>
</div>"""

    elif is_capa:
        # Slide 1 hero — huge title
        hero_ts = min(ts + 20, 110)
        body = f"""
<div class="cat-label" style="color:{accent}">{cat}</div>
<h1 class="titulo-frase" style="color:{txt_color};font-size:{hero_ts}px">{th}</h1>
<div class="sep" style="background:{accent}"></div>
<div class="slide-num-foot" style="color:{muted}">01 / {total:02d}</div>"""

    elif is_cta:
        body = f"""
<div class="cta-wrap">
  <div class="slide-num" style="color:{accent}">{num:02d}</div>
  <h2 class="titulo-frase" style="color:{txt_color};font-size:{ts}px;text-align:center">{th}</h2>
  <div class="sep" style="background:{accent};margin:28px auto"></div>
  <p class="corpo" style="color:{muted};text-align:center">{cta_txt}</p>
  <div class="cta-pill" style="border-color:{accent};color:{accent}">
    SALVA · COMPARTILHA · SEGUE
  </div>
</div>"""

    else:
        # Default frase layout
        def _lista_items() -> str:
            if not lista:
                return ""
            lis = "".join(
                f'<li><span style="color:{accent};margin-right:12px">—</span>{item}</li>'
                for item in lista
            )
            return f'<ul class="lista" style="color:{txt_color}">{lis}</ul>'

        body = f"""
<div class="slide-num" style="color:{accent}">{num:02d}</div>
<h2 class="titulo-frase" style="color:{txt_color};font-size:{ts}px">{th}</h2>
<div class="sep" style="background:{accent}"></div>
<p class="corpo" style="color:{muted}">{corpo}</p>
{_lista_items()}"""

    css = f"""
{_SYNE}
*{{margin:0;padding:0;box-sizing:border-box;list-style:none}}
body{{width:1080px;height:1080px;overflow:hidden;background:{bg_color};
     font-family:'Inter',sans-serif;position:relative}}
.logo-area{{position:absolute;top:44px;left:60px;z-index:20}}
.rodape{{position:absolute;bottom:48px;left:60px;right:60px;
         display:flex;justify-content:space-between;align-items:center;z-index:20}}
.username{{font-size:12px;color:{muted};font-weight:500;letter-spacing:0.5px}}
.pg{{font-size:12px;color:{muted};font-weight:600;font-variant-numeric:tabular-nums}}
.main{{position:absolute;top:100px;left:80px;right:80px;bottom:90px;
       display:flex;flex-direction:column;justify-content:center;z-index:5}}
.cat-label{{font-size:11px;font-weight:600;letter-spacing:0.2em;
            text-transform:uppercase;margin-bottom:32px}}
.slide-num{{font-size:80px;font-weight:800;font-family:'Syne',sans-serif;
            line-height:1;opacity:0.15;margin-bottom:16px;
            font-variant-numeric:tabular-nums}}
.slide-num-foot{{font-size:14px;font-weight:600;letter-spacing:3px;
                 font-variant-numeric:tabular-nums;margin-top:24px}}
.titulo-frase{{font-family:'Syne',sans-serif;font-weight:800;
               line-height:1.08;max-width:920px;margin-bottom:28px;word-break:break-word}}
.titulo-dado{{font-family:'Inter',sans-serif;font-weight:700;
              line-height:1.1;max-width:840px;margin-bottom:20px}}
.titulo-pergunta{{font-family:'Syne',sans-serif;font-weight:800;
                  font-size:52px;line-height:1.1;max-width:740px;margin-bottom:20px}}
.dado-giant{{font-family:'Syne',sans-serif;font-weight:800;
             font-size:160px;line-height:0.85;letter-spacing:-4px;margin-bottom:16px}}
.sep{{width:52px;height:3px;border-radius:1px;margin-bottom:24px}}
.corpo{{font-size:20px;font-weight:400;line-height:1.65;max-width:840px}}
/* Pergunta layout */
.layout-pergunta{{display:flex;gap:32px;align-items:flex-start}}
.q-mark{{font-size:200px;font-weight:800;font-family:'Syne',sans-serif;
         line-height:0.8;flex-shrink:0;opacity:0.9}}
.q-right{{display:flex;flex-direction:column;flex:1;padding-top:24px}}
/* Lista */
.lista{{display:flex;flex-direction:column;gap:16px;margin-top:20px;max-width:840px}}
.lista li{{font-size:20px;line-height:1.6;font-weight:400;display:flex;align-items:flex-start}}
/* CTA */
.cta-wrap{{display:flex;flex-direction:column;align-items:center;text-align:center}}
.cta-pill{{font-size:13px;font-weight:700;letter-spacing:0.2em;
           padding:18px 44px;border-radius:100px;margin-top:28px;
           border:2px solid;background:transparent}}
"""

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>{css}</style></head><body>
<div class="logo-area">{logo_tag}</div>
<div class="main">{body}</div>
<div class="rodape">
  <span class="username">{'@' + username if username else ''}</span>
  <span class="pg">{num:02d} / {total:02d}</span>
</div>
</body></html>"""


# ══════════════════════════════════════════════════════════════════
# TEMPLATE 6 — X Thread
# Imita post real do X/Twitter: avatar + nome + @handle + ícone X
# Versão clara (fundo branco, borda accent) e escura (#1a1a1a)
# ══════════════════════════════════════════════════════════════════
def _html_x_thread(
    slide: dict,
    total: int,
    tema: str,
    accent: str,
    avatar_local: str,
    nome_display: str,
    username: str,
    dark: bool = False,
) -> str:
    num     = slide.get("numero", 1)
    titulo  = slide.get("titulo", "")
    corpo   = slide.get("corpo") or slide.get("texto", "")
    lista   = slide.get("lista") or []
    dado    = slide.get("dado_destaque", "") or ""
    cta_txt = slide.get("cta", "") or corpo

    is_capa = (num == 1)
    is_cta  = (num == total)

    # Cores dark vs light
    if dark:
        bg          = "#15202B"
        card_bg     = "#1e2732"
        txt_primary = "#E7E9EA"
        txt_muted   = "#8B98A5"
        border_clr  = "rgba(255,255,255,0.08)"
        x_icon_clr  = "#E7E9EA"
        pill_clr    = "#E7E9EA"
        pill_txt    = "#15202B"
    else:
        bg          = "#F7F9FA"
        card_bg     = "#FFFFFF"
        txt_primary = "#0F1419"
        txt_muted   = "#536471"
        border_clr  = accent
        x_icon_clr  = "#0F1419"
        pill_clr    = "#0F1419"
        pill_txt    = "#FFFFFF"

    handle = ("@" + username.lstrip("@")) if username else "@voce"
    nome   = nome_display or handle.lstrip("@").replace("_", " ").title()

    # Avatar: imagem local ou iniciais
    if avatar_local:
        av_url  = f"file:///{avatar_local.replace(chr(92), '/')}"
        avatar_html = f'<img src="{av_url}" class="avatar">'
    else:
        inicial = (nome[0] if nome else "U").upper()
        avatar_html = f'<div class="avatar avatar-init" style="background:{accent}">{inicial}</div>'

    # Timestamp fixo visual
    from datetime import datetime
    ts_str = datetime.now().strftime("%-I:%M %p · %b %-d, %Y") if hasattr(datetime.now(), 'strftime') else "12:00 PM · Jan 1, 2025"
    try:
        ts_str = datetime.now().strftime("%I:%M %p · %b %d, %Y").lstrip("0")
    except Exception:
        ts_str = "12:00 PM · Jan 1, 2025"

    # Contador no canto superior direito
    counter = f'<div class="counter" style="color:{txt_muted}">{num}/{total}</div>'

    # ícone X (SVG compacto)
    x_svg = f'''<svg width="22" height="22" viewBox="0 0 24 24" fill="{x_icon_clr}" xmlns="http://www.w3.org/2000/svg">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.746l7.73-8.835L1.254 2.25H8.08l4.26 5.632 5.905-5.632zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
    </svg>'''

    # Conteúdo do tweet
    def build_tweet_body() -> str:
        parts = []
        if is_capa:
            parts.append(f'<p class="tweet-text">{titulo}</p>')
            if corpo:
                parts.append(f'<p class="tweet-text tweet-sub">{corpo}</p>')
        elif is_cta:
            parts.append(f'<p class="tweet-text">{cta_txt}</p>')
        else:
            if dado:
                parts.append(f'<div class="tweet-dado" style="color:{accent}">{dado}</div>')
            if titulo:
                parts.append(f'<p class="tweet-text tweet-bold">{titulo}</p>')
            if corpo:
                parts.append(f'<p class="tweet-text">{corpo}</p>')
            if lista:
                items_html = "".join(
                    f'<div class="tweet-list-item"><span style="color:{accent}">·</span> {item}</div>'
                    for item in lista
                )
                parts.append(f'<div class="tweet-list">{items_html}</div>')
        return "\n".join(parts)

    tweet_body = build_tweet_body()

    # Borda do card: accent na versão clara, sutil no dark
    card_border = f"3px solid {accent}" if not dark else f"1px solid {border_clr}"

    css = f"""
{_INTER}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  width:1080px;height:1080px;overflow:hidden;
  font-family:'Inter',sans-serif;
  background:{bg};
  display:flex;align-items:center;justify-content:center;
  position:relative;
}}
.watermark{{
  position:absolute;bottom:32px;right:40px;
  font-size:13px;font-weight:600;letter-spacing:0.04em;
  color:{txt_muted};opacity:0.5;
}}
.card{{
  width:880px;
  background:{card_bg};
  border-radius:20px;
  border:{card_border};
  padding:52px 56px 44px;
  display:flex;flex-direction:column;gap:0;
  box-shadow:{'0 8px 48px rgba(0,0,0,0.28)' if dark else '0 4px 32px rgba(0,0,0,0.08)'};
  position:relative;
}}
.card-header{{
  display:flex;align-items:center;justify-content:space-between;
  margin-bottom:28px;
}}
.header-left{{display:flex;align-items:center;gap:18px}}
.avatar{{
  width:72px;height:72px;border-radius:50%;
  object-fit:cover;flex-shrink:0;
}}
.avatar-init{{
  display:flex;align-items:center;justify-content:center;
  font-size:28px;font-weight:800;color:#fff;
}}
.user-info{{display:flex;flex-direction:column;gap:2px}}
.display-name{{
  font-size:22px;font-weight:700;color:{txt_primary};
  letter-spacing:-0.01em;
}}
.handle{{font-size:19px;color:{txt_muted};font-weight:400}}
.tweet-text{{
  font-size:28px;line-height:1.55;color:{txt_primary};
  font-weight:400;margin-bottom:18px;
}}
.tweet-bold{{font-weight:700;font-size:30px;}}
.tweet-sub{{color:{txt_muted};font-size:24px;}}
.tweet-dado{{
  font-size:80px;font-weight:800;line-height:1;
  letter-spacing:-2px;margin-bottom:12px;
}}
.tweet-list{{
  display:flex;flex-direction:column;gap:10px;
  margin-top:8px;
}}
.tweet-list-item{{
  font-size:26px;line-height:1.5;color:{txt_primary};
  display:flex;gap:12px;
}}
.divider{{
  height:1px;background:{'rgba(255,255,255,0.08)' if dark else 'rgba(0,0,0,0.08)'};
  margin:28px 0;
}}
.timestamp{{font-size:18px;color:{txt_muted};font-weight:400}}
.counter{{
  position:absolute;top:52px;right:56px;
  font-size:16px;font-weight:700;letter-spacing:0.05em;
}}
.cta-pill{{
  display:inline-block;margin-top:24px;
  background:{pill_clr};color:{pill_txt};
  font-size:16px;font-weight:700;letter-spacing:0.12em;
  padding:16px 40px;border-radius:100px;
}}
"""

    cta_pill = '<div class="cta-pill">SALVA · COMPARTILHA · SEGUE</div>' if is_cta else ""

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>{css}</style></head><body>
<div class="card">
  {counter}
  <div class="card-header">
    <div class="header-left">
      {avatar_html}
      <div class="user-info">
        <span class="display-name">{nome}</span>
        <span class="handle">{handle}</span>
      </div>
    </div>
    {x_svg}
  </div>
  <div class="tweet-content">
    {tweet_body}
    {cta_pill}
  </div>
  <div class="divider"></div>
  <div class="timestamp">{ts_str}</div>
</div>
<div class="watermark">{'@' + username if username else ''}</div>
</body></html>"""


# ══════════════════════════════════════════════════════════════════
# TEMPLATE 7 — LinkedIn Blur
# Blob gradiente roxo/lilás desfocado, fundo lavanda claro ou dark
# Avatar + "Written by" no rodapé, número ghost, botão › círculo
# ══════════════════════════════════════════════════════════════════
def _html_linkedin_blur(
    slide: dict,
    total: int,
    tema: str,
    accent: str,
    logo_url: str | None,
    username: str,
    dark: bool = False,
) -> str:
    num     = slide.get("numero", 1)
    titulo  = slide.get("titulo", "")
    hl      = slide.get("titulo_highlight", "")
    corpo   = slide.get("corpo") or slide.get("texto", "")
    lista   = slide.get("lista") or []
    dado    = slide.get("dado_destaque", "") or ""
    cta_txt = slide.get("cta", "") or corpo

    is_capa = (num == 1)
    is_cta  = (num == total)
    th      = _apply_highlight(titulo, hl, accent)

    if dark:
        bg       = "#1C1C1E"
        card_bg  = "#1C1C1E"
        txt      = "#FFFFFF"
        muted    = "#A0A0A8"
        btn_bg   = "#FFFFFF"
        btn_txt  = "#1C1C1E"
        btn_brd  = "#FFFFFF"
        ghost_c  = "rgba(255,255,255,0.07)"
        blob1    = "rgba(100,60,180,0.55)"
        blob2    = "rgba(180,100,255,0.35)"
    else:
        bg       = "#F0EEF8"
        card_bg  = "#F0EEF8"
        txt      = "#1A1A1A"
        muted    = "#666670"
        btn_bg   = "#1A1A1A"
        btn_txt  = "#FFFFFF"
        btn_brd  = "#1A1A1A"
        ghost_c  = "rgba(0,0,0,0.06)"
        blob1    = "rgba(120,80,200,0.45)"
        blob2    = "rgba(190,120,255,0.30)"

    nome = username.lstrip("@").replace("_"," ").replace("."," ").title() if username else "User Name"
    handle = ("@" + username.lstrip("@")) if username else ""

    # Avatar: logo ou iniciais
    if logo_url:
        avatar_html = f'<img src="{logo_url}" class="av-img">'
    else:
        ini = (nome[0] if nome else "U").upper()
        avatar_html = f'<div class="av-ini" style="background:{accent}">{ini}</div>'

    # Botão seta
    btn = f'<div class="nav-btn" style="border-color:{btn_brd};color:{btn_bg}"><span style="color:{btn_txt if dark else btn_bg}">›</span></div>' if not is_cta else f'<div class="nav-btn" style="border-color:{btn_brd}"><span style="color:{btn_txt if dark else btn_bg}">✓</span></div>'

    # Rodapé
    footer = f"""<div class="footer">
      <div class="written">
        {avatar_html}
        <div class="written-txt">
          <span class="wr-label" style="color:{muted}">Written by</span>
          <span class="wr-name" style="color:{txt}">{nome}</span>
        </div>
      </div>
      {btn}
    </div>"""

    def lista_items():
        if not lista: return ""
        lis = "".join(f'<li style="color:{txt}"><span style="color:{accent}">—</span> {i}</li>' for i in lista)
        return f'<ul class="lista">{lis}</ul>'

    if is_capa:
        body = f"""
<div class="ghost-n" style="color:{ghost_c}">{num}</div>
<div class="capa-content">
  <h1 class="titulo" style="color:{txt};font-size:{_font_size(titulo,56,72,92)}px">{th}</h1>
</div>"""
    elif is_cta:
        body = f"""
<div class="cta-content">
  <div class="av-cta">{avatar_html}</div>
  <h2 class="cta-nome" style="color:{txt}">{nome}</h2>
  <p class="cta-txt" style="color:{muted}">{cta_txt}</p>
</div>"""
    else:
        dado_block = f'<div class="dado" style="color:{accent}">{dado}</div>' if dado else ""
        body = f"""
<div class="ghost-n" style="color:{ghost_c}">{num}</div>
<div class="content">
  {dado_block}
  <p class="corpo" style="color:{txt}">{corpo}</p>
  {lista_items()}
</div>"""

    _NUNITO = "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');"
    css = f"""
{_NUNITO}
*{{margin:0;padding:0;box-sizing:border-box;list-style:none}}
body{{width:1080px;height:1080px;overflow:hidden;font-family:'Inter',sans-serif;
     background:{bg};position:relative}}
.blob1{{position:absolute;top:-120px;right:-80px;width:520px;height:520px;
        border-radius:50%;background:radial-gradient(circle,{blob1} 0%,transparent 70%);
        filter:blur(72px);pointer-events:none}}
.blob2{{position:absolute;top:60px;right:80px;width:320px;height:320px;
        border-radius:50%;background:radial-gradient(circle,{blob2} 0%,transparent 70%);
        filter:blur(56px);pointer-events:none}}
.ghost-n{{position:absolute;top:60px;left:64px;font-size:340px;font-weight:900;
          line-height:1;pointer-events:none;font-variant-numeric:tabular-nums;
          color:{ghost_c};z-index:1}}
.inner{{position:absolute;inset:0;padding:80px 72px 0;display:flex;
        flex-direction:column;z-index:5}}
.capa-content{{flex:1;display:flex;align-items:center}}
.titulo{{font-weight:800;line-height:1.1;max-width:760px}}
.content{{flex:1;display:flex;flex-direction:column;justify-content:center;padding-top:40px}}
.corpo{{font-size:26px;line-height:1.65;font-weight:400;max-width:820px}}
.dado{{font-size:88px;font-weight:800;line-height:1;letter-spacing:-2px;margin-bottom:12px}}
.lista{{display:flex;flex-direction:column;gap:18px;margin-top:20px}}
.lista li{{font-size:24px;line-height:1.55;display:flex;gap:12px;align-items:flex-start}}
.cta-content{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:20px}}
.av-cta{{width:120px;height:120px;border-radius:50%;overflow:hidden}}
.av-cta img,.av-cta div{{width:100%;height:100%}}
.cta-nome{{font-size:52px;font-weight:800;text-align:center}}
.cta-txt{{font-size:22px;text-align:center;max-width:640px;line-height:1.6}}
.footer{{display:flex;align-items:center;justify-content:space-between;
         padding:0 72px 56px;z-index:5}}
.written{{display:flex;align-items:center;gap:14px}}
.av-img{{width:44px;height:44px;border-radius:50%;object-fit:cover}}
.av-ini{{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;
         justify-content:center;font-size:18px;font-weight:800;color:#fff}}
.written-txt{{display:flex;flex-direction:column}}
.wr-label{{font-size:12px;font-weight:400}}
.wr-name{{font-size:15px;font-weight:700}}
.nav-btn{{width:52px;height:52px;border-radius:50%;border:2px solid;
          display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:700}}
"""
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>{css}</style></head><body>
<div class="blob1"></div><div class="blob2"></div>
<div class="inner">{body}</div>
<div class="footer">
  <div class="written">
    {avatar_html}
    <div class="written-txt">
      <span class="wr-label" style="color:{muted}">Written by</span>
      <span class="wr-name" style="color:{txt}">{nome}</span>
    </div>
  </div>
  {btn}
</div>
</body></html>"""


# ══════════════════════════════════════════════════════════════════
# TEMPLATE 8 — Studio Shodwe
# Monocromático, serif + sans, espaço extremo, split com foto
# Fundo #F2F0EB, texto quase preto, zero cores de destaque
# ══════════════════════════════════════════════════════════════════
_PLAYFAIR = "@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400;1,700;1,900&family=Inter:wght@300;400;600;700&display=swap');"

def _html_studio_shodwe(
    slide: dict,
    total: int,
    tema: str,
    accent: str,
    img_local: str,
    logo_url: str | None,
    username: str,
) -> str:
    num     = slide.get("numero", 1)
    titulo  = slide.get("titulo", "")
    corpo   = slide.get("corpo") or slide.get("texto", "")
    lista   = slide.get("lista") or []
    dado    = slide.get("dado_destaque", "") or ""
    cta_txt = slide.get("cta", "") or corpo

    is_capa = (num == 1)
    is_cta  = (num == total)

    bg   = "#F2F0EB"
    txt  = "#0D0D0D"
    mute = "#666"

    nome  = username.lstrip("@").replace("_"," ").replace("."," ").title() if username else "Studio"
    marca = nome

    img_url = f"file:///{img_local.replace(chr(92), '/')}" if img_local else ""

    # Botão círculo outline
    arrow = "←" if is_cta else "→"
    btn_circle = f'<div class="btn-circle">{arrow}</div>'

    ts = _font_size(titulo, 72, 92, 120)

    if is_capa:
        # Título mix de pesos — primeira linha regular, palavra-chave bold italic, resto regular
        parts = titulo.split()
        mid   = max(1, len(parts)//2)
        line1 = " ".join(parts[:mid])
        line2 = " ".join(parts[mid:])
        body = f"""
<div class="capa-wrap">
  <div class="capa-center">
    <h1 class="capa-t1">{line1}</h1>
    <h1 class="capa-t2">{line2}</h1>
    <h1 class="capa-t3">{dado or tema.upper()}</h1>
  </div>
  <div class="capa-foot">
    <p class="capa-sub" style="color:{mute}">{corpo}</p>
    <div class="capa-handle" style="color:{txt}">@{username.lstrip('@') if username else 'voce'}</div>
  </div>
</div>"""

    elif is_cta:
        body = f"""
<div class="cta-wrap">
  <h2 class="cta-titulo">{titulo}</h2>
  <div class="cta-foot">
    <p style="color:{mute};font-size:22px">{cta_txt}</p>
    <div class="capa-handle" style="color:{txt}">@{username.lstrip('@') if username else 'voce'}</div>
  </div>
</div>"""

    elif img_local and num % 2 == 0:
        # Split vertical: texto esquerda, foto direita
        body = f"""
<div class="split-wrap">
  <div class="split-left">
    <h2 class="split-titulo" style="font-size:{min(ts,96)}px">{titulo}</h2>
    <p class="split-corpo" style="color:{mute}">{corpo}</p>
    {''.join(f'<p class="split-corpo" style="color:{mute};margin-top:20px">{i}</p>' for i in lista) if lista else ""}
  </div>
  <div class="split-right" style="background:url('{img_url}') center/cover no-repeat"></div>
</div>"""

    elif img_local:
        # Texto top, foto bottom strip
        body = f"""
<div class="htop-wrap">
  <div class="htop-left">
    <h2 class="htop-titulo" style="font-size:{min(ts,88)}px;font-weight:800">{titulo}</h2>
    <p class="htop-corpo" style="color:{mute}">{corpo}</p>
  </div>
  <div class="htop-right">
    <p class="htop-corpo2" style="color:{txt}">{dado or (lista[0] if lista else "")}</p>
  </div>
</div>
<div class="hbot-foto" style="background:url('{img_url}') center/cover no-repeat"></div>"""

    else:
        # Ícone + texto duplo (texto central)
        icon_map = {"⏰":"⏰","📅":"📅","💡":"💡","🔑":"🔑","⚡":"⚡"}
        icon = dado or "○"
        body = f"""
<div class="icon-wrap">
  <div class="icon-circle">{icon}</div>
  <h2 class="icon-titulo" style="font-size:{min(ts,80)}px">{titulo}</h2>
  <p class="icon-corpo" style="color:{mute}">{corpo}</p>
  {f'<p class="icon-sub" style="color:{txt}">{lista[0] if lista else ""}</p>' if lista else ""}
</div>"""

    css = f"""
{_PLAYFAIR}
*{{margin:0;padding:0;box-sizing:border-box;list-style:none}}
body{{width:1080px;height:1080px;overflow:hidden;background:{bg};
     font-family:'Inter',sans-serif;color:{txt};position:relative}}
.header{{position:absolute;top:52px;left:64px;right:64px;
         display:flex;justify-content:space-between;align-items:center;z-index:20}}
.brand{{font-size:16px;font-weight:400;color:{txt};letter-spacing:0.02em}}
.btn-circle{{width:60px;height:60px;border-radius:50%;border:1.5px solid {txt};
             display:flex;align-items:center;justify-content:center;
             font-size:22px;color:{txt}}}
.footer-line{{position:absolute;bottom:52px;left:64px;
              font-size:14px;color:{mute};font-weight:400}}
/* Capa */
.capa-wrap{{position:absolute;inset:0;padding:140px 64px 64px;
           display:flex;flex-direction:column;justify-content:space-between}}
.capa-center{{display:flex;flex-direction:column}}
.capa-t1{{font-family:'Playfair Display',serif;font-weight:400;font-size:80px;
          line-height:0.95;color:{txt}}}
.capa-t2{{font-family:'Playfair Display',serif;font-weight:900;font-style:italic;
          font-size:130px;line-height:0.88;color:{txt}}}
.capa-t3{{font-family:'Playfair Display',serif;font-weight:400;font-size:72px;
          line-height:0.95;color:{txt}}}
.capa-foot{{display:flex;flex-direction:column;gap:6px}}
.capa-sub{{font-size:20px;font-weight:300;line-height:1.5;max-width:600px}}
.capa-handle{{font-size:18px;font-weight:700}}
/* CTA */
.cta-wrap{{position:absolute;inset:0;padding:140px 64px 100px;
           display:flex;flex-direction:column;justify-content:space-between;align-items:center}}
.cta-titulo{{font-family:'Playfair Display',serif;font-style:italic;font-weight:700;
             font-size:96px;line-height:1.0;text-align:center;color:{txt}}}
.cta-foot{{display:flex;flex-direction:column;align-items:center;gap:8px}}
/* Split vertical */
.split-wrap{{position:absolute;inset:0;display:grid;grid-template-columns:1fr 1fr}}
.split-left{{padding:140px 48px 100px 64px;display:flex;flex-direction:column;justify-content:center;gap:24px}}
.split-titulo{{font-family:'Playfair Display',serif;font-weight:700;line-height:1.05;color:{txt}}}
.split-corpo{{font-size:22px;line-height:1.6;font-weight:300}}
.split-right{{height:100%}}
/* H split (texto top + foto bottom) */
.htop-wrap{{position:absolute;top:0;left:0;right:0;height:52%;
            padding:140px 64px 0;display:grid;grid-template-columns:1fr 1fr;gap:40px}}
.htop-titulo{{font-family:'Playfair Display',serif;font-weight:800;line-height:1.0;color:{txt}}}
.htop-corpo{{font-size:22px;font-weight:300;line-height:1.6;margin-top:20px}}
.htop-corpo2{{font-family:'Playfair Display',serif;font-size:28px;font-weight:400;line-height:1.4}}
.hbot-foto{{position:absolute;bottom:0;left:0;right:0;height:46%}}
/* Ícone */
.icon-wrap{{position:absolute;inset:0;padding:140px 64px 100px;
            display:flex;flex-direction:column;align-items:center;justify-content:center;gap:28px}}
.icon-circle{{font-size:64px;line-height:1}}
.icon-titulo{{font-family:'Playfair Display',serif;font-weight:700;line-height:1.05;
              text-align:center;max-width:800px;color:{txt}}}
.icon-corpo{{font-size:24px;font-weight:700;text-align:center;max-width:700px;line-height:1.5}}
.icon-sub{{font-family:'Playfair Display',serif;font-size:30px;font-weight:400;font-style:italic;
           text-align:center;max-width:700px;line-height:1.4}}
"""
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>{css}</style></head><body>
<div class="header">
  <span class="brand">{marca}</span>
  {btn_circle}
</div>
{body}
<div class="footer-line">@{username.lstrip('@') if username else 'voce'}</div>
</body></html>"""


# ══════════════════════════════════════════════════════════════════
# TEMPLATE 9 — Serif Elegante
# Fundo creme #F5F2EC, verde escuro accent, números cursivos gigantes,
# grade de linhas verticais finas no rodapé, botão › círculo
# ══════════════════════════════════════════════════════════════════
_CORMO2 = "@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;0,700;1,400;1,600;1,700&family=DM+Sans:wght@300;400;600&display=swap');"

def _html_serif_elegante(
    slide: dict,
    total: int,
    tema: str,
    accent: str,
    logo_url: str | None,
    username: str,
) -> str:
    num     = slide.get("numero", 1)
    titulo  = slide.get("titulo", "")
    corpo   = slide.get("corpo") or slide.get("texto", "")
    lista   = slide.get("lista") or []
    dado    = slide.get("dado_destaque", "") or ""
    cta_txt = slide.get("cta", "") or corpo
    cat     = (slide.get("categoria_label") or tema).upper()[:20]

    is_capa = (num == 1)
    is_cta  = (num == total)

    # Usa accent como cor primária; se for o accent padrão (#8CFF2E) troca por verde elegante
    primary = accent if accent != "#8CFF2E" else "#1B5E4B"
    bg      = "#F5F2EC"

    ts = _font_size(titulo, 80, 110, 150)

    # Grade de linhas verticais (decoração rodapé)
    grid_lines = "".join(
        f'<div style="position:absolute;bottom:0;left:{i*28+60}px;width:1px;height:60px;background:{primary};opacity:0.15"></div>'
        for i in range(36)
    )

    # Número cursivo em italic gigante
    num_cursivo = f'<div class="num-cursivo" style="color:{primary}">{num}</div>'

    # Linha horizontal topo + número
    header_line = f"""
<div class="slide-header">
  {num_cursivo}
  <div class="header-rule" style="background:{primary}"></div>
</div>"""

    # Canto L bracket
    bracket = f'<div class="bracket" style="border-color:{primary}"></div>'

    # Botão ›
    btn = f'<div class="btn-next" style="border-color:{primary};color:{primary}">›</div>'

    if is_capa:
        # Capa especial: mix de estilos no título
        words = titulo.split()
        n = len(words)
        p1 = " ".join(words[:max(1,n//3)])
        p2 = " ".join(words[max(1,n//3):max(1,2*n//3)])
        p3 = " ".join(words[max(1,2*n//3):])
        body = f"""
<div class="capa-wrap">
  <div class="capa-top">
    <span class="handle-top" style="color:{primary}">@{username.lstrip('@') if username else 'voce'}</span>
  </div>
  <div class="capa-center">
    <div class="capa-t1" style="color:{primary}">{p1}</div>
    <div class="capa-t2" style="color:{primary}">{p2 or titulo}</div>
    <div class="capa-t3" style="color:{primary}">{p3}</div>
    <div class="capa-pill" style="border-color:{primary};color:{primary}">
      <span>{cat}</span>
    </div>
  </div>
  <div class="capa-footer">
    <div class="footer-rule" style="background:{primary}"></div>
    {btn}
  </div>
</div>"""

    elif is_cta:
        body = f"""
<div class="content-wrap">
  {header_line}
  <div class="titulo-wrap">
    <h2 class="titulo-display" style="color:{primary};font-size:{ts}px">{titulo}</h2>
  </div>
  {bracket}
  <p class="corpo-txt" style="color:{primary}">{cta_txt}</p>
  <div class="cta-footer">
    <div class="footer-rule" style="background:{primary}"></div>
    {btn}
  </div>
</div>"""

    else:
        corpo_block = f'<p class="corpo-txt" style="color:{primary}">{corpo}</p>' if corpo else ""
        lista_html  = ""
        if lista:
            lista_html = "".join(f'<p class="corpo-txt" style="color:{primary};margin-top:12px">— {i}</p>' for i in lista)
        body = f"""
<div class="content-wrap">
  {header_line}
  <div class="titulo-wrap">
    <h2 class="titulo-display" style="color:{primary};font-size:{ts}px">{titulo}</h2>
  </div>
  {bracket}
  {corpo_block}
  {lista_html}
  <div class="cta-footer">
    <div class="footer-rule" style="background:{primary}"></div>
    {btn}
  </div>
</div>"""

    css = f"""
{_CORMO2}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:1080px;height:1080px;overflow:hidden;background:{bg};
     font-family:'DM Sans',sans-serif;position:relative}}
/* Número cursivo topo */
.slide-header{{display:flex;align-items:center;gap:24px;margin-bottom:40px}}
.num-cursivo{{font-family:'Cormorant Garamond',serif;font-style:italic;font-weight:400;
             font-size:120px;line-height:0.85;flex-shrink:0}}
.header-rule{{flex:1;height:1px;opacity:0.4}}
/* Layouts */
.content-wrap{{position:absolute;inset:0;padding:72px 72px 0;
               display:flex;flex-direction:column}}
.titulo-wrap{{flex:1;display:flex;align-items:center}}
.titulo-display{{font-family:'Cormorant Garamond',serif;font-weight:700;
                 line-height:0.92;max-width:920px;letter-spacing:-0.01em}}
.bracket{{width:28px;height:28px;border-top:2px solid;border-left:2px solid;margin:20px 0}}
.corpo-txt{{font-size:22px;line-height:1.65;font-weight:300;max-width:860px}}
.cta-footer{{display:flex;align-items:center;justify-content:space-between;
             padding:28px 0 56px;margin-top:auto}}
.footer-rule{{flex:1;height:1px;opacity:0.4;margin-right:28px}}
.btn-next{{width:60px;height:60px;border-radius:50%;border:1.5px solid;
           display:flex;align-items:center;justify-content:center;font-size:28px;flex-shrink:0}}
/* Grade rodapé */
.grid-lines{{position:absolute;bottom:0;left:0;right:0;height:60px;pointer-events:none}}
/* Capa */
.capa-wrap{{position:absolute;inset:0;padding:72px;display:flex;flex-direction:column}}
.capa-top{{margin-bottom:auto}}
.handle-top{{font-size:18px;font-weight:400;letter-spacing:0.02em}}
.capa-center{{display:flex;flex-direction:column;align-items:flex-start;gap:4px}}
.capa-t1{{font-family:'Cormorant Garamond',serif;font-size:72px;font-weight:400;line-height:1}}
.capa-t2{{font-family:'Cormorant Garamond',serif;font-size:160px;font-weight:700;font-style:italic;line-height:0.88;letter-spacing:-2px}}
.capa-t3{{font-family:'Cormorant Garamond',serif;font-size:72px;font-weight:400;line-height:1}}
.capa-pill{{display:inline-flex;align-items:center;border:1.5px solid;
            border-radius:100px;padding:10px 28px;margin-top:16px}}
.capa-pill span{{font-size:16px;font-weight:600;letter-spacing:0.06em}}
.capa-footer{{display:flex;align-items:center;justify-content:space-between;margin-top:auto;padding-top:28px}}
"""
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>{css}</style></head><body>
{body}
<div class="grid-lines">{grid_lines}</div>
</body></html>"""


# ══════════════════════════════════════════════════════════════════
# TEMPLATE 10 — BrandsDecoded
# Condensed bold ALL CAPS, 3 paletas rotativas por slide,
# fotos em strip/split, seta à mão, destaque sublinhado
# ══════════════════════════════════════════════════════════════════
_BARLOW = "@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;700;900&family=Inter:wght@400;500;600&display=swap');"

def _html_brands_decoded(
    slide: dict,
    total: int,
    tema: str,
    accent: str,
    img_local: str,
    logo_url: str | None,
    username: str,
) -> str:
    num     = slide.get("numero", 1)
    titulo  = slide.get("titulo", "")
    hl      = slide.get("titulo_highlight", "")
    corpo   = slide.get("corpo") or slide.get("texto", "")
    lista   = slide.get("lista") or []
    dado    = slide.get("dado_destaque", "") or ""
    cta_txt = slide.get("cta", "") or corpo

    is_capa = (num == 1)
    is_cta  = (num == total)

    # Acent como vermelho se padrão
    red = accent if accent != "#8CFF2E" else "#CC0000"

    # Paleta rotativa por slide
    palette = num % 3
    if is_capa:
        bg, txt, title_c, sub_c = "#0A0A1A", "#FFFFFF", "#FFFFFF", "#F5C842"
    elif palette == 0:
        bg, txt, title_c, sub_c = "#FFFFFF", "#0D0D0D", red, red
    elif palette == 1:
        bg, txt, title_c, sub_c = "#0D0D0D", "#FFFFFF", "#FFFFFF", red
    else:
        bg, txt, title_c, sub_c = "#FFFFFF", "#0D0D0D", "#B8952A", red

    img_url = f"file:///{img_local.replace(chr(92), '/')}" if img_local else ""

    handle  = ("@" + username.lstrip("@")) if username else "@voce"
    ts      = _font_size(titulo, 72, 96, 130)

    # Seta à mão (SVG)
    arrow_color = sub_c if bg == "#FFFFFF" else "#FFFFFF"
    hand_arrow = f'''<svg width="180" height="48" viewBox="0 0 180 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M4 28 C20 24, 60 18, 100 22 C130 25, 155 28, 170 20" stroke="{arrow_color}" stroke-width="2.5" stroke-linecap="round" fill="none"/>
      <path d="M158 14 L172 20 L162 30" stroke="{arrow_color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
    </svg>'''

    # Rodapé padrão
    nav_c = txt
    footer = f"""<div class="footer" style="color:{nav_c}">
      <div class="nav-arrows">
        <div class="nav-btn" style="border-color:{nav_c};color:{nav_c}">‹</div>
        <div class="nav-btn" style="border-color:{nav_c};color:{nav_c}">›</div>
      </div>
      <div class="f-handle">{handle}
        <span class="verify" style="color:#4A90E2">●</span>
      </div>
      <div class="f-pill" style="border-color:{nav_c};color:{nav_c}">Seguindo ∨</div>
      <div class="f-date" style="color:{nav_c};opacity:0.5">Janeiro 2026</div>
    </div>"""

    # Título com destaque sublinhado
    def title_hl(t, c, hl_word=""):
        if hl_word and hl_word in t:
            return t.replace(hl_word, f'<span style="text-decoration:underline;text-decoration-color:{red}">{hl_word}</span>', 1)
        return t

    thl = title_hl(titulo, title_c, hl)

    if is_capa:
        # Foto full-bleed escura com overlay + halftone + título embaixo
        overlay = f'<div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(5,5,20,0.3) 0%,rgba(5,5,20,0.85) 65%);z-index:1"></div>'
        foto_bg = f'<div style="position:absolute;inset:0;background:url(\'{img_url}\') center/cover no-repeat;z-index:0"></div>' if img_url else f'<div style="position:absolute;inset:0;background:linear-gradient(145deg,#0a0a2a,#1a1a4a);z-index:0"></div>'
        # Elementos técnicos
        tech = f"""
<div style="position:absolute;top:44px;left:52px;z-index:10;font-size:13px;font-weight:600;color:rgba(255,255,255,0.9);letter-spacing:2px">{handle} <span style="color:#4A90E2">✓</span></div>
<div style="position:absolute;top:44px;right:52px;z-index:10;font-size:13px;color:rgba(255,255,255,0.5);letter-spacing:1px">Janeiro 2026</div>"""
        body = f"""
<div style="position:absolute;inset:0">
  {foto_bg}
  {overlay}
  {tech}
  <div style="position:absolute;bottom:130px;left:52px;right:52px;z-index:5">
    <h1 style="font-family:'Barlow Condensed',sans-serif;font-weight:900;font-size:{min(ts,110)}px;line-height:0.92;color:#fff;text-transform:uppercase;letter-spacing:-0.5px;margin-bottom:16px">{titulo}</h1>
    <div style="display:flex;align-items:center;gap:16px">
      {hand_arrow}
      <p style="font-size:20px;color:{sub_c};font-family:'Inter',sans-serif;max-width:520px;line-height:1.4">{corpo}</p>
    </div>
  </div>
</div>"""

    elif img_local and palette == 1:
        # Texto top + foto bottom strip (dark)
        body = f"""
<div style="padding:52px 52px 0">
  <h2 style="font-family:'Barlow Condensed',sans-serif;font-weight:900;font-size:{min(ts,96)}px;line-height:0.92;color:{title_c};text-transform:uppercase;letter-spacing:-0.5px;margin-bottom:20px">{thl}</h2>
  <p style="font-size:20px;color:{txt};line-height:1.6;max-width:900px;margin-bottom:12px">{corpo}</p>
  <p style="font-size:20px;color:{sub_c};text-decoration:underline;line-height:1.5;max-width:900px">{dado or (lista[0] if lista else "")}</p>
</div>
<div style="position:absolute;bottom:80px;left:52px;right:52px;height:260px;background:url('{img_url}') center/cover no-repeat;border-radius:4px"></div>
<div style="position:absolute;bottom:130px;left:50%;transform:translateX(-50%)">{hand_arrow}</div>"""

    elif img_local and palette == 2:
        # Citação dourada + caixa preta (branco)
        body = f"""
<div style="padding:52px 52px 0">
  <h2 style="font-family:'Barlow Condensed',sans-serif;font-weight:900;font-size:{min(ts,100)}px;line-height:0.90;color:{title_c};text-transform:uppercase;letter-spacing:-0.5px;margin-bottom:24px">{thl}</h2>
</div>
<div style="margin:0 52px;background:#0D0D0D;border-radius:4px;padding:36px 40px">
  <p style="font-size:21px;color:#fff;line-height:1.65;margin-bottom:16px">{corpo}</p>
  <p style="font-size:21px;color:{red};text-decoration:underline;line-height:1.5">{dado or (lista[0] if lista else cta_txt)}</p>
</div>"""

    elif palette == 0 and not img_local:
        # Só texto vermelho ALL CAPS + sublinhado + corpo
        body = f"""
<div style="padding:52px 52px 0">
  <h2 style="font-family:'Barlow Condensed',sans-serif;font-weight:900;font-size:{min(ts,110)}px;line-height:0.90;color:{title_c};text-transform:uppercase;letter-spacing:-0.5px;margin-bottom:32px">{thl}</h2>
  <p style="font-size:24px;color:{red};text-decoration:underline;line-height:1.55;max-width:900px;margin-bottom:24px">{dado or corpo[:120] if corpo else ""}</p>
  <p style="font-size:21px;color:{txt};line-height:1.65;max-width:900px">{corpo}</p>
</div>"""

    elif is_cta:
        body = f"""
<div style="padding:0 52px">
  {'<div style="height:280px;background:url(' + chr(39) + img_url + chr(39) + ') center/cover no-repeat;margin-bottom:36px;border-radius:4px"></div>' if img_url else ''}
  <h2 style="font-family:\'Barlow Condensed\',sans-serif;font-weight:900;font-size:{min(ts,110)}px;line-height:0.90;color:{title_c};text-transform:uppercase;letter-spacing:-0.5px;text-align:center;margin-bottom:16px">{thl}</h2>
  <p style="font-size:22px;color:{red};text-align:center;line-height:1.5;margin-bottom:16px">{cta_txt}</p>
  <div style="text-align:center">
    <span style="font-size:13px;border:1.5px solid {txt};border-radius:100px;padding:8px 20px;color:{txt}">Leia a Legenda ∨</span>
  </div>
</div>"""

    else:
        # Default: texto + corpo normal
        body = f"""
<div style="padding:52px 52px 0">
  <h2 style="font-family:'Barlow Condensed',sans-serif;font-weight:900;font-size:{min(ts,100)}px;line-height:0.90;color:{title_c};text-transform:uppercase;letter-spacing:-0.5px;margin-bottom:28px">{thl}</h2>
  <p style="font-size:22px;color:{txt};line-height:1.65;max-width:900px">{corpo}</p>
  {''.join(f"<p style='font-size:21px;color:{txt};line-height:1.55;margin-top:12px'>— {i}</p>" for i in lista)}
</div>"""

    css = f"""
{_BARLOW}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:1080px;height:1080px;overflow:hidden;background:{bg};
     font-family:'Inter',sans-serif;color:{txt};position:relative}}
.footer{{position:absolute;bottom:0;left:0;right:0;height:76px;
         display:flex;align-items:center;justify-content:space-between;
         padding:0 52px;border-top:1px solid rgba(128,128,128,0.15)}}
.nav-arrows{{display:flex;gap:8px}}
.nav-btn{{width:32px;height:32px;border-radius:50%;border:1.5px solid;
          display:flex;align-items:center;justify-content:center;font-size:16px}}
.f-handle{{font-size:14px;font-weight:600;display:flex;align-items:center;gap:6px}}
.verify{{font-size:10px}}
.f-pill{{font-size:12px;border:1px solid;border-radius:100px;padding:4px 12px}}
.f-date{{font-size:13px;font-weight:400}}
"""
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>{css}</style></head><body>
{body}
{footer}
</body></html>"""


# ── Dispatcher ────────────────────────────────────────────────────
_NAME_TO_NUM = {
    "authority_dark":    "1",
    "dark neon":         "1",
    "clean_editorial":   "2",
    "clean editorial":   "2",
    "clean":             "2",
    "vibrant_gradient":  "3",
    "vibrant gradient":  "3",
    "vibrant":           "3",
    "foto_bold":         "4",
    "foto bold":         "4",
    "minimal_type":      "5",
    "minimal type":      "5",
    "minimal":           "5",
    "x_thread":          "6",
    "x thread":          "6",
    "x_thread_dark":     "6d",
    "x thread dark":     "6d",
    "thread":            "6",
    "linkedin_blur":     "7",
    "linkedin blur":     "7",
    "linkedin":          "7",
    "linkedin_blur_dark":"7d",
    "linkedin dark":     "7d",
    "studio_shodwe":     "8",
    "studio shodwe":     "8",
    "shodwe":            "8",
    "serif_elegante":    "9",
    "serif elegante":    "9",
    "elegante":          "9",
    "brands_decoded":    "10",
    "brands decoded":    "10",
    "brandsdecoded":     "10",
}

def gerar_html_slide(
    slide: dict,
    total: int,
    tema: str,
    accent: str,
    accent2: str,
    img_local: str = "",
    logo_url: str | None = None,
    username: str = "",
    template: str = "4",
    avatar_local: str = "",
    nome_display: str = "",
) -> str:
    t = _NAME_TO_NUM.get(str(template).lower().strip(), template)
    if t == "1":
        return _html_authority_dark(slide, total, tema, accent, accent2, logo_url, username)
    elif t == "2":
        return _html_clean_editorial(slide, total, tema, accent, logo_url, username)
    elif t == "3":
        return _html_vibrant_gradient(slide, total, tema, accent, accent2, logo_url, username)
    elif t == "5":
        return _html_minimal_type(slide, total, tema, accent, logo_url, username)
    elif t == "6":
        return _html_x_thread(slide, total, tema, accent, avatar_local, nome_display, username, dark=False)
    elif t == "6d":
        return _html_x_thread(slide, total, tema, accent, avatar_local, nome_display, username, dark=True)
    elif t == "7":
        return _html_linkedin_blur(slide, total, tema, accent, logo_url, username, dark=False)
    elif t == "7d":
        return _html_linkedin_blur(slide, total, tema, accent, logo_url, username, dark=True)
    elif t == "8":
        return _html_studio_shodwe(slide, total, tema, accent, img_local, logo_url, username)
    elif t == "9":
        return _html_serif_elegante(slide, total, tema, accent, logo_url, username)
    elif t == "10":
        return _html_brands_decoded(slide, total, tema, accent, img_local, logo_url, username)
    else:  # "4" default
        return _html_foto_bold(slide, total, tema, accent, accent2, img_local, logo_url, username)


# ── Render PNG via subprocess (avoids asyncio/Windows conflicts) ───
_RENDER_SCRIPT = str(Path(__file__).parent.parent / "render_slide.py")

async def _render_slide_async(html_path: str, png_path: str):
    import subprocess, sys
    result = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, _RENDER_SCRIPT, html_path, png_path],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"render_slide failed:\n{result.stderr}")


# ── Claude sync helper (com retry em overload) ─────────────────────
def _gerar_conteudo_sync(api_key: str, prompt: str) -> str:
    import time
    client = anthropic.Anthropic(api_key=api_key)
    for tentativa in range(4):
        try:
            resposta = ""
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    resposta += text
            return resposta
        except Exception as e:
            if "overloaded" in str(e).lower() and tentativa < 3:
                time.sleep(8 * (tentativa + 1))  # 8s, 16s, 24s
                continue
            raise


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
    template: str = "4",
    finalidade: str = "",
    cta_objetivo: str = "",
    avatar_path: str = "",
) -> list[Path]:
    pasta_destino.mkdir(parents=True, exist_ok=True)
    pasta_html = pasta_destino / "html"
    pasta_html.mkdir(exist_ok=True)

    # Normalise template to numeric key
    t = _NAME_TO_NUM.get(str(template).lower().strip(), str(template))
    if t not in ("1","2","3","4","5","6","6d","7","7d","8","9","10"):
        t = "4"
    template = t

    # Templates que precisam de foto do Pexels
    needs_image = template in ("4", "8", "10")
    is_x_thread = template in ("6", "6d")

    # Extract brand colors
    accent, accent2 = _extract_colors(cores_marca)

    # Build prompt and call Claude
    prompt   = construir_prompt(tema, plataforma, nicho, restricoes, cores_marca, template, username, finalidade, cta_objetivo)
    resposta = await asyncio.to_thread(_gerar_conteudo_sync, api_key, prompt)

    dados  = parse_json_resposta(resposta)
    slides = dados.get("slides", [])

    # Top-level pexels query fallback
    query_pexels = dados.get("query_pexels", tema)

    logo_url = None
    if logo_path and Path(logo_path).exists():
        logo_url = f"file:///{logo_path.replace(chr(92), '/')}"

    # Para X Thread: usa avatar enviado pelo usuário ou tenta scrape do Instagram
    avatar_local = ""
    nome_display = ""
    if is_x_thread:
        nome_display = username.lstrip("@").replace("_", " ").replace(".", " ").title()
        if avatar_path and Path(avatar_path).exists():
            # Copia para a pasta do carrossel para ter o arquivo local junto
            dest_av = pasta_destino / "avatar.jpg"
            dest_av.write_bytes(Path(avatar_path).read_bytes())
            avatar_local = str(dest_av.absolute())
        elif username:
            dest_av = pasta_destino / "avatar.jpg"
            try:
                avatar_local = await asyncio.to_thread(
                    buscar_avatar_instagram, username, dest_av
                )
            except Exception:
                avatar_local = ""

    pngs = []
    for slide in slides:
        num   = slide.get("numero", 1)
        # Per-slide query fallback
        query = slide.get("query_imagem") or f"{query_pexels} {num}"

        img_local = ""
        if needs_image:
            img_path = pasta_destino / f"img_{num:02d}.jpg"
            try:
                img_local = await asyncio.to_thread(
                    baixar_imagem, query, img_path, pexels_key, 1080, 1080, num - 1
                )
            except Exception:
                pass

        html_content = gerar_html_slide(
            slide, len(slides), tema,
            accent, accent2,
            img_local, logo_url, username,
            template,
            avatar_local=avatar_local,
            nome_display=nome_display,
        )
        html_path = pasta_html / f"slide_{num:02d}.html"
        html_path.write_text(html_content, encoding="utf-8")

        png_path = pasta_destino / f"slide_{num:02d}.png"
        await _render_slide_async(str(html_path.absolute()), str(png_path))
        pngs.append(png_path)

    # Salva metadata
    import json as _json
    meta = {
        "tema": tema,
        "template": template,
        "accent": accent,
        "accent2": accent2,
        "slides": slides,
        "legenda_instagram": dados.get("legenda_instagram", ""),
        "hashtags": dados.get("hashtags", []),
    }
    (pasta_destino / "metadata.json").write_text(
        _json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return pngs


# ── Legenda rápida para modo manual ───────────────────────────────
def _gerar_legenda_sync(
    api_key: str,
    tema: str,
    plataforma: str,
    nicho: str,
    cta_objetivo: str,
    finalidade: str,
) -> str:
    """Gera apenas a legenda do post via Claude (chamada rápida)."""
    cta_hint = _CTA_HINTS.get(cta_objetivo, "")
    fin_hint = _FINALIDADE_HINTS.get(finalidade, "")
    prompt = (
        f"Crie uma legenda de post para {plataforma} sobre: \"{tema}\".\n"
        f"Nicho: {nicho or 'geral'}.\n"
        f"{fin_hint}\n{cta_hint}\n"
        "Regras: tom adequado à plataforma, emojis estratégicos, hashtags no final.\n"
        "Responda APENAS com o texto da legenda, sem explicações."
    )
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


# ── Manual carousel generation ────────────────────────────────────
async def gerar_carrossel_manual(
    slides_input: list[dict],
    plataforma: str,
    tema: str,
    nicho: str,
    cores_marca: str,
    logo_path: str | None,
    username: str,
    api_key: str,
    pexels_key: str,
    pasta_destino: Path,
    template: str = "4",
    finalidade: str = "",
    cta_objetivo: str = "",
    usar_foto: bool = True,
) -> tuple[list[Path], str]:
    """
    Gera carrossel a partir de slides fornecidos manualmente pelo usuário.
    Retorna (lista de PNGs, legenda_post).
    """
    pasta_destino.mkdir(parents=True, exist_ok=True)
    pasta_html = pasta_destino / "html"
    pasta_html.mkdir(exist_ok=True)

    # Normalise template
    t = _NAME_TO_NUM.get(str(template).lower().strip(), str(template))
    if t not in ("1","2","3","4","5","6","6d","7","7d","8","9","10"):
        t = "4"
    template = t

    needs_image = template in ("4","8","10") and usar_foto
    is_x_thread = template in ("6", "6d")
    accent, accent2 = _extract_colors(cores_marca)

    logo_url = None
    if logo_path and Path(logo_path).exists():
        logo_url = f"file:///{logo_path.replace(chr(92), '/')}"

    # Para X Thread: busca avatar do Instagram
    avatar_local = ""
    nome_display = ""
    if is_x_thread and username:
        avatar_path = pasta_destino / "avatar.jpg"
        try:
            avatar_local = await asyncio.to_thread(
                buscar_avatar_instagram, username, avatar_path
            )
        except Exception:
            avatar_local = ""
        nome_display = username.lstrip("@").replace("_", " ").replace(".", " ").title()

    # Normalise slides — garante campos obrigatórios
    TIPOS = ["gancho", "setup", "conteudo", "conteudo", "conteudo", "virada", "cta"]
    slides = []
    for i, s in enumerate(slides_input[:7]):
        slides.append({
            "numero":          i + 1,
            "tipo":            s.get("tipo") or TIPOS[i],
            "layout":          s.get("layout", "hero"),
            "categoria_label": s.get("categoria_label") or (tema.upper()[:20]),
            "titulo":          s.get("titulo", ""),
            "titulo_highlight": s.get("titulo_highlight", ""),
            "corpo":           s.get("corpo", ""),
            "lista":           s.get("lista") or None,
            "dado_destaque":   s.get("dado_destaque") or None,
            "cta":             s.get("cta") or None,
        })

    # Query pexels fallback por slide
    query_pexels = tema

    pngs = []
    for slide in slides:
        num   = slide["numero"]
        query = f"{query_pexels} {num}"

        img_local = ""
        if needs_image:
            img_path = pasta_destino / f"img_{num:02d}.jpg"
            try:
                img_local = await asyncio.to_thread(
                    baixar_imagem, query, img_path, pexels_key, 1080, 1080, num - 1
                )
            except Exception:
                pass

        html_content = gerar_html_slide(
            slide, len(slides), tema,
            accent, accent2,
            img_local, logo_url, username,
            template,
            avatar_local=avatar_local,
            nome_display=nome_display,
        )
        html_path = pasta_html / f"slide_{num:02d}.html"
        html_path.write_text(html_content, encoding="utf-8")

        png_path = pasta_destino / f"slide_{num:02d}.png"
        await _render_slide_async(str(html_path.absolute()), str(png_path))
        pngs.append(png_path)

    # Gera legenda via Claude (rápido)
    legenda = ""
    if api_key:
        try:
            legenda = await asyncio.to_thread(
                _gerar_legenda_sync, api_key, tema, plataforma,
                nicho, cta_objetivo, finalidade,
            )
        except Exception:
            pass

    # Salva metadata
    import json as _json
    meta = {
        "tema": tema, "template": template, "modo": "manual",
        "accent": accent, "accent2": accent2,
        "slides": slides, "legenda_instagram": legenda,
    }
    (pasta_destino / "metadata.json").write_text(
        _json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return pngs, legenda

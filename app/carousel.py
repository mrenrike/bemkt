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
    """Extract up to 2 hex colors from brand colors string."""
    hexes = re.findall(r'#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', cores_marca or "")
    accent  = hexes[0] if hexes else "#8CFF2E"
    accent2 = hexes[1] if len(hexes) > 1 else "#ff6a00"
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
    "1": "authority_dark",
    "2": "clean_editorial",
    "3": "vibrant_gradient",
    "4": "foto_bold",
    "5": "minimal_type",
}
_TEMPLATE_HINTS = {
    "authority_dark":   "Títulos bold e curtos. Uma palavra/frase em titulo_highlight (substring exata). Tom: autoridade, premium. Sem emoji no corpo.",
    "clean_editorial":  "Linguagem elaborada. Listas numeradas são bem-vindas. Tom: profissional, refinado.",
    "vibrant_gradient": "Energia alta. Verbos de ação. Emojis ocasionais no corpo. Tom: motivacional.",
    "foto_bold":        "Headline único e poderoso (máx 6 palavras). Corpo mínimo. A foto carrega o visual.",
    "minimal_type":     "Frases filosóficas, dados isolados ou perguntas provocadoras. Use dado_destaque para estatísticas. Máx 1 ideia por slide. Corpo curto.",
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
    tname    = _TEMPLATE_NAMES.get(str(template), "foto_bold")
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


# ── Dispatcher ────────────────────────────────────────────────────
_NAME_TO_NUM = {
    "authority_dark":   "1",
    "brandsDecoded":    "1",
    "dark neon":        "1",
    "clean_editorial":  "2",
    "clean editorial":  "2",
    "clean":            "2",
    "vibrant_gradient": "3",
    "vibrant gradient": "3",
    "vibrant":          "3",
    "foto_bold":        "4",
    "foto bold":        "4",
    "minimal_type":     "5",
    "minimal type":     "5",
    "minimal":          "5",
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
) -> list[Path]:
    pasta_destino.mkdir(parents=True, exist_ok=True)
    pasta_html = pasta_destino / "html"
    pasta_html.mkdir(exist_ok=True)

    # Normalise template to numeric key
    t = _NAME_TO_NUM.get(str(template).lower().strip(), str(template))
    if t not in ("1", "2", "3", "4", "5"):
        t = "4"
    template = t

    # Templates 1, 2, 3, 5 não precisam de foto; Template 4 precisa
    needs_image = (template == "4")

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
    if t not in ("1", "2", "3", "4", "5"):
        t = "4"
    template = t

    needs_image = (template == "4") and usar_foto
    accent, accent2 = _extract_colors(cores_marca)

    logo_url = None
    if logo_path and Path(logo_path).exists():
        logo_url = f"file:///{logo_path.replace(chr(92), '/')}"

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

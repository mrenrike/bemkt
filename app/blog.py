# app/blog.py
# Renderiza as páginas do blog BeContent como strings HTML

from .blog_data import POSTS, POSTS_BY_SLUG

_BASE_URL = "https://becontent.bemkt.com.br"

_COMMON_HEAD = """
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="index, follow">
  <meta name="author" content="BeContent">
  <meta name="theme-color" content="#080808">
  <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
  <link rel="icon" type="image/png" href="/static/favicon.png" sizes="32x32">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="preload" as="style" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap"
        onload="this.onload=null;this.rel='stylesheet'">
  <noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap"></noscript>
"""

_COMMON_CSS = """
  <style>
    :root {
      --bg: #080808; --surface: #111; --border: #1e1e1e;
      --text: #f0f0f0; --muted: #666; --muted2: #888;
      --accent: #8cff2e; --accent2: #ff6a00; --radius: 14px;
    }
    *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body { background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; font-size: 16px; line-height: 1.6; overflow-x: hidden; }
    a { color: inherit; text-decoration: none; }
    img { max-width: 100%; display: block; }

    /* NAV */
    nav { position: fixed; top: 0; left: 0; right: 0; z-index: 100; display: flex; align-items: center; justify-content: space-between; padding: 18px 5%; background: rgba(8,8,8,0.85); -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px); border-bottom: 1px solid var(--border); }
    .nav-logo { font-size: 20px; font-weight: 800; letter-spacing: -0.5px; }
    .nav-logo span { color: var(--accent); }
    .nav-links { display: flex; align-items: center; gap: 32px; }
    .nav-links a { font-size: 14px; color: var(--muted); font-weight: 500; transition: color .2s; }
    .nav-links a:hover, .nav-links a.active { color: var(--text); }
    .nav-cta { background: var(--accent); color: #080808; font-weight: 700; padding: 10px 22px; border-radius: 100px; font-size: 14px; transition: opacity .2s; }
    .nav-cta:hover { opacity: .85; }
    @media (max-width: 640px) { .nav-links .hide-mob { display: none; } }

    /* FOOTER */
    footer { border-top: 1px solid var(--border); padding: 48px 5% 32px; margin-top: 80px; }
    .footer-inner { max-width: 1100px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 24px; }
    .footer-logo { font-size: 18px; font-weight: 800; }
    .footer-logo span { color: var(--accent); }
    .footer-links { display: flex; gap: 24px; flex-wrap: wrap; }
    .footer-links a { color: var(--muted); font-size: 14px; transition: color .2s; }
    .footer-links a:hover { color: var(--text); }
    .footer-copy { color: var(--muted); font-size: 13px; margin-top: 32px; text-align: center; }

    /* BLOG LIST */
    .blog-hero { padding: 140px 5% 60px; max-width: 1100px; margin: 0 auto; }
    .blog-hero h1 { font-size: clamp(2rem, 5vw, 3.5rem); font-weight: 900; letter-spacing: -1.5px; line-height: 1.1; margin-bottom: 16px; }
    .blog-hero h1 em { color: var(--accent); font-style: normal; }
    .blog-hero p { color: var(--muted); font-size: 1.1rem; max-width: 560px; }

    .blog-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 24px; max-width: 1100px; margin: 48px auto 0; padding: 0 5% 80px; }
    .blog-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 28px; display: flex; flex-direction: column; gap: 12px; transition: border-color .2s, transform .2s; cursor: pointer; }
    .blog-card:hover { border-color: #333; transform: translateY(-3px); }
    .card-cat { font-size: 11px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: var(--accent); }
    .card-title { font-size: 1.05rem; font-weight: 700; line-height: 1.35; color: var(--text); }
    .card-desc { font-size: 0.875rem; color: var(--muted); line-height: 1.55; flex: 1; }
    .card-meta { display: flex; gap: 16px; font-size: 12px; color: var(--muted2); border-top: 1px solid var(--border); padding-top: 12px; margin-top: 4px; }
    .card-read { font-size: 13px; font-weight: 600; color: var(--accent); margin-top: 4px; display: inline-flex; align-items: center; gap: 4px; }

    /* ARTICLE */
    .art-header { padding: 140px 5% 48px; max-width: 780px; margin: 0 auto; }
    .art-cat { font-size: 11px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: var(--accent); margin-bottom: 16px; }
    .art-title { font-size: clamp(1.8rem, 4vw, 2.8rem); font-weight: 900; letter-spacing: -1px; line-height: 1.1; margin-bottom: 20px; }
    .art-meta { display: flex; gap: 20px; color: var(--muted); font-size: 13px; flex-wrap: wrap; }
    .art-body { max-width: 780px; margin: 0 auto; padding: 0 5% 80px; }
    .art-body h2 { font-size: 1.5rem; font-weight: 800; letter-spacing: -0.5px; margin: 40px 0 16px; line-height: 1.2; }
    .art-body h3 { font-size: 1.15rem; font-weight: 700; margin: 28px 0 12px; }
    .art-body p { margin-bottom: 16px; color: #d0d0d0; line-height: 1.75; }
    .art-body ul, .art-body ol { margin: 12px 0 20px 22px; color: #d0d0d0; line-height: 1.75; }
    .art-body li { margin-bottom: 8px; }
    .art-body strong { color: var(--text); font-weight: 700; }
    .art-body a { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; }
    .art-body table { width: 100%; border-collapse: collapse; margin: 24px 0; font-size: 14px; }
    .art-body th { background: var(--surface); color: var(--accent); font-weight: 700; padding: 10px 14px; text-align: left; border: 1px solid var(--border); }
    .art-body td { padding: 10px 14px; border: 1px solid var(--border); color: #d0d0d0; }
    .art-body tr:nth-child(even) td { background: rgba(255,255,255,.02); }
    .art-body [itemscope][itemtype="https://schema.org/FAQPage"] { margin-top: 40px; }
    .art-body [itemscope][itemtype="https://schema.org/Question"] { border: 1px solid var(--border); border-radius: 10px; padding: 20px 24px; margin-bottom: 12px; background: var(--surface); }
    .art-body [itemscope][itemtype="https://schema.org/Question"] h3 { margin: 0 0 10px; font-size: 1rem; }
    .art-body [itemscope][itemtype="https://schema.org/Question"] p { margin: 0; font-size: 0.9rem; }

    /* CTA BOX */
    .cta-box { background: linear-gradient(135deg, rgba(140,255,46,.08) 0%, rgba(255,106,0,.05) 100%); border: 1px solid rgba(140,255,46,.2); border-radius: var(--radius); padding: 40px; text-align: center; margin: 48px 0; }
    .cta-box h3 { font-size: 1.4rem; font-weight: 800; margin-bottom: 12px; }
    .cta-box p { color: var(--muted); margin-bottom: 24px; }
    .cta-box a { display: inline-block; background: var(--accent); color: #080808; font-weight: 800; padding: 14px 32px; border-radius: 100px; font-size: 15px; transition: opacity .2s; }
    .cta-box a:hover { opacity: .85; text-decoration: none; }

    /* BREADCRUMB */
    .breadcrumb { max-width: 780px; margin: 0 auto; padding: 100px 5% 0; font-size: 13px; color: var(--muted); display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .breadcrumb a { color: var(--muted2); }
    .breadcrumb a:hover { color: var(--text); }
    .breadcrumb span { color: #444; }

    /* RELATED */
    .related { max-width: 780px; margin: 60px auto 0; padding: 0 5%; }
    .related h2 { font-size: 1.25rem; font-weight: 800; margin-bottom: 24px; }
    .related-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
    .related-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; transition: border-color .2s; }
    .related-card:hover { border-color: #333; }
    .related-cat { font-size: 10px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: var(--accent); margin-bottom: 8px; }
    .related-title { font-size: 0.875rem; font-weight: 700; line-height: 1.35; color: var(--text); }
  </style>
"""

_NAV = """
  <nav>
    <a href="/" class="nav-logo">Be<span>Content</span></a>
    <div class="nav-links">
      <a href="/" class="hide-mob">Início</a>
      <a href="/blog" class="active">Blog</a>
      <a href="/static/planos.html" class="hide-mob">Planos</a>
      <a href="/entrar" class="nav-cta">Criar grátis</a>
    </div>
  </nav>
"""

_FOOTER = """
  <footer>
    <div class="footer-inner">
      <span class="footer-logo">Be<span>Content</span></span>
      <div class="footer-links">
        <a href="/blog">Blog</a>
        <a href="/static/planos.html">Planos</a>
        <a href="/entrar">Entrar</a>
        <a href="mailto:bruno@bemkt.com.br">Contato</a>
      </div>
    </div>
    <p class="footer-copy">© 2025 BeContent · Todos os direitos reservados</p>
  </footer>
"""


def _fmt_date(d: str) -> str:
    """'2025-01-15' → '15 jan 2025'"""
    months = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"]
    try:
        y, m, day = d.split("-")
        return f"{int(day)} {months[int(m)-1]} {y}"
    except Exception:
        return d


def render_blog_list() -> str:
    cards_html = ""
    for p in POSTS:
        cards_html += f"""
    <a href="/blog/{p['slug']}" class="blog-card">
      <span class="card-cat">{p['categoria']}</span>
      <div class="card-title">{p['titulo']}</div>
      <div class="card-desc">{p['meta_desc']}</div>
      <div class="card-meta">
        <span>{_fmt_date(p['data'])}</span>
        <span>{p['tempo_leitura']} de leitura</span>
      </div>
      <span class="card-read">Ler artigo →</span>
    </a>"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
{_COMMON_HEAD}
  <title>Blog BeContent — Carrossel, Automação e Conteúdo para Instagram</title>
  <meta name="description" content="Aprenda a criar carrosseis profissionais, automatizar conteúdo e crescer no Instagram com IA. Artigos práticos do time BeContent.">
  <link rel="canonical" href="{_BASE_URL}/blog">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{_BASE_URL}/blog">
  <meta property="og:title" content="Blog BeContent — Carrossel, Automação e Conteúdo para Instagram">
  <meta property="og:description" content="Aprenda a criar carrosseis profissionais, automatizar conteúdo e crescer no Instagram com IA.">
  <meta property="og:image" content="{_BASE_URL}/static/og-image.svg">
  <meta name="twitter:card" content="summary_large_image">
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Blog",
    "name": "Blog BeContent",
    "url": "{_BASE_URL}/blog",
    "description": "Artigos sobre carrossel para Instagram, automação de conteúdo e crescimento com IA.",
    "publisher": {{
      "@type": "Organization",
      "name": "BeContent",
      "url": "{_BASE_URL}"
    }}
  }}
  </script>
{_COMMON_CSS}
</head>
<body>
{_NAV}

<section class="blog-hero">
  <h1>Blog <em>BeContent</em></h1>
  <p>Estratégias, tutoriais e insights sobre carrossel para Instagram, automação com IA e criação de conteúdo.</p>
</section>

<section class="blog-grid">
{cards_html}
</section>

{_FOOTER}
</body>
</html>"""


def render_blog_post(slug: str) -> str | None:
    post = POSTS_BY_SLUG.get(slug)
    if not post:
        return None

    # related: up to 3 posts in same category, excluding current
    related = [p for p in POSTS if p["slug"] != slug and p["categoria"] == post["categoria"]][:3]
    if len(related) < 3:
        extra = [p for p in POSTS if p["slug"] != slug and p not in related]
        related += extra[:3 - len(related)]

    related_html = ""
    for r in related:
        related_html += f"""
      <a href="/blog/{r['slug']}" class="related-card">
        <div class="related-cat">{r['categoria']}</div>
        <div class="related-title">{r['titulo']}</div>
      </a>"""

    cta_html = """
<div class="cta-box">
  <h3>Crie seu carrossel em 60 segundos</h3>
  <p>A IA escreve o conteúdo e gera 7 slides prontos para postar. Sem Canva, sem designer.</p>
  <a href="https://becontent.bemkt.com.br/entrar">Experimente grátis →</a>
</div>"""

    # Inject CTA after ~half of content
    content = post["conteudo"]
    # Find a </h2> roughly in the middle to inject the CTA
    parts = content.split("</h2>")
    if len(parts) >= 4:
        mid = len(parts) // 2
        content = "</h2>".join(parts[:mid]) + "</h2>" + cta_html + "</h2>".join(parts[mid:])

    article_schema = f"""
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "{post['titulo'].replace('"', '&quot;')}",
    "description": "{post['meta_desc'].replace('"', '&quot;')}",
    "url": "{_BASE_URL}/blog/{post['slug']}",
    "datePublished": "{post['data']}",
    "dateModified": "{post['data']}",
    "author": {{
      "@type": "Organization",
      "name": "BeContent",
      "url": "{_BASE_URL}"
    }},
    "publisher": {{
      "@type": "Organization",
      "name": "BeContent",
      "url": "{_BASE_URL}",
      "logo": {{
        "@type": "ImageObject",
        "url": "{_BASE_URL}/static/favicon.svg"
      }}
    }},
    "inLanguage": "pt-BR",
    "mainEntityOfPage": {{
      "@type": "WebPage",
      "@id": "{_BASE_URL}/blog/{post['slug']}"
    }}
  }}
  </script>"""

    breadcrumb_schema = f"""
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
      {{"@type": "ListItem", "position": 1, "name": "Início", "item": "{_BASE_URL}/"}},
      {{"@type": "ListItem", "position": 2, "name": "Blog", "item": "{_BASE_URL}/blog"}},
      {{"@type": "ListItem", "position": 3, "name": "{post['titulo'].replace('"', '&quot;')}", "item": "{_BASE_URL}/blog/{post['slug']}"}}
    ]
  }}
  </script>"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
{_COMMON_HEAD}
  <title>{post['titulo']} — Blog BeContent</title>
  <meta name="description" content="{post['meta_desc']}">
  <link rel="canonical" href="{_BASE_URL}/blog/{post['slug']}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{_BASE_URL}/blog/{post['slug']}">
  <meta property="og:title" content="{post['titulo']}">
  <meta property="og:description" content="{post['meta_desc']}">
  <meta property="og:image" content="{_BASE_URL}/static/og-image.svg">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{post['titulo']}">
  <meta name="twitter:description" content="{post['meta_desc']}">
{article_schema}
{breadcrumb_schema}
{_COMMON_CSS}
</head>
<body>
{_NAV}

<nav class="breadcrumb" aria-label="breadcrumb">
  <a href="/">Início</a>
  <span>›</span>
  <a href="/blog">Blog</a>
  <span>›</span>
  <span>{post['categoria']}</span>
</nav>

<header class="art-header">
  <div class="art-cat">{post['categoria']}</div>
  <h1 class="art-title">{post['titulo']}</h1>
  <div class="art-meta">
    <span>{_fmt_date(post['data'])}</span>
    <span>·</span>
    <span>{post['tempo_leitura']} de leitura</span>
  </div>
</header>

<article class="art-body">
{content}

{cta_html}
</article>

<section class="related">
  <h2>Artigos relacionados</h2>
  <div class="related-grid">
{related_html}
  </div>
</section>

{_FOOTER}
</body>
</html>"""

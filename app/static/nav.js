/* app/static/nav.js — topbar injetada em todas as páginas autenticadas */
(function () {
  const LINKS = [
    { href: '/static/chat.html',      label: 'Automático',  page: 'chat'      },
    { href: '/static/editor.html',    label: 'Manual',      page: 'editor'    },
    { href: '/static/historico.html', label: 'Histórico',   page: 'historico' },
    { href: '/static/planos.html',    label: 'Planos',      page: 'planos'    },
    { href: '/static/perfil.html',    label: 'Perfil',      page: 'perfil'    },
  ];

  const currentPage = (function () {
    const p = window.location.pathname;
    if (p.includes('editor'))    return 'editor';
    if (p.includes('chat'))      return 'chat';
    if (p.includes('historico')) return 'historico';
    if (p.includes('planos'))    return 'planos';
    if (p.includes('perfil'))    return 'perfil';
    return '';
  })();

  const navLinks = LINKS.map(l =>
    `<a href="${l.href}" class="topbar-link${l.page === currentPage ? ' active' : ''}">${l.label}</a>`
  ).join('');

  // Topbar
  const bar = document.createElement('header');
  bar.className = 'app-topbar';
  bar.setAttribute('role', 'banner');
  bar.innerHTML = `
    <a href="/static/chat.html" class="topbar-logo">BEMKT<span>.</span></a>
    <nav class="topbar-nav" aria-label="Navegação principal">${navLinks}</nav>
    <div class="topbar-right">
      <div class="topbar-credits" id="topbar-credits"><em>—</em> créditos</div>
      <button type="button" class="topbar-logout" id="topbar-logout">Sair</button>
      <button type="button" class="topbar-hamburger" id="topbar-hamburger" aria-label="Menu">&#9776;</button>
    </div>`;

  // Mobile nav drawer
  const mobileNav = document.createElement('nav');
  mobileNav.className = 'topbar-mobile-nav';
  mobileNav.setAttribute('aria-label', 'Menu mobile');
  mobileNav.innerHTML = LINKS.map(l =>
    `<a href="${l.href}" class="topbar-link${l.page === currentPage ? ' active' : ''}">${l.label}</a>`
  ).join('') + `<button type="button" class="topbar-link" id="mobile-logout" style="border:none;cursor:pointer;background:none;font-family:inherit;text-align:left;color:var(--muted)">Sair</button>`;

  document.body.prepend(mobileNav, bar);
  document.body.classList.add('has-topbar');

  // Hamburger toggle
  let menuOpen = false;
  document.getElementById('topbar-hamburger').addEventListener('click', function () {
    menuOpen = !menuOpen;
    mobileNav.classList.toggle('open', menuOpen);
  });

  // Fecha ao clicar fora
  document.addEventListener('click', function (e) {
    if (menuOpen && !bar.contains(e.target) && !mobileNav.contains(e.target)) {
      menuOpen = false;
      mobileNav.classList.remove('open');
    }
  });

  // Logout
  function logout() { localStorage.clear(); window.location = '/'; }
  document.getElementById('topbar-logout').addEventListener('click', logout);
  document.getElementById('mobile-logout').addEventListener('click', logout);

  // Créditos
  const token = localStorage.getItem('token');
  if (token) {
    fetch('/me', { headers: { 'Authorization': 'Bearer ' + token } })
      .then(r => r.ok ? r.json() : null)
      .then(function (d) {
        if (!d) return;
        const el = document.getElementById('topbar-credits');
        if (el) el.innerHTML = '<em>' + d.creditos + '</em> crédito' + (d.creditos !== 1 ? 's' : '');
      })
      .catch(function () {});
  }
})();

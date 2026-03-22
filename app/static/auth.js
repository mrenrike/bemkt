// Intercepta qualquer fetch que retorne 401 e redireciona para login
const _fetch = window.fetch.bind(window);
window.fetch = async function(...args) {
  const r = await _fetch(...args);
  if (r.status === 401) {
    localStorage.clear();
    window.location = '/static/entrar.html';
    return r;
  }
  return r;
};

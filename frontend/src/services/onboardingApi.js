const BASE = (import.meta.env.VITE_API_URL ?? '/api') + '/onboarding';

async function get(url, signal) {
  const resp = await fetch(url, { signal });
  if (!resp.ok) throw new Error(`API error ${resp.status}`);
  return resp.json();
}

export const searchBooks     = (q, signal) => get(`${BASE}/books?q=${encodeURIComponent(q)}`, signal);
export const searchLibraries = (q, signal) => get(`${BASE}/libraries?q=${encodeURIComponent(q)}`, signal);
export const getCategories   = ()           => get(`${BASE}/categories`);

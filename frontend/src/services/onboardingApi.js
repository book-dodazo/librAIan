const BASE = (import.meta.env.VITE_API_URL ?? '/api') + '/onboarding';

async function get(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`API error ${resp.status}`);
  return resp.json();
}

export const searchBooks     = (q) => get(`${BASE}/books?q=${encodeURIComponent(q)}`);
export const searchLibraries = (q) => get(`${BASE}/libraries?q=${encodeURIComponent(q)}`);
export const getCategories   = ()  => get(`${BASE}/categories`);

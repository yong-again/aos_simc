// Relative by default: in production the FastAPI server serves the
// built frontend (same origin); in dev the Vite proxy forwards /api.
const BASE = import.meta.env.VITE_API_BASE || '';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
    ...options,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const getFactions = () => request('/api/factions');
export const getWarscrolls = (slug) => request(`/api/factions/${slug}/warscrolls`);
export const getWarscrollKo = (slug, wsId) =>
  request(`/api/factions/${slug}/warscrolls/${encodeURIComponent(wsId)}/ko`);
export const parseRoster = (text) =>
  request('/api/roster/parse', { method: 'POST', body: JSON.stringify({ text }) });
export const generateRoster = (faction_slug, points) =>
  request('/api/roster/generate', {
    method: 'POST',
    body: JSON.stringify({ faction_slug, points }),
  });
export const setupBattle = (player_roster, enemy_roster) =>
  request('/api/setup', {
    method: 'POST',
    body: JSON.stringify({ player_roster, enemy_roster }),
  });
export const runSimulation = (player_roster, enemy_roster, deployment) =>
  request('/api/simulate', {
    method: 'POST',
    body: JSON.stringify({ player_roster, enemy_roster, deployment }),
  });

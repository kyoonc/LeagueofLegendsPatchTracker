// Points at the local dev server by default. In production (Vercel),
// set VITE_API_URL in the project's environment variables to your
// deployed Render backend URL instead of editing this file.
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

async function request(path) {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

export function fetchChampions() {
  return request("/champions");
}

export function fetchPatches() {
  return request("/patches");
}

export function fetchDiff(champion, start, end) {
  const params = new URLSearchParams({ champion, start, end });
  return request(`/diff?${params}`);
}

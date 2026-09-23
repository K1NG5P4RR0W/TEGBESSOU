// Squelette du client API (D0). Le vrai câblage (login, refresh) arrive en DASH-1.
// Voir docs/ui/frontend-architecture.md et api-contract.md (repo privé).

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8001";

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (accessToken !== null) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  const resp = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`API ${resp.status}: ${detail}`);
  }
  return (await resp.json()) as T;
}

export const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "booktranslate_api_token";
const REFRESH_TOKEN_KEY = "booktranslate_refresh_token";
let refreshPromise: Promise<string> | null = null;

export function getApiToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_KEY) ?? "";
}

export function getRefreshToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(REFRESH_TOKEN_KEY) ?? "";
}

export function setApiToken(token: string) {
  if (typeof window === "undefined") return;
  const value = token.trim();
  if (value) window.localStorage.setItem(TOKEN_KEY, value);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export function setSessionTokens(token: string, refreshToken?: string) {
  setApiToken(token);
  if (typeof window === "undefined" || refreshToken === undefined) return;
  const value = refreshToken.trim();
  if (value) window.localStorage.setItem(REFRESH_TOKEN_KEY, value);
  else window.localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function clearSessionTokens() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
}

async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) return refreshPromise;
  const refreshToken = getRefreshToken();
  if (!refreshToken) throw new Error("No refresh token available");
  refreshPromise = (async () => {
    try {
      const response = await fetch(`${apiUrl}/api/auth/session/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.token || !payload.refresh_token) {
        clearSessionTokens();
        throw new Error(payload.detail ?? "Session refresh failed");
      }
      setSessionTokens(String(payload.token), String(payload.refresh_token));
      return String(payload.token);
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

async function fetchWithToken(path: string, init: RequestInit, token: string) {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(path.startsWith("http") ? path : `${apiUrl}${path}`, { ...init, headers });
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  let response = await fetchWithToken(path, init, getApiToken());
  if (response.status !== 401 || path.includes("/api/auth/session/refresh") || !getRefreshToken()) return response;
  try {
    const token = await refreshAccessToken();
    response = await fetchWithToken(path, init, token);
  } catch {
    return response;
  }
  return response;
}

export async function getDownloadUrl(bookId: string, format: "docx" | "translated.docx" | "translated.epub") {
  const response = await apiFetch(`/api/books/${bookId}/export-ticket`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ format }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail ?? `Download ticket failed with ${response.status}`);
  const path = String(payload.url || "");
  return path.startsWith("http") ? path : `${apiUrl}${path}`;
}

export function oidcLoginUrl(returnTo?: string) {
  const target = returnTo ?? (typeof window !== "undefined" ? `${window.location.origin}/auth/callback` : "");
  return `${apiUrl}/api/auth/oidc/login?return_to=${encodeURIComponent(target)}`;
}

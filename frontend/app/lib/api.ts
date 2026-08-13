export const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "booktranslate_api_token";

export function getApiToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_KEY) ?? "";
}

export function setApiToken(token: string) {
  if (typeof window === "undefined") return;
  const value = token.trim();
  if (value) window.localStorage.setItem(TOKEN_KEY, value);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  const token = getApiToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(path.startsWith("http") ? path : `${apiUrl}${path}`, { ...init, headers });
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

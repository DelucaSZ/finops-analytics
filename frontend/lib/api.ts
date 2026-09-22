const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("nuvemiq_token");
}

export function setToken(token: string): void {
  window.localStorage.setItem("nuvemiq_token", token);
}

export function clearToken(): void {
  window.localStorage.removeItem("nuvemiq_token");
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  if (response.status === 401) {
    clearToken();
    if (typeof window !== "undefined") window.location.assign("/login");
    throw new Error("Sessão expirada");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail || `Erro HTTP ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function usd(value: number | string): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }).format(Number(value));
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

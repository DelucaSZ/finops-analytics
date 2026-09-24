const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const publicWrites = new Set(["/auth/mfa/verify", "/auth/login", "/auth/forgot-password", "/auth/reset-password", "/auth/accept-invitation"]);

export class ApiError extends Error {
  constructor(message: string, public status: number, public detail?: string) { super(message); }
}

export async function api<T>(path: string, init: RequestInit = {}, redirectOnUnauthorized = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) headers.set("Content-Type", "application/json");
  const method = (init.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    headers.set("X-DeepOps-Request", "1");
    if (!publicWrites.has(path)) {
      // Fetch for each mutation: no token storage, and another tab's login cannot leave stale CSRF state.
      const csrf = await api<{ csrf_token: string }>("/auth/csrf", {}, redirectOnUnauthorized);
      headers.set("X-CSRF-Token", csrf.csrf_token);
    }
  }
  const response = await fetch(`${API_URL}${path}`, { ...init, headers, credentials: "include", cache: "no-store" });
  if (response.status === 401 && !publicWrites.has(path) && redirectOnUnauthorized) {
    if (typeof window !== "undefined") window.location.assign("/login");
    throw new ApiError("Sessão expirada. Entre novamente.", 401);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    if (detail === "mfa_enrollment_required" && typeof window !== "undefined") {
      window.location.assign("/mfa-setup");
      throw new ApiError("Configure o autenticador para continuar.", 403);
    }
    const translated: Record<string, string> = {
      "Email is already registered": "Este e-mail já está cadastrado.",
      "Cannot remove the last active administrator": "Mantenha pelo menos um administrador ativo com senha definida.",
      "User not found": "Usuário não encontrado.",
      "Administrator access required": "Acesso disponível somente para administradores.",
      "Administrator access changed; sign in again": "Suas permissões mudaram. Entre novamente.",
    };
    const message = detail === "reauthentication_required"
      ? "Confirme sua identidade em Minha segurança antes de continuar."
      : Array.isArray(detail) ? "Confira os campos preenchidos e tente novamente."
      : detail === "Invalid email or password" ? "E-mail ou senha inválidos."
      : translated[detail] || detail || `Erro HTTP ${response.status}`;
    throw new ApiError(message, response.status, typeof detail === "string" ? detail : undefined);
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

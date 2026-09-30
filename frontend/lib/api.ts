const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const API_TIMEOUT_MS = 30_000;
const publicWrites = new Set(["/auth/mfa/verify", "/auth/login", "/auth/forgot-password", "/auth/reset-password", "/auth/accept-invitation"]);

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: string,
    public code?: string,
  ) {
    super(message);
  }
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
  const timeoutController = new AbortController();
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    timeoutController.abort();
  }, API_TIMEOUT_MS);
  const callerSignal = init.signal;
  const abortFromCaller = () => timeoutController.abort();
  if (callerSignal?.aborted) timeoutController.abort();
  else callerSignal?.addEventListener("abort", abortFromCaller, { once: true });

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers,
      credentials: "include",
      cache: "no-store",
      signal: timeoutController.signal,
    });
  } catch (error) {
    if (timedOut && !callerSignal?.aborted) {
      throw new ApiError("A solicitação excedeu o tempo limite. Tente novamente.", 408);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
    callerSignal?.removeEventListener("abort", abortFromCaller);
  }

  if (response.status === 401 && !publicWrites.has(path) && redirectOnUnauthorized) {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("deepops:session-invalidated"));
      window.location.assign("/login");
    }
    throw new ApiError("Sessão expirada. Entre novamente.", 401);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    const structuredDetail = detail && typeof detail === "object" && !Array.isArray(detail)
      ? detail as { code?: unknown; message?: unknown }
      : null;
    const detailText = typeof detail === "string"
      ? detail
      : typeof structuredDetail?.message === "string"
        ? structuredDetail.message
        : undefined;
    const detailCode = typeof structuredDetail?.code === "string" ? structuredDetail.code : undefined;
    if (detail === "mfa_enrollment_required" && typeof window !== "undefined") {
      window.dispatchEvent(new Event("deepops:session-invalidated"));
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
    const fallbackByStatus: Record<number, string> = {
      403: "Você não tem permissão para realizar esta ação.",
      404: "O recurso solicitado não foi encontrado.",
      410: "Os dados históricos detalhados não estão mais disponíveis pela política de retenção.",
      422: "Confira os campos preenchidos e tente novamente.",
      429: "Muitas solicitações em pouco tempo. Tente novamente em instantes.",
    };
    const message = detail === "reauthentication_required"
      ? "Confirme sua identidade em Minha segurança antes de continuar."
      : Array.isArray(detail) ? "Confira os campos preenchidos e tente novamente."
      : detail === "Invalid email or password" ? "E-mail ou senha inválidos."
      : translated[typeof detail === "string" ? detail : ""]
        || (detailText && !detailText.includes("Traceback") ? detailText : undefined)
        || (response.status >= 500
          ? "Não foi possível concluir a solicitação. Tente novamente."
          : fallbackByStatus[response.status])
        || "Não foi possível concluir a solicitação.";
    throw new ApiError(message, response.status, detailText, detailCode);
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

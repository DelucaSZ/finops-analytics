const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const API_TIMEOUT_MS = 30_000;
const publicWrites = new Set(["/auth/mfa/verify", "/auth/login", "/auth/forgot-password", "/auth/reset-password", "/auth/accept-invitation"]);

function dispatchAuthRedirect(path: string) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event("deepops:session-invalidated"));
  window.dispatchEvent(
    new CustomEvent("deepops:auth-redirect", { detail: { path } }),
  );
}

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
    if (!callerSignal?.aborted && error instanceof TypeError) {
      throw new ApiError(
        "Não foi possível conectar ao serviço. Verifique sua conexão e tente novamente.",
        0,
      );
    }
    throw error;
  } finally {
    clearTimeout(timeout);
    callerSignal?.removeEventListener("abort", abortFromCaller);
  }

  if (response.status === 401 && !publicWrites.has(path) && redirectOnUnauthorized) {
    dispatchAuthRedirect("/login");
    throw new ApiError("Sessão expirada. Entre novamente.", 401);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    if (detail === "mfa_enrollment_required") {
      dispatchAuthRedirect("/mfa-setup");
      throw new ApiError("Configure o autenticador para continuar.", 403);
    }
    const translated: Record<string, string> = {
      "Email is already registered": "Este e-mail já está cadastrado.",
      "Cannot remove the last active administrator": "Mantenha pelo menos um administrador ativo com senha definida.",
      "User not found": "Usuário não encontrado.",
      "Administrator access required": "Acesso disponível somente para administradores.",
      "Administrator access changed; sign in again": "Suas permissões mudaram. Entre novamente.",
    };
    const retentionExpired =
      typeof detail === "string" &&
      detail.startsWith("COLLECTION_OBSERVATIONS_EXPIRED:");
    const statusFallback: Record<number, string> = {
      403: "Você não tem permissão para realizar esta ação.",
      404: "O recurso solicitado não foi encontrado.",
      409: "Não foi possível concluir porque o estado dos dados mudou. Atualize e tente novamente.",
      410: "Os detalhes históricos solicitados não estão mais disponíveis pela política de retenção.",
      422: "Confira os campos preenchidos e tente novamente.",
      500: "O serviço encontrou um erro inesperado. Tente novamente.",
      502: "O serviço está temporariamente indisponível. Tente novamente.",
      503: "O serviço está temporariamente indisponível. Tente novamente.",
      504: "O serviço demorou demais para responder. Tente novamente.",
    };
    const message = detail === "reauthentication_required"
      ? "Confirme sua identidade em Minha segurança antes de continuar."
      : retentionExpired
        ? statusFallback[410]
        : Array.isArray(detail)
          ? statusFallback[422]
          : detail === "Invalid email or password"
            ? "E-mail ou senha inválidos."
            : translated[detail] ||
              statusFallback[response.status] ||
              detail ||
              "Não foi possível concluir a solicitação. Tente novamente.";
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

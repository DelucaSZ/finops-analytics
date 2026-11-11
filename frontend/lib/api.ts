import ptBRMessages from "@/i18n/messages/pt-BR.json";
import enUSMessages from "@/i18n/messages/en-US.json";
import {formatLocaleCurrency, formatLocaleDate, formatLocaleDateTime} from "@/i18n/formatters.mjs";
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const API_TIMEOUT_MS = 30_000;
function apiErrorText(key: keyof typeof ptBRMessages.errors.api): string {
  const locale = typeof document !== "undefined" ? document.documentElement.lang : "pt-BR";
  return (locale === "en-US" ? enUSMessages : ptBRMessages).errors.api[key];
}
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
      throw new ApiError(apiErrorText("timeout"), 408);
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
    throw new ApiError(apiErrorText("sessionExpired"), 401);
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
      throw new ApiError(apiErrorText("enrollmentRequired"), 403);
    }
    const translated: Record<string, string> = {
      "Email is already registered": apiErrorText("duplicateEmail"),
      "Cannot remove the last active administrator": apiErrorText("lastAdmin"),
      "User not found": apiErrorText("unknownUser"),
      "Administrator access required": apiErrorText("adminOnly"),
      "Administrator access changed; sign in again": apiErrorText("permissionChanged"),
    };
    const fallbackByStatus: Record<number, string> = {
      403: apiErrorText("forbidden"),
      404: apiErrorText("notFound"),
      410: apiErrorText("historicalExpired"),
      422: apiErrorText("validation"),
      429: apiErrorText("tooManyRequests"),
    };
    const message = detail === "reauthentication_required"
      ? apiErrorText("reauthentication")
      : Array.isArray(detail) ? apiErrorText("validation")
      : detail === "Invalid email or password" ? apiErrorText("invalidCredentials")
      : translated[typeof detail === "string" ? detail : ""]
        || (detailText && !detailText.includes("Traceback") ? detailText : undefined)
        || (response.status >= 500
          ? apiErrorText("serverError")
          : fallbackByStatus[response.status])
        || apiErrorText("generic");
    throw new ApiError(message, response.status, detailText, detailCode);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function usd(value: number | string, locale = "pt-BR"): string {
  return formatLocaleCurrency(value, "USD", locale, {minimumFractionDigits: 2});
}

export function formatDate(value: string | null, locale = "pt-BR"): string {
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? formatLocaleDate(value, locale)
    : formatLocaleDateTime(value, locale);
}

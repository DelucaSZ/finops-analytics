import { ApiError } from "@/lib/api";

/** UI-only error classification: never expose arbitrary API details, identifiers, or secrets. */
export type AuthErrorKey =
  | "invalidCredentials" | "invalidCode" | "invalidLink" | "tooManyRequests"
  | "sessionExpired" | "accessDenied" | "requestFailed" | "timeout"
  | "networkUnavailable";
type Context = "login" | "verify" | "configure" | "access" | "logout";

export function authErrorKey(error: unknown, context: Context): AuthErrorKey {
  if (!(error instanceof ApiError)) return "networkUnavailable";
  if (error.status === 429) return "tooManyRequests";
  if (error.status === 408) return "timeout";
  if (context === "login" && error.status === 401) return "invalidCredentials";
  if (context === "verify" && error.status === 400) return "invalidCode";
  if (context === "access" && error.status === 400) return "invalidLink";
  if (error.status === 401) return "sessionExpired";
  if (error.status === 403) return "accessDenied";
  return "requestFailed";
}

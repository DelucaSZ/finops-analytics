"use client";

import { FormEvent, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { IdentityProof } from "@/components/identity-proof";
import { PageHeader } from "@/components/page-header";
import { api, ApiError, formatDate } from "@/lib/api";

type CertificateInfo = {
  fingerprint_sha256: string;
  issuer: string;
  valid_from: string;
  valid_until: string;
  san: string[];
  chain_length?: number;
};

type LocalTls = {
  healthy: boolean;
  trusted: boolean | null;
  trust_error: string | null;
  certificate: CertificateInfo | null;
  message: string;
};

type Endpoint = {
  record_type: "A" | "AAAA";
  address: string;
  status: "VERIFIED" | "PARTIAL" | "MISMATCH" | "UNREACHABLE";
  fingerprint_matches: boolean | null;
  hostname_valid: boolean;
  trusted: boolean | null;
  message: string;
};

type EndpointValidation = {
  status:
    | "VERIFIED"
    | "PARTIAL"
    | "MISMATCH"
    | "UNREACHABLE"
    | "DNS_NOT_FOUND";
  endpoints: Endpoint[];
  message: string;
};

type ChainInfo = {
  status: "VALID" | "UNANCHORED";
  provided_intermediates: number;
  served_intermediates: number;
  served_chain_length: number;
  root_omitted: boolean;
  root_subject: string | null;
  message: string;
};

type TrustInfo = {
  status:
    | "PUBLIC_TRUSTED"
    | "PRIVATE_OR_UNTRUSTED"
    | "UNTRUSTED_OR_INCOMPLETE"
    | "UNANCHORED";
  message: string;
};

type TlsStatus = {
  configured: boolean;
  mode: "http" | "automatic" | "custom";
  domain: string | null;
  healthy: boolean;
  local_tls: LocalTls;
  dns: { a: string[]; aaaa: string[] };
  endpoint_validation: EndpointValidation;
  certificate: CertificateInfo | null;
  chain: ChainInfo | null;
  trust: TrustInfo | null;
  applied_at: string | null;
  last_validated_at: string | null;
  message: string;
};

type ValidationResult = {
  valid: boolean;
  mode: "automatic" | "custom";
  domain: string;
  certificate: CertificateInfo | null;
  chain: ChainInfo | null;
  trust: TrustInfo | null;
};

function endpointLabel(status: EndpointValidation["status"]) {
  switch (status) {
    case "VERIFIED":
      return "Endpoint DNS validado";
    case "MISMATCH":
      return "Endpoint DNS divergente";
    case "PARTIAL":
      return "Validação DNS parcial";
    case "UNREACHABLE":
      return "Endpoint externo não pôde ser testado deste host";
    default:
      return "DNS A/AAAA não encontrado";
  }
}

function trustLabel(trust: TrustInfo | null) {
  if (!trust) return "Não avaliada";
  if (trust.status === "PUBLIC_TRUSTED") return "Confiável pela trust store";
  if (trust.status === "PRIVATE_OR_UNTRUSTED") return "CA privada/não pública";
  return "Confiança requer atenção";
}

export default function HttpsSettingsPage() {
  const locale = useLocale();
  const t = useTranslations("settings.https");
  const [status, setStatus] = useState<TlsStatus | null>(null);
  const [mode, setMode] = useState<"automatic" | "custom">("automatic");
  const [domain, setDomain] = useState("");
  const [serverCertificate, setServerCertificate] = useState("");
  const [intermediateChain, setIntermediateChain] = useState("");
  const [privateKey, setPrivateKey] = useState("");
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load(initial = false) {
    const next = await api<TlsStatus>("/tls");
    setStatus(next);
    if (initial && next.configured && next.domain) {
      setDomain(next.domain);
      if (next.mode === "automatic" || next.mode === "custom") {
        setMode(next.mode);
      }
    }
  }

  useEffect(() => {
    load(true).catch((err) =>
      setError(
        err instanceof Error ? err.message : t("loadError"),
      ),
    );
  }, []);

  function payload() {
    return {
      mode,
      domain,
      server_certificate: mode === "custom" ? serverCertificate : "",
      intermediate_chain: mode === "custom" ? intermediateChain : "",
      private_key: mode === "custom" ? privateKey : undefined,
    };
  }

  async function run(action: "validate" | "apply") {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      if (action === "validate") {
        const result = await api<ValidationResult>("/tls/validate", {
          method: "POST",
          body: JSON.stringify(payload()),
        });
        setValidation(result);
        setMessage(
          result.mode === "custom"
            ? t("validatedCustom")
            : t("validatedAutomatic"),
        );
      } else {
        const result = await api<TlsStatus>("/tls/apply", {
          method: "POST",
          body: JSON.stringify(payload()),
        });
        setStatus(result);
        setValidation(null);
        setServerCertificate("");
        setIntermediateChain("");
        setPrivateKey("");
        setMessage(
          t("appliedMessage"),
        );
      }
    } catch (err) {
      setValidation(null);
      if (
        err instanceof ApiError &&
        err.detail === "reauthentication_required"
      ) {
        setError(
          t("reauthRequired"),
        );
        document
          .getElementById("identity-proof")
          ?.scrollIntoView({ behavior: "smooth" });
      } else {
        setError(
          err instanceof Error
            ? err.message
            : t("operationError"),
        );
      }
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void run("apply");
  }

  return (
    <div className="https-settings-page">
      <PageHeader
        eyebrow={t("eyebrow")}
        title={t("title")}
        description={t("description")}
        actions={
          <button
            className="button"
            disabled={busy}
            onClick={() => {
              setError("");
              void load().catch((err) =>
                setError(
                  err instanceof Error
                    ? err.message
                    : t("verifyError"),
                ),
              );
            }}
          >
            {t("verifyNow")}
          </button>
        }
      />

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="form-success" role="status">
          {message}
        </p>
      )}

      <div className="security-grid">
        <section className="security-card">
          <h2>{t("currentState")}</h2>
          {!status ? (
            <p>{t("loading")}</p>
          ) : (
            <>
              <p>
                <strong>
                  {status.configured
                    ? status.local_tls.healthy
                      ? t("localValid")
                      : t("localNeedsAttention")
                    : t("httpOnly")}
                </strong>
              </p>
              <p>{status.message}</p>
              {status.domain && (
                <p>
                  Domínio: <code>{status.domain}</code>
                </p>
              )}
              {status.configured && (
                <>
                  <p>
                    Modo:{" "}
                    {status.mode === "automatic"
                      ? t("automaticMode")
                      : t("customCertificate")}
                  </p>
                  <p>
                    HTTPS local:{" "}
                    {status.local_tls.healthy
                      ? t("expectedCertificate")
                      : t("notValidated")}
                  </p>
                  <p>
                    DNS público: {status.dns.a.length + status.dns.aaaa.length} endpoint(s)
                  </p>
                  <p>
                    Validação do endpoint: {endpointLabel(status.endpoint_validation.status)}
                  </p>
                  <p>{status.endpoint_validation.message}</p>
                  <p>{t("trust")}: {trustLabel(status.trust)}</p>
                  {status.trust && <p>{status.trust.message}</p>}
                </>
              )}
              {status.applied_at && (
                <p>{t("appliedAt")}: {formatDate(status.applied_at, locale)}</p>
              )}
              {status.last_validated_at && (
                <p>{t("lastValidated")}: {formatDate(status.last_validated_at, locale)}</p>
              )}
              {status.certificate && (
                <>
                  <p>{t("issuer")}: {status.certificate.issuer}</p>
                  <p>
                    Validade: {formatDate(status.certificate.valid_from, locale)} até{" "}
                    {formatDate(status.certificate.valid_until, locale)}
                  </p>
                  <p>
                    SHA-256: <code>{status.certificate.fingerprint_sha256}</code>
                  </p>
                  <p>
                    SANs:{" "}
                    {status.certificate.san.length > 0
                      ? status.certificate.san.join(", ")
                      : "—"}
                  </p>
                  {status.certificate.chain_length !== undefined && (
                    <p>
                      Certificados servidos na cadeia: {status.certificate.chain_length}
                    </p>
                  )}
                </>
              )}
              {status.chain && <p>{t("chain")}: {status.chain.message}</p>}
              {status.dns.a.length > 0 && (
                <p>
                  A: <code>{status.dns.a.join(", ")}</code>
                </p>
              )}
              {status.dns.aaaa.length > 0 && (
                <p>
                  AAAA: <code>{status.dns.aaaa.join(", ")}</code>
                </p>
              )}
              {status.endpoint_validation.endpoints.map((endpoint) => (
                <p key={`${endpoint.record_type}-${endpoint.address}`}>
                  {endpoint.record_type} <code>{endpoint.address}</code> · {endpoint.status} ·{" "}
                  {endpoint.message}
                </p>
              ))}
            </>
          )}
        </section>

        <section className="security-card">
          <h2>{t("howItWorks")}</h2>
          <p>
            No modo automático, o Caddy solicita e renova o certificado. O
            domínio precisa apontar para este host e os desafios ACME precisam
            alcançar as portas 80/443.
          </p>
          <p>
            No modo próprio, o Aven valida separadamente o certificado do
            servidor, as CAs intermediárias e a chave privada, ordena a cadeia e
            monta o fullchain servido pelo Caddy.
          </p>
          <p>
            O probe local confirma o Caddy. A resolução A/AAAA e os endpoints
            publicados são diagnosticados separadamente; indisponibilidade do IP
            público a partir da própria EC2 não desfaz um TLS local válido.
          </p>
        </section>
      </div>

      <section className="security-card">
        <h2>{t("configure")}</h2>
        <form onSubmit={submit}>
          <div className="settings-form-grid">
            <label>
              {t("mode")}
              <select
                value={mode}
                onChange={(event) => {
                  setMode(event.target.value as "automatic" | "custom");
                  setValidation(null);
                }}
              >
                <option value="automatic">
                  {t("automaticRecommended")}
                </option>
                <option value="custom">{t("customCertificate")}</option>
              </select>
            </label>
            <label>
              {t("publicDomain")}
              <input
                inputMode="url"
                autoComplete="off"
                placeholder={t("domainPlaceholder")}
                maxLength={253}
                value={domain}
                onChange={(event) => {
                  setDomain(event.target.value);
                  setValidation(null);
                }}
                required
              />
            </label>
          </div>

          {mode === "custom" && (
            <>
              <label>
                {t("serverCertificate")}
                <textarea
                  rows={9}
                  autoComplete="off"
                  spellCheck={false}
                  value={serverCertificate}
                  onChange={(event) => {
                    setServerCertificate(event.target.value);
                    setValidation(null);
                  }}
                  placeholder={
                    "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
                  }
                  required
                />
              </label>
              <p className="settings-help">
                Cole aqui somente o certificado emitido para o domínio,
                normalmente um único bloco BEGIN CERTIFICATE.
              </p>

              <label>
                {t("intermediateChain")}
                <textarea
                  rows={9}
                  autoComplete="off"
                  spellCheck={false}
                  value={intermediateChain}
                  onChange={(event) => {
                    setIntermediateChain(event.target.value);
                    setValidation(null);
                  }}
                  placeholder={
                    "-----BEGIN CERTIFICATE-----\n... CA intermediária ...\n-----END CERTIFICATE-----"
                  }
                />
              </label>
              <p className="settings-help">
                Cole as CAs intermediárias fornecidas pela autoridade
                certificadora. O Aven valida e ordena a cadeia. O Root CA
                normalmente não deve ser enviado pelo servidor e será omitido do
                fullchain quando identificado.
              </p>

              <label>
                {t("privateKey")}
                <textarea
                  rows={9}
                  autoComplete="off"
                  spellCheck={false}
                  value={privateKey}
                  onChange={(event) => {
                    setPrivateKey(event.target.value);
                    setValidation(null);
                  }}
                  placeholder={
                    "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
                  }
                  required
                />
              </label>
              <p className="settings-help">
                A chave privada precisa corresponder ao certificado leaf e não
                pode estar protegida por senha. Ela nunca é devolvida pela API e
                o campo é limpo após uma aplicação bem-sucedida.
              </p>
            </>
          )}

          {validation?.certificate && (
            <div className="settings-help">
              <p>
                Certificado validado · emissor {validation.certificate.issuer} ·
                expira em {formatDate(validation.certificate.valid_until, locale)}
              </p>
              {validation.chain && <p>{validation.chain.message}</p>}
              {validation.trust && <p>{validation.trust.message}</p>}
            </div>
          )}

          <div className="security-actions">
            <button
              className="button"
              type="button"
              disabled={busy}
              onClick={() => void run("validate")}
            >
              {busy ? t("validating") : t("validate")}
            </button>
            <button className="button primary" disabled={busy}>
              {busy ? t("applying") : t("apply")}
            </button>
          </div>
        </form>
      </section>

      <IdentityProof />
    </div>
  );
}

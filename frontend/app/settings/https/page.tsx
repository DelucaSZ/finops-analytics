"use client";

import { FormEvent, useEffect, useState } from "react";
import { IdentityProof } from "@/components/identity-proof";
import { PageHeader } from "@/components/page-header";
import { api, ApiError, formatDate } from "@/lib/api";

type CertificateInfo = {
  fingerprint_sha256: string;
  issuer: string;
  valid_from: string;
  valid_until: string;
};

type TlsStatus = {
  configured: boolean;
  mode: "http" | "automatic" | "custom";
  domain: string | null;
  healthy: boolean;
  certificate: CertificateInfo | null;
  applied_at: string | null;
  message: string;
};

type ValidationResult = {
  valid: boolean;
  mode: "automatic" | "custom";
  domain: string;
  certificate: CertificateInfo | null;
};

export default function HttpsSettingsPage() {
  const [status, setStatus] = useState<TlsStatus | null>(null);
  const [mode, setMode] = useState<"automatic" | "custom">("automatic");
  const [domain, setDomain] = useState("");
  const [certificateChain, setCertificateChain] = useState("");
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
        err instanceof Error ? err.message : "Não foi possível carregar o HTTPS.",
      ),
    );
  }, []);

  function payload() {
    return {
      mode,
      domain,
      certificate_chain: mode === "custom" ? certificateChain : "",
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
            ? "Certificado, domínio e chave privada são compatíveis."
            : "Domínio e configuração automática são válidos.",
        );
      } else {
        const result = await api<TlsStatus>("/tls/apply", {
          method: "POST",
          body: JSON.stringify(payload()),
        });
        setStatus(result);
        setValidation(null);
        setCertificateChain("");
        setPrivateKey("");
        setMessage(
          "HTTPS aplicado e verificado. O material sensível foi removido do formulário.",
        );
      }
    } catch (err) {
      setValidation(null);
      if (
        err instanceof ApiError &&
        err.detail === "reauthentication_required"
      ) {
        setError(
          "Confirme sua identidade abaixo e repita a aplicação do HTTPS.",
        );
        document
          .getElementById("identity-proof")
          ?.scrollIntoView({ behavior: "smooth" });
      } else {
        setError(
          err instanceof Error
            ? err.message
            : "Não foi possível concluir a operação.",
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
    <>
      <PageHeader
        eyebrow="CONFIGURAÇÕES"
        title="HTTPS e certificado"
        description="Configure o domínio público e o TLS sem expor a chave privada pela aplicação."
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
                    : "Não foi possível verificar o HTTPS.",
                ),
              );
            }}
          >
            Verificar agora
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
          <h2>Estado atual</h2>
          {!status ? (
            <p>Carregando configuração…</p>
          ) : (
            <>
              <p>
                <strong>
                  {status.configured
                    ? status.healthy
                      ? "HTTPS válido"
                      : "HTTPS requer atenção"
                    : "Somente HTTP"}
                </strong>
              </p>
              <p>{status.message}</p>
              {status.domain && (
                <p>
                  Domínio: <code>{status.domain}</code>
                </p>
              )}
              {status.configured && (
                <p>
                  Modo:{" "}
                  {status.mode === "automatic"
                    ? "Automático (Caddy/ACME)"
                    : "Certificado próprio"}
                </p>
              )}
              {status.applied_at && (
                <p>Aplicado em: {formatDate(status.applied_at)}</p>
              )}
              {status.certificate && (
                <>
                  <p>Emissor: {status.certificate.issuer}</p>
                  <p>
                    Válido até: {formatDate(status.certificate.valid_until)}
                  </p>
                  <p>
                    SHA-256:{" "}
                    <code>{status.certificate.fingerprint_sha256}</code>
                  </p>
                </>
              )}
            </>
          )}
        </section>

        <section className="security-card">
          <h2>Como funciona</h2>
          <p>
            No modo automático, o Caddy solicita e renova o certificado. O
            domínio precisa apontar para este host e os desafios ACME precisam
            alcançar as portas 80/443.
          </p>
          <p>
            No modo próprio, o DeepOps valida SAN, validade e correspondência
            entre certificado e chave; depois confirma o handshake TLS antes de
            manter a nova configuração.
          </p>
          <p>
            A abertura externa do host, Security Group e testes de exposição
            continuam na etapa 6.
          </p>
        </section>
      </div>

      <section className="security-card">
        <h2>Configurar HTTPS</h2>
        <form onSubmit={submit}>
          <div className="settings-form-grid">
            <label>
              Modo
              <select
                value={mode}
                onChange={(event) => {
                  setMode(event.target.value as "automatic" | "custom");
                  setValidation(null);
                }}
              >
                <option value="automatic">
                  Certificado automático (recomendado)
                </option>
                <option value="custom">Certificado próprio</option>
              </select>
            </label>
            <label>
              Domínio público
              <input
                inputMode="url"
                autoComplete="off"
                placeholder="deepops.exemplo.com"
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
                Certificado + cadeia intermediária (PEM)
                <textarea
                  rows={9}
                  autoComplete="off"
                  spellCheck={false}
                  value={certificateChain}
                  onChange={(event) => {
                    setCertificateChain(event.target.value);
                    setValidation(null);
                  }}
                  placeholder={
                    "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
                  }
                  required
                />
              </label>
              <label>
                Chave privada (PEM)
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
                A chave é usada somente para validar e gravar o arquivo
                protegido no volume interno. Ela não é devolvida pela API e o
                campo é limpo após uma aplicação bem-sucedida.
              </p>
            </>
          )}

          {validation?.certificate && (
            <p className="settings-help">
              Certificado validado · emissor {validation.certificate.issuer} ·
              expira em {formatDate(validation.certificate.valid_until)}
            </p>
          )}

          <div className="security-actions">
            <button
              className="button"
              type="button"
              disabled={busy}
              onClick={() => void run("validate")}
            >
              {busy ? "Validando…" : "Validar configuração"}
            </button>
            <button className="button primary" disabled={busy}>
              {busy ? "Aplicando…" : "Aplicar HTTPS"}
            </button>
          </div>
        </form>
      </section>

      <IdentityProof />
    </>
  );
}

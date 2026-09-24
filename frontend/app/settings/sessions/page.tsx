"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { api, formatDate } from "@/lib/api";
type Session = {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  user_agent: string;
  current: boolean;
};
export default function SessionsPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function load() {
    setSessions(await api<Session[]>("/auth/sessions"));
    setLoaded(true);
  }
  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);
  async function action(run: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await run();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Não foi possível concluir.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="CONFIGURAÇÕES"
        title="Minhas sessões"
        description="Veja onde sua conta está conectada e encerre acessos que não reconhece."
      />
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <section className="security-card session-list">
        <h2>Sessões ativas</h2>
        <p>As informações do navegador ajudam a reconhecer seus acessos.</p>
        <div className="security-actions">
          <button
            className="button"
            disabled={busy}
            onClick={() => action(load)}
          >
            Atualizar lista
          </button>
          <button
            className="button"
            disabled={busy || !loaded}
            onClick={() =>
              action(async () => {
                await api("/auth/logout-all", { method: "POST" });
                router.replace("/login");
              })
            }
          >
            Encerrar todas, incluindo esta
          </button>
        </div>
        {!loaded && <p>Carregando sessões…</p>}
        {sessions.map((session) => (
          <article className="session-item" key={session.id}>
            <div>
              <strong>
                {session.current ? "Esta sessão" : "Outro acesso"}
              </strong>
              <p className="session-agent">
                {session.user_agent || "Navegador não identificado"}
              </p>
              <p>
                Início: {formatDate(session.created_at)} · Última atividade:{" "}
                {formatDate(session.last_seen_at)}
              </p>
              <p>Expira até: {formatDate(session.expires_at)}</p>
            </div>
            <button
              className="button"
              disabled={busy}
              onClick={() =>
                action(async () => {
                  await api(`/auth/sessions/${session.id}`, {
                    method: "DELETE",
                  });
                  if (session.current) router.replace("/login");
                  else await load();
                })
              }
            >
              {session.current ? "Sair desta sessão" : "Encerrar sessão"}
            </button>
          </article>
        ))}
      </section>
    </>
  );
}

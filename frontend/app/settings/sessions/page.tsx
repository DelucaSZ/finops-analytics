"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PageHeader, Section } from "@/components/aven";
import {
  Alert,
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableState,
} from "@/components/ui";
import { api, formatDate } from "@/lib/api";
import styles from "../settings-page.module.css";

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
    load().catch((err) => setError(err instanceof Error ? err.message : "Não foi possível carregar as sessões."));
  }, []);

  async function action(run: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await run();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível concluir.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Minhas sessões"
        description="Veja onde sua conta está conectada e encerre acessos que não reconhece."
        actions={
          <div className={styles.formActions}>
            <Button variant="outline" loading={busy} onClick={() => void action(load)}>
              Atualizar lista
            </Button>
            <Button
              variant="danger"
              disabled={!loaded}
              loading={busy}
              onClick={() => void action(async () => {
                await api("/auth/logout-all", { method: "POST" });
                router.replace("/login");
              })}
            >
              Encerrar todas, incluindo esta
            </Button>
          </div>
        }
      />

      {error && <Alert variant="danger" title="Falha ao gerenciar sessões" description={error} />}

      <Section
        title="Sessões ativas"
        description="As informações do navegador ajudam a reconhecer seus acessos."
      >
        <Table aria-label="Sessões ativas da conta">
          <TableHeader>
            <TableRow staticRow>
              <TableHead>Sessão</TableHead>
              <TableHead>Navegador</TableHead>
              <TableHead>Início</TableHead>
              <TableHead>Última atividade</TableHead>
              <TableHead>Expira até</TableHead>
              <TableHead>Ação</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!loaded ? (
              <TableRow staticRow>
                <TableState state="loading" colSpan={6}>Carregando sessões…</TableState>
              </TableRow>
            ) : sessions.length === 0 ? (
              <TableRow staticRow>
                <TableState state="empty" colSpan={6}>Nenhuma sessão ativa foi retornada.</TableState>
              </TableRow>
            ) : sessions.map((session) => (
              <TableRow key={session.id}>
                <TableCell>{session.current ? "Esta sessão" : "Outro acesso"}</TableCell>
                <TableCell>{session.user_agent || "Navegador não identificado"}</TableCell>
                <TableCell>{formatDate(session.created_at)}</TableCell>
                <TableCell>{formatDate(session.last_seen_at)}</TableCell>
                <TableCell>{formatDate(session.expires_at)}</TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    variant={session.current ? "danger" : "outline"}
                    loading={busy}
                    onClick={() => void action(async () => {
                      await api(`/auth/sessions/${session.id}`, { method: "DELETE" });
                      if (session.current) router.replace("/login");
                      else await load();
                    })}
                  >
                    {session.current ? "Sair desta sessão" : "Encerrar sessão"}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>
    </>
  );
}

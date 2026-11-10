"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
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
  const locale = useLocale();
  const t = useTranslations("settings.sessions");
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
    load().catch((err) => setError(err instanceof Error ? err.message : "ERR_SESSIONS_LOAD"));
  }, []);

  async function action(run: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await run();
    } catch (err) {
      setError(err instanceof Error ? err.message : "ERR_SESSIONS_ACTION");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={
          <div className={styles.formActions}>
            <Button variant="outline" loading={busy} onClick={() => void action(load)}>
              {t("refresh")}
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
              {t("logoutAll")}
            </Button>
          </div>
        }
      />

      {error && <Alert variant="danger" title={t("errorTitle")} description={error === "ERR_SESSIONS_LOAD" ? t("loadFailed") : error === "ERR_SESSIONS_ACTION" ? t("actionFailed") : error} />}

      <Section
        title={t("activeTitle")}
        description={t("activeDescription")}
      >
        <Table aria-label={t("tableLabel")}>
          <TableHeader>
            <TableRow staticRow>
              <TableHead>{t("column.session")}</TableHead>
              <TableHead>{t("column.browser")}</TableHead>
              <TableHead>{t("column.start")}</TableHead>
              <TableHead>{t("column.lastActivity")}</TableHead>
              <TableHead>{t("column.expires")}</TableHead>
              <TableHead>{t("column.action")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!loaded ? (
              <TableRow staticRow>
                <TableState state="loading" colSpan={6}>{t("loading")}</TableState>
              </TableRow>
            ) : sessions.length === 0 ? (
              <TableRow staticRow>
                <TableState state="empty" colSpan={6}>{t("empty")}</TableState>
              </TableRow>
            ) : sessions.map((session) => (
              <TableRow key={session.id}>
                <TableCell>{session.current ? t("current") : t("other")}</TableCell>
                <TableCell>{session.user_agent || t("unknownBrowser")}</TableCell>
                <TableCell>{formatDate(session.created_at, locale)}</TableCell>
                <TableCell>{formatDate(session.last_seen_at, locale)}</TableCell>
                <TableCell>{formatDate(session.expires_at, locale)}</TableCell>
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
                    {session.current ? t("logoutCurrent") : t("revoke")}
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

"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { PageContainer, PageHeader } from "@/components/aven";
import { Alert, Button, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui";
import { api } from "@/lib/api";
import {
  isAdminOnlySettingsPath,
  isSettingsTabActive,
  settingsTabsForRole,
} from "@/lib/settings-navigation.mjs";
import styles from "./settings-layout.module.css";

type CurrentUser = { role: string };

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const navigationViewportRef = useRef<HTMLDivElement | null>(null);
  const [role, setRole] = useState("");
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let active = true;
    setError("");
    api<CurrentUser>("/auth/me")
      .then((user) => {
        if (active) setRole(user.role);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Não foi possível carregar as permissões de Configurações.");
      });
    return () => {
      active = false;
    };
  }, [retry]);

  const tabs = useMemo(() => settingsTabsForRole(role), [role]);
  const activeTab = useMemo(
    () => tabs.find((tab) => isSettingsTabActive(path, tab.href))?.href ?? tabs[0]?.href ?? path,
    [path, tabs],
  );

  useEffect(() => {
    const activeTabElement = navigationViewportRef.current?.querySelector<HTMLElement>(
      '[role="tab"][aria-selected="true"]',
    );
    activeTabElement?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [activeTab]);

  if (error) {
    return (
      <PageContainer width="full" className={styles.statePage}>
        <PageHeader
          title="Configurações"
          description="Gerencie as configurações disponíveis da plataforma."
        />
        <Alert
          variant="danger"
          title="Não foi possível carregar Configurações"
          description={error}
          actions={
            <Button variant="outline" onClick={() => setRetry((value) => value + 1)}>
              Tentar novamente
            </Button>
          }
        />
      </PageContainer>
    );
  }

  if (!role) {
    return (
      <PageContainer
        width="full"
        className={styles.statePage}
        aria-busy="true"
        aria-label="Carregando configurações"
      >
        <Skeleton className={styles.headerSkeleton} />
        <Skeleton className={styles.navigationSkeleton} />
        <Skeleton className={styles.contentSkeleton} />
      </PageContainer>
    );
  }

  const adminOnly = isAdminOnlySettingsPath(path);

  return (
    <PageContainer width="full" className={styles.page}>
      <Tabs
        value={activeTab}
        defaultValue={activeTab}
        onValueChange={(href) => {
          if (href !== path) router.push(href);
        }}
      >
        <div ref={navigationViewportRef} className={styles.navigationViewport}>
          <TabsList className={styles.tabs} aria-label="Áreas de Configurações">
            {tabs.map((tab) => (
              <TabsTrigger key={tab.href} value={tab.href}>
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <TabsContent value={activeTab} className={styles.content}>
          {adminOnly && role !== "admin" ? (
            <Alert
              variant="warning"
              title="Acesso restrito"
              description="Esta área está disponível apenas para administradores."
            />
          ) : (
            children
          )}
        </TabsContent>
      </Tabs>
    </PageContainer>
  );
}

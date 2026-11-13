"use client";

import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
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
  const t = useTranslations("settings");
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
        if (active) setError(err instanceof Error ? err.message : "ERR_SETTINGS_PERMISSIONS");
      });
    return () => {
      active = false;
    };
  }, [retry]);

  const navigationLabels: Record<string, string> = {
    appearance: t("navigation.appearance"),
    accounts: t("navigation.accounts"),
    policies: t("navigation.policies"),
    security: t("navigation.security"),
    sessions: t("navigation.sessions"),
    users: t("navigation.users"),
    audit: t("navigation.audit"),
    https: t("navigation.https"),
    pricing: t("navigation.pricing"),
    pricingAws: t("navigation.pricingAws"),
    billingProfiles: t("navigation.billingProfiles"),
    usageCosts: t("navigation.usageCosts"),
    retention: t("navigation.retention"),
  };
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
          title={t("title")}
          description={t("description")}
        />
        <Alert
          variant="danger"
          title={t("errors.loading")}
          description={error === "ERR_SETTINGS_PERMISSIONS" ? t("errors.permissions") : error}
          actions={
            <Button variant="outline" onClick={() => setRetry((value) => value + 1)}>
              {t("retry")}
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
        aria-label={t("loading")}
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
          <TabsList className={styles.tabs} aria-label={t("navigation.ariaLabel")}>
            {tabs.map((tab) => (
              <TabsTrigger key={tab.href} value={tab.href}>
                {navigationLabels[tab.labelKey] ?? tab.labelKey}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <TabsContent value={activeTab} className={styles.content}>
          {adminOnly && role !== "admin" ? (
            <Alert
              variant="warning"
              title={t("restricted.title")}
              description={t("restricted.description")}
            />
          ) : (
            children
          )}
        </TabsContent>
      </Tabs>
    </PageContainer>
  );
}

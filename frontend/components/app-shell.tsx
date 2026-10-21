"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Activity,
  ChevronLeft,
  ChevronRight,
  CloudCog,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  ReceiptText,
  ScanSearch,
  Settings2,
  WalletCards,
  X,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { clearApiQueryCache } from "@/lib/server-state";
import {
  normalizeThemePreference,
  parseSidebarCollapsed,
  resolveThemePreference,
  serializeSidebarCollapsed,
  SIDEBAR_STORAGE_KEY,
  THEME_STORAGE_KEY,
} from "@/lib/ui-preferences.mjs";

const nav = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/opportunities", label: "Oportunidades", icon: ScanSearch, exact: true },
  { href: "/opportunities/history-cycles", label: "Histórico", icon: History },
  { href: "/flow", label: "Fluxo", icon: WalletCards },
  { href: "/billing", label: "Billing", icon: ReceiptText },
  { href: "/collections", label: "Coletas", icon: Activity },
  { href: "/settings", label: "Configurações", icon: Settings2 },
];

const publicRoutes = [
  "/mfa-setup",
  "/login",
  "/forgot-password",
  "/reset-password",
  "/accept-invitation",
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [leaving, setLeaving] = useState(false);
  const [retry, setRetry] = useState(0);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const isPublic = publicRoutes.includes(pathname);

  useEffect(() => {
    const root = document.documentElement;
    const media = window.matchMedia("(prefers-color-scheme: dark)");

    const applyTheme = () => {
      let saved: string | null = null;
      try {
        saved = window.localStorage.getItem(THEME_STORAGE_KEY);
      } catch {
        saved = null;
      }
      const preference = normalizeThemePreference(saved);
      const resolved = resolveThemePreference(preference, media.matches);
      root.dataset.themePreference = preference;
      root.dataset.theme = resolved;
      root.style.colorScheme = resolved;
    };

    applyTheme();
    media.addEventListener("change", applyTheme);
    window.addEventListener("storage", applyTheme);
    window.addEventListener("deepops:theme-change", applyTheme);
    return () => {
      media.removeEventListener("change", applyTheme);
      window.removeEventListener("storage", applyTheme);
      window.removeEventListener("deepops:theme-change", applyTheme);
    };
  }, []);

  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    } catch {
      saved = null;
    }
    const next = parseSidebarCollapsed(saved);
    setCollapsed(next);
    document.documentElement.dataset.sidebar = next ? "collapsed" : "expanded";
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  useEffect(() => {
    const clearPrivateCache = () => clearApiQueryCache();
    window.addEventListener("deepops:session-invalidated", clearPrivateCache);
    return () => window.removeEventListener("deepops:session-invalidated", clearPrivateCache);
  }, []);

  useEffect(() => {
    let active = true;
    window.localStorage.removeItem("nuvemiq_token");
    setReady(false);
    setError("");
    if (isPublic) {
      clearApiQueryCache();
      setReady(true);
      return;
    }
    api("/auth/me", {}, false).then(() => {
      if (active) setReady(true);
    }).catch((err) => {
      if (!active) return;
      if (err instanceof ApiError && err.status === 401) {
        clearApiQueryCache();
        router.replace("/login");
      } else {
        setError("Não foi possível verificar sua sessão. Tente novamente.");
      }
    });
    return () => {
      active = false;
    };
  }, [isPublic, router, retry]);

  function toggleSidebar() {
    const next = !collapsed;
    setCollapsed(next);
    document.documentElement.dataset.sidebar = next ? "collapsed" : "expanded";
    try {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, serializeSidebarCollapsed(next));
    } catch {
      // A navegação continua funcional mesmo sem persistência local.
    }
  }

  if (error && !ready) {
    return (
      <main className="boot-screen">
        <p role="alert">{error}</p>
        <button className="button" onClick={() => setRetry((value) => value + 1)}>
          Tentar novamente
        </button>
      </main>
    );
  }
  if (!ready) return <div className="boot-screen">Verificando acesso…</div>;
  if (isPublic) return <>{children}</>;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Pular para o conteúdo</a>
      <aside
        id="deepops-sidebar"
        className={`sidebar${mobileOpen ? " mobile-open" : ""}`}
        aria-label="Navegação do DeepOps"
      >
        <div className="brand-row">
          <Link className="brand" href="/" aria-label="DeepOps — Dashboard">
            <span className="brand-mark"><CloudCog size={21} /></span>
            <span className="brand-label"><strong>Deep</strong>Ops</span>
          </Link>
          <button
            className="sidebar-collapse-toggle"
            type="button"
            onClick={toggleSidebar}
            aria-label={collapsed ? "Expandir navegação" : "Recolher navegação"}
            aria-expanded={!collapsed}
            aria-controls="deepops-sidebar"
            title={collapsed ? "Expandir navegação" : "Recolher navegação"}
          >
            {collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}
          </button>
        </div>
        <div className="product-tag">FINOPS MULTI-CLOUD</div>
        <nav className="main-nav" aria-label="Navegação principal">
          {nav.map((item) => {
            const Icon = item.icon;
            const active = item.href === "/"
              ? pathname === "/"
              : item.exact
                ? pathname === item.href
                : pathname.startsWith(item.href);
            return (
              <Link
                className={active ? "nav-item active" : "nav-item"}
                href={item.href}
                key={item.href}
                aria-label={item.label}
                aria-current={active ? "page" : undefined}
                onClick={() => setMobileOpen(false)}
              >
                <Icon size={18} aria-hidden="true" />
                <span className="nav-label">{item.label}</span>
                <span className="sidebar-tooltip" role="tooltip" aria-hidden="true">{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <button
            className="nav-item logout"
            aria-label="Sair"
            title="Sair"
            disabled={leaving}
            onClick={async () => {
              setLeaving(true);
              setError("");
              try {
                await api("/auth/logout", { method: "POST" });
                clearApiQueryCache();
                router.replace("/login");
              } catch (err) {
                setError(err instanceof Error ? err.message : "Não foi possível sair.");
              } finally {
                setLeaving(false);
              }
            }}
          >
            <LogOut size={18} aria-hidden="true" />
            <span className="nav-label">{leaving ? "Saindo…" : "Sair"}</span>
            <span className="sidebar-tooltip" role="tooltip" aria-hidden="true">Sair</span>
          </button>
        </div>
      </aside>

      <button
        className={`sidebar-overlay${mobileOpen ? " visible" : ""}`}
        aria-label="Fechar navegação"
        type="button"
        tabIndex={mobileOpen ? 0 : -1}
        onClick={() => setMobileOpen(false)}
      />

      <main id="main-content" tabIndex={-1} className="main-content">
        <div className="mobile-topbar">
          <button
            className="mobile-nav-toggle"
            type="button"
            onClick={() => setMobileOpen((open) => !open)}
            aria-label={mobileOpen ? "Fechar navegação" : "Abrir navegação"}
            aria-expanded={mobileOpen}
            aria-controls="deepops-sidebar"
          >
            {mobileOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <Link className="mobile-brand" href="/" aria-label="DeepOps — Dashboard">
            <CloudCog size={18} aria-hidden="true" />
            <strong>DeepOps</strong>
          </Link>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        {children}
      </main>
    </div>
  );
}

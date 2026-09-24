"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Activity,
  Building2,
  CloudCog,
  LayoutDashboard,
  LogOut,
  ScanSearch,
  Settings2,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";

const nav = [
  { href: "/", label: "Visão geral", icon: LayoutDashboard },
  { href: "/opportunities", label: "Oportunidades", icon: ScanSearch },
  { href: "/accounts", label: "Contas AWS", icon: Building2 },
  { href: "/policies", label: "Políticas", icon: Settings2 },
  { href: "/scans", label: "Execuções", icon: Activity },
  { href: "/security", label: "Minha segurança", icon: Settings2 },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [leaving, setLeaving] = useState(false);
  const [retry, setRetry] = useState(0);
  const isPublic = ["/mfa-setup", "/login", "/forgot-password", "/reset-password", "/accept-invitation"].includes(pathname);

  useEffect(() => {
    let active = true;
    window.localStorage.removeItem("nuvemiq_token");
    setReady(false);
    setError("");
    if (isPublic) { setReady(true); return; }
    api("/auth/me", {}, false).then(() => { if (active) setReady(true); }).catch((err) => {
      if (!active) return;
      if (err instanceof ApiError && err.status === 401) router.replace("/login");
      else setError("Não foi possível verificar sua sessão. Tente novamente.");
    });
    return () => { active = false; };
  }, [isPublic, pathname, router, retry]);

  if (error && !ready) return <main className="boot-screen"><p role="alert">{error}</p><button className="button" onClick={() => setRetry((value) => value + 1)}>Tentar novamente</button></main>;
  if (!ready) return <div className="boot-screen">Verificando acesso…</div>;
  if (isPublic) return <>{children}</>;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Pular para o conteúdo</a>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark"><CloudCog size={23} /></span>
          <span><strong>Deep</strong>Ops</span>
        </div>
        <div className="product-tag">FINOPS INTELLIGENCE</div>
        <nav className="main-nav" aria-label="Navegação principal">
          {nav.map((item) => {
            const Icon = item.icon;
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link className={active ? "nav-item active" : "nav-item"} href={item.href} key={item.href} title={item.label} aria-label={item.label} aria-current={active ? "page" : undefined}>
                <Icon size={18} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <div className="environment-pill"><span /> Ambiente protegido</div>
          <button
            className="nav-item logout"
            aria-label="Sair" title="Sair"
            disabled={leaving}
            onClick={async () => {
              setLeaving(true);
              setError("");
              try { await api("/auth/logout", { method: "POST" }); router.replace("/login"); }
              catch (err) { setError(err instanceof Error ? err.message : "Não foi possível sair."); }
              finally { setLeaving(false); }
            }}
          >
            <LogOut size={18} /> <span>{leaving ? "Saindo…" : "Sair"}</span>
          </button>
        </div>
      </aside>
      <main id="main-content" tabIndex={-1} className="main-content">{error && <p className="form-error" role="alert">{error}</p>}{children}</main>
    </div>
  );
}

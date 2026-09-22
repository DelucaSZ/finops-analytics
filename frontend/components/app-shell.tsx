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
import { clearToken, getToken } from "@/lib/api";

const nav = [
  { href: "/", label: "Visão geral", icon: LayoutDashboard },
  { href: "/opportunities", label: "Oportunidades", icon: ScanSearch },
  { href: "/accounts", label: "Contas AWS", icon: Building2 },
  { href: "/policies", label: "Políticas", icon: Settings2 },
  { href: "/scans", label: "Execuções", icon: Activity },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const isLogin = pathname === "/login";

  useEffect(() => {
    const token = getToken();
    if (!token && !isLogin) router.replace("/login");
    if (token && isLogin) router.replace("/");
    setReady(true);
  }, [isLogin, router]);

  if (!ready) return <div className="boot-screen">Inicializando NuvemIQ…</div>;
  if (isLogin) return <>{children}</>;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark"><CloudCog size={23} /></span>
          <span><strong>Nuvem</strong>IQ</span>
        </div>
        <div className="product-tag">FINOPS INTELLIGENCE</div>
        <nav className="main-nav">
          {nav.map((item) => {
            const Icon = item.icon;
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link className={active ? "nav-item active" : "nav-item"} href={item.href} key={item.href}>
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
            onClick={() => {
              clearToken();
              router.push("/login");
            }}
          >
            <LogOut size={18} /> Sair
          </button>
        </div>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  );
}

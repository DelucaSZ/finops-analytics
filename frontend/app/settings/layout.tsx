"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const path = usePathname();
  const [role, setRole] = useState("");
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setRole("");
    setError("");
    api<{ role: string }>("/auth/me")
      .then((user) => {
        if (active) setRole(user.role);
      })
      .catch((err) => {
        if (active) setError(err.message);
      });
    return () => {
      active = false;
    };
  }, [path, retry]);
  if (error)
    return (
      <section className="security-card">
        <p role="alert">{error}</p>
        <button className="button" onClick={() => setRetry((n) => n + 1)}>
          Tentar novamente
        </button>
      </section>
    );
  if (!role) return <p role="status">Carregando configurações…</p>;
  const tabs = [
    { href: "/settings/security", label: "Minha segurança" },
    { href: "/settings/sessions", label: "Sessões" },
    ...(role === "admin"
      ? [
          { href: "/settings/users", label: "Usuários" },
          { href: "/settings/audit", label: "Auditoria" },
          { href: "/settings/https", label: "HTTPS" },
        ]
      : []),
  ];
  const adminOnly = ["/settings/users", "/settings/audit", "/settings/https"].some(
    (prefix) => path.startsWith(prefix),
  );
  return (
    <>
      <nav className="settings-tabs" aria-label="Configurações">
        {tabs.map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={path === tab.href ? "page" : undefined}
          >
            {tab.label}
          </Link>
        ))}
      </nav>
      {adminOnly && role !== "admin" ? (
        <section className="security-card">
          <h1>Acesso restrito</h1>
          <p>Esta área está disponível apenas para administradores.</p>
        </section>
      ) : (
        children
      )}
    </>
  );
}

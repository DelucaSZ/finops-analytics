import type { Metadata } from "next";
import { AppShell } from "@/components/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "DeepOps | FinOps Intelligence",
  description: "Eficiência e inteligência de custos para ambientes AWS",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}

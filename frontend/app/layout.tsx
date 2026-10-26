import type { Metadata } from "next";
import { AppShell } from "@/components/app-shell";
import { ThemeProvider } from "@/components/theme-provider";
import {
  getThemeBootstrapScript,
  SIDEBAR_STORAGE_KEY,
} from "@/lib/ui-preferences.mjs";
import "./globals.css";
import "./opportunities-stage5.css";
import "./styles/tokens/index.css";
import "./ui-system.css";
import "./legacy-theme-compat.css";
import "./dashboard-executive.css";
import "./dashboard-operational-insights.css";
import "./task-23-25-layout.css";

export const metadata: Metadata = {
  title: "DeepOps | FinOps Multi-Cloud",
  description: "Operação, governança e inteligência FinOps para ambientes multi-cloud.",
};

const sidebarBootstrap = `
(() => {
  const root = document.documentElement;
  let collapsed = false;
  try { collapsed = window.localStorage.getItem(${JSON.stringify(SIDEBAR_STORAGE_KEY)}) === "true"; } catch {}
  root.dataset.sidebar = collapsed ? "collapsed" : "expanded";
})();
`;

const appearanceBootstrap = `${getThemeBootstrapScript()}${sidebarBootstrap}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: appearanceBootstrap }} />
      </head>
      <body>
        <ThemeProvider>
          <AppShell>{children}</AppShell>
        </ThemeProvider>
      </body>
    </html>
  );
}

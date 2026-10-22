import type { Metadata } from "next";
import { Suspense } from "react";
import { AppShell } from "@/components/app-shell";
import { OpportunityComparisonContext } from "@/components/opportunity-comparison-context";
import "./globals.css";
import "./opportunities-stage5.css";
import "./ui-system.css";
import "./legacy-theme-compat.css";
import "./dashboard-executive.css";
import "./dashboard-operational-insights.css";

export const metadata: Metadata = {
  title: "DeepOps | FinOps Multi-Cloud",
  description: "Operação, governança e inteligência FinOps para ambientes multi-cloud.",
};

const appearanceBootstrap = `
(() => {
  const root = document.documentElement;
  let preference = "system";
  try {
    const stored = window.localStorage.getItem("deepops.theme");
    if (stored === "light" || stored === "dark" || stored === "system") preference = stored;
  } catch {}
  const systemDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const resolved = preference === "system" ? (systemDark ? "dark" : "light") : preference;
  root.dataset.themePreference = preference;
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;

  let collapsed = false;
  try { collapsed = window.localStorage.getItem("deepops.sidebar.collapsed") === "true"; } catch {}
  root.dataset.sidebar = collapsed ? "collapsed" : "expanded";
})();
`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: appearanceBootstrap }} />
      </head>
      <body>
        <AppShell>
          <Suspense fallback={null}>
            <OpportunityComparisonContext />
          </Suspense>
          {children}
        </AppShell>
      </body>
    </html>
  );
}

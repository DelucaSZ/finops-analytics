import type { Metadata } from "next";
import { Inter, Sora } from "next/font/google";
import { AppShell } from "@/components/app-shell";
import { ThemeProvider } from "@/components/theme-provider";
import { ToastProvider } from "@/components/ui/toast";
import { brand, PRODUCT_NAME } from "@/lib/brand";
import {
  getThemeBootstrapScript,
  SIDEBAR_STORAGE_KEY,
} from "@/lib/ui-preferences.mjs";
import "./globals.css";
import "./opportunities-stage5.css";
import "./styles/tokens/index.css";
import "./ui-system.css";
import "./legacy-theme-compat.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--aven-font-inter",
});

const sora = Sora({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--aven-font-sora",
});

export const metadata: Metadata = {
  applicationName: PRODUCT_NAME,
  title: {
    default: PRODUCT_NAME,
    template: `%s — ${PRODUCT_NAME}`,
  },
  description: brand.description,
  icons: {
    icon: [{ url: brand.assets.symbolGradient, type: "image/svg+xml" }],
  },
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
    <html
      lang="pt-BR"
      className={`${inter.variable} ${sora.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: appearanceBootstrap }} />
      </head>
      <body>
        <ThemeProvider>
          <ToastProvider>
            <AppShell>{children}</AppShell>
          </ToastProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

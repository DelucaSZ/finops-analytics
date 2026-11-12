import type { Metadata } from "next";
import { getLocale, getMessages } from "next-intl/server";
import { LocaleProvider } from "@/components/locale-provider";
import "@fontsource-variable/inter/wght.css";
import "@fontsource-variable/sora/wght.css";
import { AppShell } from "@/components/app-shell";
import { AvenAmbientBackground } from "@/components/aven/ambient-background";
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
import "./surface-hierarchy.css";
import "./layout-system.css";

export const metadata: Metadata = {
  applicationName: PRODUCT_NAME,
  title: {
    default: PRODUCT_NAME,
    template: `%s — ${PRODUCT_NAME}`,
  },
  description: brand.description,
  icons: {
    icon: [{ url: brand.assets.icons.favicon }],
    shortcut: [brand.assets.icons.favicon],
    apple: [{ url: brand.assets.icons.appleTouch, type: "image/png", sizes: "180x180" }],
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

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html
      lang={locale}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: appearanceBootstrap }} />
      </head>
      <body>
        <LocaleProvider locale={locale} messages={messages}>
          <ThemeProvider>
          <AvenAmbientBackground>
            <ToastProvider>
              <AppShell>{children}</AppShell>
            </ToastProvider>
          </AvenAmbientBackground>
          </ThemeProvider>
        </LocaleProvider>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import { Inter, Sora } from "next/font/google";
import { AppShell } from "@/components/app-shell";
import { ThemeProvider } from "@/components/theme-provider";
import { ToastProvider } from "@/components/ui";
import { brand, PRODUCT_NAME } from "@/lib/brand";
import { getThemeBootstrapScript } from "@/lib/ui-preferences.mjs";
import "./styles/tokens/index.css";
import "./globals.css";
import "./opportunities-stage5.css";
import "./ui-system.css";
import "./legacy-theme-compat.css";
import "./dashboard-executive.css";
import "./dashboard-operational-insights.css";
import "./task-23-25-layout.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

const sora = Sora({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sora",
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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning className={`${inter.variable} ${sora.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: getThemeBootstrapScript() }} />
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

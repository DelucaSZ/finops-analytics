import createNextIntlPlugin from "next-intl/plugin";
import { legacySettingsRedirects } from "./lib/settings-navigation.mjs";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async redirects() {
    return legacySettingsRedirects;
  },
  async headers() {
    return ["/login", "/forgot-password", "/reset-password", "/accept-invitation", "/security"].map((source) => ({
      source, headers: [{ key: "Referrer-Policy", value: "no-referrer" }, { key: "Cache-Control", value: "no-store" }],
    }));
  },
};

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

export default withNextIntl(nextConfig);

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

export default nextConfig;

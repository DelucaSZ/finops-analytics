const commonSettingsTabs = [
  { href: "/settings/appearance", labelKey: "appearance" },
  { href: "/settings/accounts", labelKey: "accounts" },
  { href: "/settings/policies", labelKey: "policies" },
  { href: "/settings/security", labelKey: "security" },
  { href: "/settings/sessions", labelKey: "sessions" },
];

const adminSettingsTabs = [
  { href: "/settings/users", labelKey: "users" },
  { href: "/settings/audit", labelKey: "audit" },
  { href: "/settings/https", labelKey: "https" },
  { href: "/settings/pricing/oci", labelKey: "pricing" },
  { href: "/settings/billing/profiles", labelKey: "billingProfiles" },
  { href: "/settings/usage-costs", labelKey: "usageCosts" },
  { href: "/settings/opportunities", labelKey: "retention" },
];

export const legacySettingsRedirects = [
  { source: "/accounts/:path*", destination: "/settings/accounts/:path*", permanent: false },
  { source: "/policies/:path*", destination: "/settings/policies/:path*", permanent: false },
];

export function settingsTabsForRole(role) {
  return role === "admin" ? [...commonSettingsTabs, ...adminSettingsTabs] : commonSettingsTabs;
}

export function isSettingsTabActive(pathname, href) {
  return pathname === href || pathname.startsWith(href + "/");
}

export function isAdminOnlySettingsPath(pathname) {
  return adminSettingsTabs.some((tab) => isSettingsTabActive(pathname, tab.href));
}

export function canManageCloudAccounts(role) {
  return role === "admin";
}

export function canRunCloudAnalysis(role) {
  return role === "admin" || role === "operator";
}

export function canManagePolicies(role) {
  return role === "admin";
}

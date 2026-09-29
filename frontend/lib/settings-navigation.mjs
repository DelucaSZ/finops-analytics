const commonSettingsTabs = [
  { href: "/settings/accounts", label: "Contas" },
  { href: "/settings/policies", label: "Políticas" },
  { href: "/settings/security", label: "Minha segurança" },
  { href: "/settings/sessions", label: "Sessões" },
];

const adminSettingsTabs = [
  { href: "/settings/users", label: "Usuários" },
  { href: "/settings/audit", label: "Auditoria" },
  { href: "/settings/https", label: "HTTPS" },
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

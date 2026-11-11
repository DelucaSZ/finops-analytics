// Inventory reconciled with docs/i18n/25.9-test-matrix.md (33 page.tsx routes).
// A navigation result must never be inferred from an authentication redirect.
export const PROTECTED_ROUTES = [
  '/', '/billing', '/inventory', '/flow', '/opportunities',
  '/opportunities/history-cycles', '/opportunities/collection/qa-collection',
  '/rds/reservations', '/collections', '/collections/qa-collection',
  '/collections/qa-collection/compare', '/scans',
  '/settings/accounts', '/settings/appearance', '/settings/audit',
  '/settings/billing/profiles', '/settings/https', '/settings/opportunities',
  '/settings/policies', '/settings/pricing/oci', '/settings/security',
  '/settings/sessions', '/settings/usage-costs', '/settings/users'
];
export const PUBLIC_ROUTES = [
  '/login', '/forgot-password', '/reset-password', '/accept-invitation', '/mfa-setup'
];
export const TECHNICAL_ROUTES = ['/settings', '/security', '/finops/ledger', '/dev/ui'];
export const INVENTORIED_COUNT = 33;
if (new Set([...PROTECTED_ROUTES,...PUBLIC_ROUTES,...TECHNICAL_ROUTES]).size !== INVENTORIED_COUNT) {
  throw new Error('i18n route inventory has duplicates or missing entries');
}

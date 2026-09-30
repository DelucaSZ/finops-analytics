import test from "node:test";
import assert from "node:assert/strict";
import { formatAccountLabel, formatMoney, formatNumber, providerLabel } from "../lib/cloud.mjs";
import {
  buildOpportunityApiQuery,
  parseOpportunitySearchParams,
} from "../lib/opportunity-query.mjs";

test("provider labels are centralized without enabling providers in the UI by themselves", () => {
  assert.equal(providerLabel("aws"), "AWS");
  assert.equal(providerLabel("oci"), "OCI");
  assert.equal(providerLabel("azure"), "Azure");
  assert.equal(providerLabel("gcp"), "GCP");
  assert.equal(providerLabel("custom-cloud"), "CUSTOM-CLOUD");
});

test("opportunity filters preserve provider-native account ids, regions and resource types", () => {
  const state = parseOpportunitySearchParams(
    "provider=oci&account_id=ocid1.tenancy.example&region=sa-saopaulo-1&service=Compute&resource_type=Compute%20Instance",
  );
  assert.equal(state.accountId, "ocid1.tenancy.example");
  assert.equal(state.region, "sa-saopaulo-1");
  assert.equal(state.service, "Compute");
  assert.equal(state.resourceType, "Compute Instance");

  const query = new URLSearchParams(buildOpportunityApiQuery(state));
  assert.equal(query.get("provider"), "oci");
  assert.equal(query.get("account_id"), "ocid1.tenancy.example");
  assert.equal(query.get("region"), "sa-saopaulo-1");
  assert.equal(query.get("service"), "Compute");
  assert.equal(query.get("resource_type"), "Compute Instance");
});

test("money formatter is currency-aware", () => {
  assert.match(formatMoney(10, "USD"), /10/);
  assert.match(formatMoney(10, "BRL"), /10/);
});

test("opportunity workspace no longer depends on the AWS account settings endpoint", async () => {
  const { readFile } = await import("node:fs/promises");
  const page = await readFile(
    new URL("../app/opportunities/page.tsx", import.meta.url),
    "utf8",
  );
  const detail = await readFile(
    new URL("../components/opportunity-detail.tsx", import.meta.url),
    "utf8",
  );

  assert.match(page, /\/opportunities\/options/);
  assert.doesNotMatch(page, /api<AwsAccount\[]>\("\/accounts"/);
  assert.doesNotMatch(page, /aws_account_id/);
  assert.match(page, /resource_type/);
  assert.match(detail, /provider_metadata/);
  assert.match(detail, /resource_type/);
});


test("shared presentation helpers keep account and numeric formatting consistent", () => {
  assert.equal(formatAccountLabel("Produção ERP", "123456789012"), "Produção ERP · 123456789012");
  assert.equal(formatAccountLabel(null, "ocid1.tenancy.example"), "ocid1.tenancy.example");
  assert.equal(formatNumber(9999), new Intl.NumberFormat("pt-BR").format(9999));
});

test("stage 15 navigation removes the legacy executions duplicate and status badge normalizes API enums", async () => {
  const { readFile } = await import("node:fs/promises");
  const shell = await readFile(
    new URL("../components/app-shell.tsx", import.meta.url),
    "utf8",
  );
  const badge = await readFile(
    new URL("../components/status-badge.tsx", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(shell, /href: "\/scans"/);
  assert.match(badge, /toLowerCase\(\)/);
  assert.match(badge, /success: "Concluída"/);
});


test("stage 17 settings uses the common account registry and keeps AWS legacy ids explicit", async () => {
  const { readFile } = await import("node:fs/promises");
  const accounts = await readFile(
    new URL("../app/settings/accounts/page.tsx", import.meta.url),
    "utf8",
  );
  const policies = await readFile(
    new URL("../app/settings/policies/page.tsx", import.meta.url),
    "utf8",
  );

  assert.match(accounts, /\/cloud-accounts/);
  assert.match(accounts, /native_account_id/);
  assert.match(accounts, /aws_configuration\?\.id/);
  assert.doesNotMatch(accounts, /api<AwsAccount\[]>\("\/accounts"/);
  assert.match(policies, /\/cloud-accounts/);
  assert.match(policies, /aws_configuration\.id/);
});


test("stage 18/19 presents OCI connection state without enabling AWS scan actions", async () => {
  const { readFile } = await import("node:fs/promises");
  const accounts = await readFile(
    new URL("../app/settings/accounts/page.tsx", import.meta.url),
    "utf8",
  );
  const types = await readFile(
    new URL("../lib/types.ts", import.meta.url),
    "utf8",
  );

  assert.match(accounts, /oci_configuration/);
  assert.match(accounts, /hasOperationalConnection/);
  assert.match(accounts, /canAnalyze && account\.aws_configuration/);
  assert.match(accounts, /Coleta OCI ainda não implementada/);
  assert.match(types, /credentials_configured: boolean/);
  assert.doesNotMatch(types, /private_key_pem/);
  assert.doesNotMatch(types, /private_key_ciphertext/);
});

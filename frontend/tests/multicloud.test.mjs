import test from "node:test";
import assert from "node:assert/strict";
import { formatMoney, providerLabel } from "../lib/cloud.mjs";
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

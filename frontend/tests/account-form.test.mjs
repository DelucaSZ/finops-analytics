import assert from "node:assert/strict";
import test from "node:test";

import {
  accountToForm,
  buildCreateAccountPayload,
  buildUpdateAccountPayload,
  createEmptyAccountForm,
  filterCloudAccounts,
  validateAccountForm,
} from "../lib/account-form.mjs";

const awsAccount = {
  id: 1,
  provider: "aws",
  native_account_id: "123456789012",
  name: "AWS Prod",
  enabled: true,
  connection_status: "connected",
  last_connection_test_at: null,
  last_error: null,
  schedule_enabled: false,
  scan_interval_hours: 24,
  next_scan_at: null,
  created_at: "",
  updated_at: "",
  oci_configuration: null,
  aws_configuration: {
    id: 10,
    role_arn: "arn:aws:iam::123456789012:role/DeepOps",
    external_id: "nuvemiq-existing-id",
    regions: ["sa-east-1"],
    is_management_account: false,
    schedule_enabled: true,
    scan_interval_hours: 168,
    next_scan_at: "2099-01-01T00:00:00Z",
    created_at: "",
    updated_at: "",
  },
};

const ociAccount = {
  id: 2,
  provider: "oci",
  native_account_id: "ocid1.tenancy.oc1..tenant",
  name: "OCI Prod",
  enabled: true,
  connection_status: "untested",
  last_connection_test_at: null,
  last_error: null,
  schedule_enabled: false,
  scan_interval_hours: 24,
  next_scan_at: null,
  created_at: "",
  updated_at: "",
  aws_configuration: null,
  oci_configuration: {
    id: 20,
    user_ocid: "ocid1.user.oc1..user",
    fingerprint: "aa:bb:cc",
    region: "sa-saopaulo-1",
    scope_regions: ["sa-saopaulo-1"],
    compartment_ocids: ["ocid1.compartment.oc1..a"],
    include_root_compartment: false,
    include_subcompartments: false,
    credentials_configured: true,
    credential_key_version: "v1",
    credential_revision: 1,
    configuration_revision: 1,
    created_at: "",
    updated_at: "",
  },
};

test("AWS form reads schedule from CloudAccount rather than the legacy AWS mirror", () => {
  const form = accountToForm(awsAccount);
  assert.equal(form.aws.schedule_enabled, false);
  assert.equal(form.aws.scan_interval_hours, 24);
});

test("OCI create payload never contains AWS fields and preserves explicit scope", () => {
  const form = createEmptyAccountForm("oci");
  form.name = "OCI";
  form.native_account_id = "ocid1.tenancy.oc1..tenant";
  form.oci.user_ocid = "ocid1.user.oc1..user";
  form.oci.fingerprint = "aa:bb";
  form.oci.region = "sa-saopaulo-1";
  form.oci.scope_regions = "sa-saopaulo-1, us-ashburn-1";
  form.oci.compartment_ocids = "";
  form.oci.include_root_compartment = true;
  form.oci.private_key_pem = "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----";

  const payload = buildCreateAccountPayload(form);
  assert.equal(payload.provider, "oci");
  assert.equal("aws" in payload, false);
  assert.deepEqual(payload.configuration.scope_regions, ["sa-saopaulo-1", "us-ashburn-1"]);
  assert.deepEqual(payload.configuration.compartment_ocids, []);
  assert.equal(payload.configuration.include_root_compartment, true);
  assert.equal("role_arn" in payload.configuration, false);
});

test("switching to a fresh provider state clears incompatible secret fields", () => {
  const oci = createEmptyAccountForm("oci");
  oci.oci.private_key_pem = "secret";
  oci.oci.private_key_password = "password";
  const aws = createEmptyAccountForm("aws", "generated");
  assert.equal(aws.oci.private_key_pem, "");
  assert.equal(aws.oci.private_key_password, "");
  assert.equal(aws.aws.external_id, "generated");
});

test("OCI edit without replacement omits credentials and fingerprint", () => {
  const form = accountToForm(ociAccount);
  form.name = "OCI Renamed";
  form.oci.scope_regions = "sa-saopaulo-1, us-ashburn-1";
  const payload = buildUpdateAccountPayload(ociAccount, form);

  assert.equal(payload.name, "OCI Renamed");
  assert.deepEqual(payload.configuration.scope_regions, ["sa-saopaulo-1", "us-ashburn-1"]);
  assert.equal("private_key_pem" in payload.configuration, false);
  assert.equal("private_key_password" in payload.configuration, false);
  assert.equal("fingerprint" in payload.configuration, false);
});

test("OCI credential replacement is explicit and can be cancelled by omitting it", () => {
  const form = accountToForm(ociAccount);
  form.oci.private_key_pem = "new-private-key";
  form.oci.private_key_password = "new-password";
  form.oci.fingerprint = "11:22:33";

  const cancelled = buildUpdateAccountPayload(ociAccount, form, { replaceCredentials: false });
  assert.equal(cancelled.configuration, undefined);

  const replacing = buildUpdateAccountPayload(ociAccount, form, { replaceCredentials: true });
  assert.equal(replacing.configuration.private_key_pem, "new-private-key");
  assert.equal(replacing.configuration.private_key_password, "new-password");
  assert.equal(replacing.configuration.fingerprint, "11:22:33");
});

test("AWS partial update preserves explicit false and empty list values", () => {
  const form = accountToForm(awsAccount);
  form.aws.regions = "";
  form.aws.schedule_enabled = true;
  form.enabled = false;
  const payload = buildUpdateAccountPayload(awsAccount, form);

  assert.equal(payload.enabled, false);
  assert.deepEqual(payload.configuration.regions, []);
  assert.equal(payload.configuration.schedule_enabled, true);
});

test("mixed account filter searches the complete loaded list by provider, name or identifier", () => {
  const accounts = [awsAccount, ociAccount];
  assert.deepEqual(filterCloudAccounts(accounts, "oci", "").map((item) => item.id), [2]);
  assert.deepEqual(filterCloudAccounts(accounts, "all", "123456").map((item) => item.id), [1]);
  assert.deepEqual(filterCloudAccounts(accounts, "all", "oci prod").map((item) => item.id), [2]);
});

test("form validation rejects invalid AWS identity and role mismatch before submit", () => {
  const form = createEmptyAccountForm("aws", "nuvemiq-valid-external-id");
  form.name = "AWS";
  form.native_account_id = "123";
  form.aws.role_arn = "arn:aws:iam::999999999999:role/DeepOps";
  form.aws.regions = "sa-east-1";
  let errors = validateAccountForm(form, { mode: "create" });
  assert.equal(errors.native_account_id, "AWS Account ID deve conter exatamente 12 dígitos.");

  form.native_account_id = "123456789012";
  errors = validateAccountForm(form, { mode: "create" });
  assert.equal(errors.role_arn, "O Account ID do Role ARN deve ser o mesmo da conta.");
});

test("OCI validation enforces explicit subcompartment base and replacement key", () => {
  const form = accountToForm(ociAccount);
  form.oci.include_subcompartments = true;
  form.oci.include_root_compartment = false;
  form.oci.compartment_ocids = "";
  form.oci.private_key_pem = "short";
  form.oci.fingerprint = "";

  const errors = validateAccountForm(form, { mode: "edit", replaceCredentials: true });
  assert.match(errors.compartment_ocids, /compartment-base/);
  assert.match(errors.private_key_pem, /64 bytes/);
  assert.match(errors.fingerprint, /fingerprint/);
});

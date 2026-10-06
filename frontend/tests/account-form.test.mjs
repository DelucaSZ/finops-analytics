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
  id: 1, provider: "aws", native_account_id: "123456789012", name: "AWS Prod", enabled: true,
  connection_status: "connected", last_connection_test_at: null, last_error: null,
  schedule_enabled: false, scan_interval_hours: 24, next_scan_at: null, created_at: "", updated_at: "",
  oci_configuration: null,
  aws_configuration: {
    id: 10, role_arn: "arn:aws:iam::123456789012:role/DeepOps", external_id: "nuvemiq-existing-id",
    regions: ["sa-east-1"], is_management_account: false,
    schedule_enabled: true, scan_interval_hours: 168, next_scan_at: "2099-01-01T00:00:00Z",
    created_at: "", updated_at: "",
  },
};

const ociAccount = {
  id: 2, provider: "oci", native_account_id: "ocid1.tenancy.oc1..tenant", name: "OCI Prod", enabled: true,
  connection_status: "untested", last_connection_test_at: null, last_error: null,
  schedule_enabled: false, scan_interval_hours: 24, next_scan_at: null, created_at: "", updated_at: "",
  aws_configuration: null,
  oci_configuration: {
    id: 20, user_ocid: "ocid1.user.oc1..user", fingerprint: "aa:bb:cc", region: "sa-saopaulo-1",
    scope_regions: ["sa-saopaulo-1"], compartment_ocids: ["ocid1.compartment.oc1..a"],
    include_root_compartment: false, include_subcompartments: false, credentials_configured: true,
    credential_key_version: "v1", credential_revision: 1, configuration_revision: 1, created_at: "", updated_at: "",
  },
};

function assertNoWriteOnlyFields(payload) {
  assert.equal("next_scan_at" in payload, false);
  if (payload.configuration) assert.equal("next_scan_at" in payload.configuration, false);
}

function assertScheduleOnlyOciPayload(payload) {
  assert.equal(payload.configuration, undefined);
  assert.equal("private_key_pem" in payload, false);
  assert.equal("private_key_password" in payload, false);
  assert.equal("fingerprint" in payload, false);
  assert.equal("scope_regions" in payload, false);
  assert.equal("compartment_ocids" in payload, false);
  assert.equal("region" in payload, false);
  assert.equal("user_ocid" in payload, false);
  assertNoWriteOnlyFields(payload);
}

test("empty form keeps scheduling provider-neutral with safe defaults", () => {
  const form = createEmptyAccountForm();
  assert.equal(form.schedule_enabled, false);
  assert.equal(form.scan_interval_hours, 24);
  assert.equal("schedule_enabled" in form.aws, false);
  assert.equal("scan_interval_hours" in form.aws, false);
});

test("AWS and OCI forms read scheduling from CloudAccount", () => {
  const aws = accountToForm(awsAccount);
  assert.equal(aws.schedule_enabled, false);
  assert.equal(aws.scan_interval_hours, 24);
  assert.equal("schedule_enabled" in aws.aws, false);
  const oci = accountToForm({ ...ociAccount, schedule_enabled: true, scan_interval_hours: 168 });
  assert.equal(oci.schedule_enabled, true);
  assert.equal(oci.scan_interval_hours, 168);
});

test("AWS create sends scheduling only at common level", () => {
  const form = createEmptyAccountForm("aws", "nuvemiq-valid-external-id");
  form.name = "AWS"; form.native_account_id = "123456789012";
  form.aws.role_arn = "arn:aws:iam::123456789012:role/DeepOps";
  form.schedule_enabled = true; form.scan_interval_hours = 168;
  const payload = buildCreateAccountPayload(form);
  assert.equal(payload.schedule_enabled, true);
  assert.equal(payload.scan_interval_hours, 168);
  assert.equal("schedule_enabled" in payload.configuration, false);
  assert.equal("scan_interval_hours" in payload.configuration, false);
  assertNoWriteOnlyFields(payload);
});

test("OCI create sends common scheduling and only OCI-specific configuration", () => {
  const form = createEmptyAccountForm("oci");
  form.name = "OCI"; form.native_account_id = "ocid1.tenancy.oc1..tenant";
  form.oci.user_ocid = "ocid1.user.oc1..user"; form.oci.fingerprint = "aa:bb";
  form.oci.region = "sa-saopaulo-1"; form.oci.scope_regions = "sa-saopaulo-1, us-ashburn-1";
  form.oci.include_root_compartment = true;
  form.oci.private_key_pem = "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----";
  const payload = buildCreateAccountPayload(form);
  assert.equal(payload.schedule_enabled, false);
  assert.equal(payload.scan_interval_hours, 24);
  assert.equal("schedule_enabled" in payload.configuration, false);
  assert.equal("scan_interval_hours" in payload.configuration, false);
  assert.deepEqual(payload.configuration.scope_regions, ["sa-saopaulo-1", "us-ashburn-1"]);
  assertNoWriteOnlyFields(payload);
});

test("AWS schedule-only update is common and leaves configuration absent", () => {
  const form = accountToForm(awsAccount);
  form.schedule_enabled = true;
  assert.deepEqual(buildUpdateAccountPayload(awsAccount, form), { schedule_enabled: true });
  form.schedule_enabled = false; form.scan_interval_hours = 168;
  assert.deepEqual(buildUpdateAccountPayload(awsAccount, form), { scan_interval_hours: 168 });
});

test("AWS schedule plus config keeps each field in its correct layer", () => {
  const form = accountToForm(awsAccount);
  form.schedule_enabled = true;
  form.aws.regions = "sa-east-1, us-east-1";
  const payload = buildUpdateAccountPayload(awsAccount, form);
  assert.equal(payload.schedule_enabled, true);
  assert.deepEqual(payload.configuration, { regions: ["sa-east-1", "us-east-1"] });
});

test("OCI schedule-only updates never resend credentials or scope", () => {
  const enabled = accountToForm(ociAccount); enabled.schedule_enabled = true;
  const enabledPayload = buildUpdateAccountPayload(ociAccount, enabled);
  assert.deepEqual(enabledPayload, { schedule_enabled: true });
  assertScheduleOnlyOciPayload(enabledPayload);

  const disabledAccount = { ...ociAccount, schedule_enabled: true };
  const disabled = accountToForm(disabledAccount); disabled.schedule_enabled = false;
  assert.deepEqual(buildUpdateAccountPayload(disabledAccount, disabled), { schedule_enabled: false });

  const weekly = accountToForm(ociAccount); weekly.scan_interval_hours = 168;
  const weeklyPayload = buildUpdateAccountPayload(ociAccount, weekly);
  assert.deepEqual(weeklyPayload, { scan_interval_hours: 168 });
  assertScheduleOnlyOciPayload(weeklyPayload);

  const twelveAccount = { ...ociAccount, scan_interval_hours: 168 };
  const twelve = accountToForm(twelveAccount); twelve.scan_interval_hours = 12;
  assert.deepEqual(buildUpdateAccountPayload(twelveAccount, twelve), { scan_interval_hours: 12 });
});

test("OCI combined schedule and scope update preserves partial configuration", () => {
  const form = accountToForm(ociAccount);
  form.schedule_enabled = true;
  form.oci.scope_regions = "sa-saopaulo-1, us-ashburn-1";
  const payload = buildUpdateAccountPayload(ociAccount, form);
  assert.equal(payload.schedule_enabled, true);
  assert.deepEqual(payload.configuration, { scope_regions: ["sa-saopaulo-1", "us-ashburn-1"] });
  assert.equal("private_key_pem" in payload.configuration, false);
  assert.equal("fingerprint" in payload.configuration, false);
});

test("OCI combined schedule and credential replacement keeps credentials provider-specific", () => {
  const form = accountToForm(ociAccount);
  form.schedule_enabled = true;
  form.oci.private_key_pem = "new-private-key";
  form.oci.private_key_password = "new-password";
  form.oci.fingerprint = "11:22:33";
  const payload = buildUpdateAccountPayload(ociAccount, form, { replaceCredentials: true });
  assert.equal(payload.schedule_enabled, true);
  assert.deepEqual(payload.configuration, {
    private_key_pem: "new-private-key", fingerprint: "11:22:33", private_key_password: "new-password",
  });
});

test("no changes and reverted scheduling changes produce an empty diff", () => {
  const form = accountToForm(ociAccount);
  assert.deepEqual(buildUpdateAccountPayload(ociAccount, form), {});
  form.schedule_enabled = true; form.schedule_enabled = false;
  form.scan_interval_hours = 168; form.scan_interval_hours = 24;
  assert.deepEqual(buildUpdateAccountPayload(ociAccount, form), {});
});

test("fresh provider state clears incompatible secrets and never auto-enables scheduling", () => {
  const oci = createEmptyAccountForm("oci");
  oci.oci.private_key_pem = "secret"; oci.oci.private_key_password = "password"; oci.schedule_enabled = true;
  const aws = createEmptyAccountForm("aws", "generated");
  assert.equal(aws.oci.private_key_pem, "");
  assert.equal(aws.oci.private_key_password, "");
  assert.equal(aws.schedule_enabled, false);
  assert.equal(aws.scan_interval_hours, 24);
});

test("mixed account filter searches the complete loaded list by provider, name or identifier", () => {
  const accounts = [awsAccount, ociAccount];
  assert.deepEqual(filterCloudAccounts(accounts, "oci", "").map((item) => item.id), [2]);
  assert.deepEqual(filterCloudAccounts(accounts, "all", "123456").map((item) => item.id), [1]);
  assert.deepEqual(filterCloudAccounts(accounts, "all", "oci prod").map((item) => item.id), [2]);
});

test("validation preserves provider rules and validates supported schedule intervals", () => {
  const form = createEmptyAccountForm("aws", "nuvemiq-valid-external-id");
  form.name = "AWS"; form.native_account_id = "123456789012";
  form.aws.role_arn = "arn:aws:iam::123456789012:role/DeepOps";
  form.scan_interval_hours = 13;
  const errors = validateAccountForm(form, { mode: "create" });
  assert.match(errors.scan_interval_hours, /intervalo/);
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  archiveResultMessage,
  buildArchiveFilters,
  buildArchiveScope,
  periodCloseResultMessage,
} from "../lib/opportunity-archive.mjs";

const state = {
  provider: "aws",
  accountId: "111111111111",
  region: "sa-east-1",
  service: "EC2",
  resourceType: "instance",
  status: "treated",
  presenceStatus: "active",
  severity: "low",
  rule: "ec2_stopped",
  collectionRunId: "run-1",
  resourceId: "i-123",
  search: " worker ",
  current: true,
  page: 7,
  pageSize: 50,
  sort: "last_seen_at",
  order: "desc",
};

test("archive filters mirror list semantics without pagination or ordering", () => {
  assert.deepEqual(buildArchiveFilters(state), {
    provider: "aws",
    account_id: "111111111111",
    region: "sa-east-1",
    service: "EC2",
    resource_type: "instance",
    status: "treated",
    presence_status: "active",
    severity: "low",
    rule: "ec2_stopped",
    collection_run_id: "run-1",
    resource_id: "i-123",
    search: "worker",
    current: true,
  });
});

test("archive-all is explicit and cannot accidentally inherit filters", () => {
  assert.deepEqual(buildArchiveScope(state, { archiveAll: true }), {
    filters: {},
    archive_all: true,
  });
  assert.deepEqual(buildArchiveScope(state), {
    filters: buildArchiveFilters(state),
    archive_all: false,
  });
});

test("result copy reports updated and already archived counts", () => {
  assert.equal(
    archiveResultMessage({ archived: 1795, already_archived: 5 }),
    "1.795 oportunidades arquivadas. 5 já estavam no Histórico.",
  );
  assert.equal(
    periodCloseResultMessage({ snapshots_created: 1842, archived: 1800 }, "Outubro/2026"),
    "Período Outubro/2026 fechado com 1.842 snapshots e 1.800 oportunidades arquivadas.",
  );
});

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = path.resolve(FRONTEND, "..");
const readFrontend = (relativePath) => fs.readFileSync(path.join(FRONTEND, relativePath), "utf8");
const readRoot = (relativePath) => fs.readFileSync(path.join(ROOT, relativePath), "utf8");

const selectors = readFrontend("components/aven/selectors.tsx");

test("selector selection flags are strict booleans and preserve the summary contract", () => {
  assert.match(selectors, /formatSelectionSummary\?: \(selectedOptions: T\[\], allSelected: boolean\) => string/);
  assert.match(selectors, /const allSelected = Boolean\(/);
  assert.match(selectors, /selectableOptions\.length > 0/);
  assert.match(selectors, /selectedSelectableCount === selectableOptions\.length/);
  assert.match(selectors, /const partiallySelected = Boolean\(/);
  assert.match(selectors, /formatSelectionSummary\?\.\(selectedOptions, allSelected\)/);
  assert.doesNotMatch(selectors, /@ts-ignore|@ts-expect-error|as any/);
});

test("single and multiple selector behavior remains covered by explicit branches", () => {
  assert.match(selectors, /multiple\?: false/);
  assert.match(selectors, /multiple: true/);
  assert.match(selectors, /if \(!selection\.multiple\) selection\.onChange\(event\.currentTarget\.value\)/);
  assert.match(selectors, /selection\.onChange\(\[\]\)/);
  assert.match(selectors, /\(selection as SingleSelectorProps\)\.onChange\(""\)/);
  assert.match(selectors, /selection\.value\.length > 0 \? `\$\{selection\.value\.length\} selected` : placeholder/);
  assert.match(selectors, /selection\.onChange\(selectableOptions\.map\(\(option\) => option\.value\)\)/);
  assert.match(selectors, /new Set\(\[\.\.\.selection\.value, option\.value\]\)/);
  assert.match(selectors, /selection\.value\.filter\(\(value\) => value !== option\.value\)/);
  assert.match(selectors, /emptyLabel = "No options available"/);
  assert.match(selectors, /filteredOptions\.length > 0/);
});

test("AccountSelector keeps zero, one, many, all, metadata, search, clear and partial-selection semantics", () => {
  assert.match(selectors, /Nenhuma conta selecionada/);
  assert.match(selectors, /1 conta selecionada/);
  assert.match(selectors, /\$\{selectedOptions\.length\} contas selecionadas/);
  assert.match(selectors, /Todas as contas selecionadas/);
  assert.match(selectors, /account\.accountId, account\.environment, account\.provider\?\.toUpperCase\(\)/);
  assert.match(selectors, /searchable=\{props\.searchable \?\? true\}/);
  assert.match(selectors, /indeterminate=\{partiallySelected\}/);
  assert.match(selectors, /disabled=\{disabled \|\| !hasSelection\}/);
});

test("manual deployment is fail-fast and verifies the running web revision", () => {
  const deploy = readRoot("scripts/deploy.sh");
  assert.match(deploy, /set -euo pipefail/);
  assert.match(deploy, /git diff --quiet/);
  assert.match(deploy, /git diff --cached --quiet/);
  assert.match(deploy, /git pull --ff-only/);
  assert.match(deploy, /git rev-parse --short=12 HEAD/);
  assert.match(deploy, /export NEXT_PUBLIC_BUILD_SHA=/);
  assert.match(deploy, /docker compose build --pull --no-cache/);
  assert.match(deploy, /docker compose up -d --force-recreate --remove-orphans/);
  assert.match(deploy, /docker compose ps/);
  assert.match(deploy, /docker compose exec -T web printenv NEXT_PUBLIC_BUILD_SHA/);
  assert.doesNotMatch(deploy, /git reset --hard/);
  assert.ok(
    deploy.indexOf("docker compose build --pull --no-cache")
      < deploy.indexOf("docker compose up -d --force-recreate --remove-orphans"),
    "build must complete before container recreation",
  );
});

test("the frontend image and version endpoint carry build-time revision metadata", () => {
  const dockerfile = readFrontend("Dockerfile");
  const compose = readRoot("compose.yaml");
  const versionRoute = readFrontend("app/version/route.ts");

  assert.match(compose, /NEXT_PUBLIC_BUILD_SHA: \$\{NEXT_PUBLIC_BUILD_SHA:-unversioned\}/);
  assert.match(dockerfile, /ARG NEXT_PUBLIC_BUILD_SHA/);
  assert.match(dockerfile, /ENV NEXT_PUBLIC_BUILD_SHA=\$NEXT_PUBLIC_BUILD_SHA/);
  assert.match(dockerfile, /LABEL org\.opencontainers\.image\.revision=\$NEXT_PUBLIC_BUILD_SHA/);
  assert.match(versionRoute, /process\.env\.NEXT_PUBLIC_BUILD_SHA/);
  assert.match(versionRoute, /export const dynamic = "force-static"/);
  assert.match(versionRoute, /\{ buildSha \}/);
});

test("deployment documentation makes build success a prerequisite for compose up", () => {
  const deployment = readRoot("docs/deployment.md");
  assert.match(deployment, /docker compose build --pull --no-cache &&/);
  assert.match(deployment, /docker compose up -d --force-recreate --remove-orphans/);
  assert.match(deployment, /\/version/);
  assert.match(deployment, /org\.opencontainers\.image\.revision/);
});

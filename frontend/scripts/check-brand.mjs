import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { legacyBrandAllowlist, legacyBrandPathAllowlist } from "./brand-legacy-allowlist.mjs";

const FRONTEND_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(FRONTEND_ROOT, "..");
const TARGETS = [
  path.join(REPO_ROOT, "frontend", "app"),
  path.join(REPO_ROOT, "frontend", "components"),
  path.join(REPO_ROOT, "frontend", "lib"),
  path.join(REPO_ROOT, "frontend", "package.json"),
  path.join(REPO_ROOT, "backend", "app"),
  path.join(REPO_ROOT, "infrastructure", "cloudformation"),
];
const SOURCE_EXTENSIONS = new Set([".css", ".html", ".js", ".json", ".mjs", ".mts", ".py", ".ts", ".tsx", ".yaml", ".yml"]);
const LEGACY_PATTERN = /DeepOps|Deep Ops|deepops|deep-ops|deep_ops|DEEPOPS|DEEP_OPS|NuvemIQ|Nuvem IQ|nuvemiq/gi;
const SKIP_DIRECTORIES = new Set([".next", "__pycache__", "node_modules"]);

function relative(filename) {
  return path.relative(REPO_ROOT, filename).split(path.sep).join("/");
}

function collectFiles(target) {
  const stat = fs.statSync(target);
  if (stat.isFile()) return [target];
  return fs.readdirSync(target, { withFileTypes: true }).flatMap((entry) => {
    if (entry.isDirectory() && SKIP_DIRECTORIES.has(entry.name)) return [];
    const fullPath = path.join(target, entry.name);
    if (entry.isDirectory()) return collectFiles(fullPath);
    return SOURCE_EXTENSIONS.has(path.extname(entry.name)) ? [fullPath] : [];
  });
}

function isAllowed(file, value) {
  return legacyBrandAllowlist.some((entry) => {
    if (entry.file !== file) return false;
    entry.pattern.lastIndex = 0;
    return entry.pattern.test(value);
  });
}

function auditFile(filename) {
  const file = relative(filename);
  const source = fs.readFileSync(filename, "utf8");
  const findings = [];
  source.split(/\r?\n/).forEach((line, index) => {
    LEGACY_PATTERN.lastIndex = 0;
    for (const match of line.matchAll(LEGACY_PATTERN)) {
      if (!isAllowed(file, match[0]) && !isAllowed(file, line)) {
        findings.push({ file, line: index + 1, value: match[0], excerpt: line.trim() });
      }
    }
  });
  return findings;
}

function auditPath(filename) {
  const file = relative(filename);
  LEGACY_PATTERN.lastIndex = 0;
  if (!LEGACY_PATTERN.test(file)) return [];
  if (legacyBrandPathAllowlist.some((entry) => entry.path === file)) return [];
  return [{ file, line: 0, value: "legacy path", excerpt: file }];
}

const files = [...new Set(TARGETS.flatMap(collectFiles))];
const findings = files.flatMap((filename) => [...auditPath(filename), ...auditFile(filename)]);

console.log(`Aven brand lint: ${findings.length === 0 ? "PASS" : "FAIL"}`);
console.log(`Files scanned: ${files.length}`);
console.log(`Allowlisted technical references: ${legacyBrandAllowlist.length}`);
console.log(`Allowlisted legacy paths: ${legacyBrandPathAllowlist.length}`);

if (findings.length) {
  console.error("\nUnclassified legacy branding references:");
  for (const finding of findings) {
    console.error(`- ${finding.file}${finding.line ? `:${finding.line}` : ""} ${finding.value} — ${finding.excerpt}`);
  }
  process.exitCode = 1;
}

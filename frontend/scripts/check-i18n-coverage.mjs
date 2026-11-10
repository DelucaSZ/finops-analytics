import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(FRONTEND, "..");
const DIRECTORIES = ["app", "components", "lib"];
const UI_PROPS = new Set([
  "label", "title", "description", "placeholder", "helperText", "supportingText",
  "emptyTitle", "emptyDescription", "tooltip", "aria-label", "aria-description",
  "alt", "message", "error", "success", "heading", "caption", "hint",
]);
const PRESERVED = new Set([
  "Aven", "AWS", "OCI", "RDS", "NU", "ACME", "Caddy", "JSON", "API", "URL",
  "TLS", "DNS", "MFA", "HTTP", "HTTPS", "IAM", "UTC", "OCID", "ARN", "PEM",
  "BRL", "USD", "EC2", "EBS", "S3", "KMS", "RBAC", "FinOps",
]);

function normalized(value) {
  return value.replace(/\s+/g, " ").trim();
}

function isCopy(value) {
  const text = normalized(value);
  if (text.length < 2 || PRESERVED.has(text)) return false;
  if (!/[\p{L}]/u.test(text) || !/[\p{L}]{2,}/u.test(text)) return false;
  if (/^(?:https?:\/\/|\/|#|--|[A-Z_][A-Z_0-9/-]*$)/.test(text)) return false;
  if (/^(?:ocid1\.|arn:|[A-Za-z]+:\/|[\w.-]+\.(?:ts|tsx|js|mjs|json))/.test(text)) return false;
  return true;
}

function literal(node) {
  if (node && (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node))) {
    return node.text;
  }
  if (node && ts.isJsxExpression(node)) return literal(node.expression);
  return null;
}

function propertyName(node) {
  if (!node) return null;
  if (ts.isIdentifier(node) || ts.isStringLiteral(node)) return node.text;
  return null;
}

/** Candidate detector, not proof of translation status. Runs only over source AST nodes
 * that can directly supply user-facing copy. Never mutates or translates business values.
 */
export function scanFileCandidates(source, relativePath = "fixture.tsx") {
  const scriptKind = relativePath.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const sf = ts.createSourceFile(relativePath, source, ts.ScriptTarget.Latest, true, scriptKind);
  const findings = new Map();

  function add(node, kind, raw) {
    if (!isCopy(raw)) return;
    const value = normalized(raw);
    const fingerprint = JSON.stringify([relativePath, kind, value]);
    if (!findings.has(fingerprint)) {
      const position = sf.getLineAndCharacterOfPosition(node.getStart(sf));
      findings.set(fingerprint, { file: relativePath, line: position.line + 1, kind, text: value, fingerprint });
    }
  }

  function visit(node) {
    if (ts.isJsxText(node)) {
      if (!(node.parent && ts.isJsxElement(node.parent) &&
        ["code", "pre", "kbd"].includes(node.parent.openingElement.tagName.getText(sf)))) {
        add(node, "jsx", node.getText(sf));
      }
    } else if (ts.isJsxAttribute(node)) {
      const key = propertyName(node.name);
      if (key && UI_PROPS.has(key)) {
        const value = literal(node.initializer);
        if (value !== null) add(node, "attribute", value);
      }
    } else if (ts.isPropertyAssignment(node)) {
      const key = propertyName(node.name);
      if (key && UI_PROPS.has(key)) {
        const value = literal(node.initializer);
        if (value !== null) add(node, "presentation-property", value);
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sf);
  return [...findings.values()].sort((a, b) => a.line - b.line || a.fingerprint.localeCompare(b.fingerprint));
}

export function newCandidates(current, previous) {
  const known = new Set(previous.map(item => item.fingerprint));
  return current.filter(item => !known.has(item.fingerprint));
}

function walk(directory, output = []) {
  if (!existsSync(directory)) return output;
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) walk(target, output);
    else if (entry.isFile() && /\.(tsx|ts)$/.test(entry.name) &&
      !/(\.d\.ts|\.test\.ts|\.spec\.ts|\.stories\.tsx)$/.test(entry.name)) {
      output.push(target);
    }
  }
  return output;
}

function runGit(args) {
  return execFileSync("git", ["-C", REPO, ...args], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
}

function exceptions() {
  const filename = path.join(FRONTEND, "scripts", "i18n-coverage-exceptions.json");
  const data = JSON.parse(readFileSync(filename, "utf8"));
  for (const [fingerprint, reason] of Object.entries(data)) {
    if (typeof reason !== "string" || reason.trim().length < 20 ||
      !Array.isArray(JSON.parse(fingerprint)) || JSON.parse(fingerprint).length !== 3) {
      throw new Error("Exception must supply [file, kind, text] and a reason of at least 20 characters");
    }
  }
  return data;
}

export function auditCoverage({ base = null, report = false } = {}) {
  const allow = exceptions();
  const scanned = [];
  let targets;
  if (base) {
    // Explicit base is mandatory in PR CI. Git handles files that did not exist at base.
    runGit(["rev-parse", "--verify", base + "^{commit}"]);
    targets = runGit(["diff", "--name-only", "--diff-filter=ACMRT", base, "--",
      "frontend/app", "frontend/components", "frontend/lib"])
      .split("\n").filter(file => /\.(tsx|ts)$/.test(file) && !/\.d\.ts$/.test(file))
      .map(file => path.join(REPO, file));
  } else {
    targets = DIRECTORIES.flatMap(dir => walk(path.join(FRONTEND, dir)));
  }

  for (const file of targets) {
    if (!existsSync(file)) continue;
    const relative = path.relative(REPO, file).replace(/\\/g, "/");
    const current = scanFileCandidates(readFileSync(file, "utf8"), relative);
    let newItems = current;
    if (base) {
      let before = "";
      try {
        before = runGit(["show", base + ":" + relative]);
      } catch {
        // File added since the base commit.
      }
      newItems = newCandidates(current, scanFileCandidates(before, relative));
    }
    scanned.push({ file: relative, count: current.length,
      candidates: newItems.filter(item => !(item.fingerprint in allow)) });
  }

  const findings = scanned.flatMap(item => item.candidates);
  const total = scanned.reduce((sum, file) => sum + file.count, 0);
  if (report) {
    console.log(JSON.stringify({ mode: base ? "incremental" : "inventory", files: scanned.length,
      candidateCount: total, findings }, null, 2));
  } else {
    console.log("[Aven i18n] " + scanned.length + " files scanned, " + total +
      " candidate occurrences, " + findings.length + (base ? " new unapproved" : " unreviewed"));
    for (const item of findings.slice(0, 50)) {
      console.log(item.file + ":" + item.line + " [" + item.kind + "] " + item.text);
    }
    if (findings.length > 50) console.log("... additional findings: " + (findings.length - 50));
  }
  if (base && findings.length > 0) {
    throw new Error("New user-visible hardcoded text detected. Localize or add a reviewed exception with reason.");
  }
  return { files: scanned.length, total, findings };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const args = process.argv.slice(2);
    const baseFlag = args.indexOf("--base");
    const base = baseFlag >= 0 ? args[baseFlag + 1] : process.env.AVEN_I18N_BASE || null;
    if (baseFlag >= 0 && (!base || base.startsWith("--"))) {
      throw new Error("--base requires a Git commit/ref");
    }
    auditCoverage({ base, report: args.includes("--report") });
  } catch (error) {
    console.error("[Aven i18n coverage] " + String(error));
    process.exitCode = 1;
  }
}

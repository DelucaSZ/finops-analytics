import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import { isVisualGuardrailAllowlisted } from "./visual-guardrail-allowlist.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_TARGETS = [
  path.join(ROOT, "components", "ui"),
  path.join(ROOT, "components", "aven"),
  path.join(ROOT, "components", "brand"),
  path.join(ROOT, "components", "app-shell.tsx"),
  path.join(ROOT, "components", "app-shell"),
  path.join(ROOT, "components", "auth"),
  path.join(ROOT, "components", "mfa-settings.tsx"),
  path.join(ROOT, "components", "mfa-settings.module.css"),
  path.join(ROOT, "components", "access-form.tsx"),
  path.join(ROOT, "components", "access-form.module.css"),
  path.join(ROOT, "components", "executive-dashboard.tsx"),
  path.join(ROOT, "components", "executive-dashboard.module.css"),
  path.join(ROOT, "components", "dashboard-operational-insights.tsx"),
  path.join(ROOT, "components", "dashboard-operational-insights.module.css"),
  path.join(ROOT, "components", "opportunity-decision-dialog.tsx"),
  path.join(ROOT, "components", "opportunity-archive-dialog.tsx"),
  path.join(ROOT, "components", "opportunity-dialog.module.css"),
  path.join(ROOT, "components", "opportunity-detail.tsx"),
  path.join(ROOT, "components", "opportunity-detail.module.css"),
  path.join(ROOT, "components", "page-header.tsx"),
  path.join(ROOT, "components", "manual-collection-launcher.tsx"),
  path.join(ROOT, "components", "manual-collection-launcher.module.css"),
  path.join(ROOT, "app", "legacy-theme-compat.css"),
  path.join(ROOT, "app", "surface-hierarchy.css"),
  path.join(ROOT, "app", "layout-system.css"),
  path.join(ROOT, "app", "login"),
  path.join(ROOT, "app", "mfa-setup"),
  path.join(ROOT, "app", "billing"),
  path.join(ROOT, "app", "rds", "reservations"),
  path.join(ROOT, "app", "inventory"),
  path.join(ROOT, "app", "opportunities"),
  path.join(ROOT, "app", "settings"),
  path.join(ROOT, "app", "flow"),
  path.join(ROOT, "app", "collections"),
  path.join(ROOT, "app", "scans"),
  path.join(ROOT, "app", "dev", "ui"),
];
const SOURCE_EXTENSIONS = new Set([".css", ".ts", ".tsx"]);

function stripComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|\s)\/\/.*$/gm, "$1");
}

const rules = [
  {
    category: "colors",
    label: "Hardcoded color",
    guidance: "Use Aven semantic color tokens instead.",
    patterns: [/#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})\b/i, /\b(?:rgb|rgba|hsl|hsla)\s*\(/i, /(?:text|bg|border)-\[\s*#[0-9a-f]+\s*\]/i],
  },
  {
    category: "spacing",
    label: "Hardcoded structural spacing",
    guidance: "Use the Aven spacing scale or a documented technical sizing exception.",
    patterns: [
      /\b(?:padding|padding-(?:block|inline|top|right|bottom|left)|margin|margin-(?:block|inline|top|right|bottom|left)|gap|row-gap|column-gap)\s*:(?!\s*[^;]*var\()[^;]*(?:\d+(?:\.\d+)?(?:px|rem|em))/i,
      /\b(?:p|px|py|pt|pr|pb|pl|m|mx|my|mt|mr|mb|ml|gap|gap-x|gap-y)-\[[^\]]*(?:px|rem|em)[^\]]*\]/i,
      /\b(?:padding|margin|gap|rowGap|columnGap)\s*:\s*["'`]\s*\d+(?:\.\d+)?(?:px|rem|em)/i,
      /\b(?:w|h|min-w|max-w|min-h|max-h)-\[(?:[4-9]\d|[1-9]\d{2,})px\]/i,
    ],
  },
  {
    category: "radius",
    label: "Hardcoded border radius",
    guidance: "Use an Aven semantic radius token instead.",
    patterns: [
      /\bborder-radius\s*:(?!\s*var\()[^;]*(?:\d+(?:\.\d+)?(?:px|rem|em)|999\w*)/i,
      /\brounded(?:-[trblxy]+)?-\[[^\]]+\]/i,
      /\bborderRadius\s*:\s*["'`]\s*\d+(?:\.\d+)?(?:px|rem|em)/i,
    ],
  },
  {
    category: "typography",
    label: "Hardcoded typography",
    guidance: "Use Aven semantic typography tokens instead.",
    patterns: [
      /\bfont-(?:size|family|weight)\s*:(?!\s*var\()[^;]+/i,
      /\bline-height\s*:(?!\s*var\()[^;]+/i,
      /\bletter-spacing\s*:(?!\s*var\()[^;]+/i,
      /\b(?:fontSize|fontFamily|fontWeight|lineHeight)\s*:\s*["'`]?(?:\d|[a-z])/i,
      /\b(?:text|font|leading)-\[[^\]]+\]/i,
    ],
  },
];

export function scanText(source, filename = "unknown") {
  const clean = stripComments(source);
  const violations = [];
  clean.split(/\r?\n/).forEach((line, index) => {
    for (const rule of rules) {
      for (const pattern of rule.patterns) {
        const match = line.match(pattern);
        if (match) {
          violations.push({
            category: rule.category,
            label: rule.label,
            guidance: rule.guidance,
            filename,
            line: index + 1,
            excerpt: match[0].trim(),
          });
          break;
        }
      }
    }
  });
  return violations;
}

function collectFiles(target) {
  const stat = fs.statSync(target);
  if (stat.isFile()) return SOURCE_EXTENSIONS.has(path.extname(target)) ? [target] : [];
  return fs.readdirSync(target, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(target, entry.name);
    if (entry.isDirectory()) return collectFiles(fullPath);
    return SOURCE_EXTENSIONS.has(path.extname(entry.name)) ? [fullPath] : [];
  });
}

export function scanDirectory(target = DEFAULT_TARGETS[0]) {
  return collectFiles(target).flatMap((filename) => {
    const relative = path.relative(ROOT, filename).replaceAll("\\", "/");
    if (isVisualGuardrailAllowlisted(relative)) return [];
    return scanText(fs.readFileSync(filename, "utf8"), relative);
  });
}

function normalizeDiffPath(value) {
  return value.replace(/^b\//, "").replace(/^frontend\//, "").replaceAll("\\", "/");
}

export function scanAddedLines(diffText) {
  const violations = [];
  let filename = "";
  let newLine = 0;

  for (const rawLine of diffText.split(/\r?\n/)) {
    if (rawLine.startsWith("+++ ")) {
      const target = rawLine.slice(4).trim();
      filename = target === "/dev/null" ? "" : normalizeDiffPath(target);
      continue;
    }

    const hunk = rawLine.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
    if (hunk) {
      newLine = Number.parseInt(hunk[1], 10);
      continue;
    }

    if (!filename || !SOURCE_EXTENSIONS.has(path.extname(filename)) || isVisualGuardrailAllowlisted(filename)) {
      if (rawLine.startsWith(" ") || rawLine.startsWith("+")) newLine += 1;
      continue;
    }

    if (rawLine.startsWith("+") && !rawLine.startsWith("+++")) {
      const found = scanText(rawLine.slice(1), filename);
      violations.push(...found.map((item) => ({ ...item, line: newLine })));
      newLine += 1;
      continue;
    }

    if (rawLine.startsWith(" ")) newLine += 1;
  }

  return violations;
}

export function summarize(violations) {
  return Object.fromEntries(rules.map((rule) => [rule.category, violations.filter((item) => item.category === rule.category).length]));
}

function printResult(violations, scopeLabel) {
  const summary = summarize(violations);
  console.log(`Aven hardcode gate: ${violations.length === 0 ? "PASS" : "FAIL"}`);
  console.log(`Scope: ${scopeLabel}`);
  console.log(`Hardcoded colors: ${summary.colors}`);
  console.log(`Hardcoded structural spacing: ${summary.spacing}`);
  console.log(`Hardcoded border radius: ${summary.radius}`);
  console.log(`Hardcoded typography: ${summary.typography}`);

  if (violations.length) {
    console.error("\nViolations:");
    for (const violation of violations) {
      console.error(`- ${violation.filename}:${violation.line} [${violation.category}] ${violation.label}: ${violation.excerpt}. ${violation.guidance}`);
    }
    process.exitCode = 1;
  }
}

function scanChanged(baseRef) {
  if (!baseRef) throw new Error("Changed-line visual guardrail requires a base ref or AVEN_VISUAL_BASE.");
  const diff = execFileSync(
    "git",
    ["diff", "--unified=0", `${baseRef}...HEAD`, "--", "app", "components"],
    { cwd: ROOT, encoding: "utf8", maxBuffer: 16 * 1024 * 1024 },
  );
  return scanAddedLines(diff);
}

function run() {
  const args = process.argv.slice(2);
  if (args[0] === "--changed") {
    const baseRef = args[1] || process.env.AVEN_VISUAL_BASE;
    const violations = scanChanged(baseRef);
    printResult(violations, `new lines in app/components since ${baseRef}`);
    return;
  }

  const targets = args.length
    ? args.map((target) => path.resolve(process.cwd(), target))
    : DEFAULT_TARGETS;
  const violations = targets.flatMap((target) => scanDirectory(target));
  printResult(violations, targets.map((target) => path.relative(ROOT, target)).join(", "));
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) run();

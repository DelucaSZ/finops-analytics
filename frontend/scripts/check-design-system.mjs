import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

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
    label: "Hardcoded colors",
    patterns: [/#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})\b/i, /\b(?:rgb|rgba|hsl|hsla)\s*\(/i, /(?:text|bg|border)-\[\s*#[0-9a-f]+\s*\]/i],
  },
  {
    category: "spacing",
    label: "Hardcoded structural spacing",
    patterns: [
      /\b(?:padding|padding-(?:block|inline|top|right|bottom|left)|margin|margin-(?:block|inline|top|right|bottom|left)|gap|row-gap|column-gap)\s*:(?!\s*[^;]*var\()[^;]*(?:\d+(?:\.\d+)?(?:px|rem|em))/i,
      /\b(?:p|px|py|pt|pr|pb|pl|m|mx|my|mt|mr|mb|ml|gap|gap-x|gap-y)-\[[^\]]*(?:px|rem|em)[^\]]*\]/i,
      /\b(?:padding|margin|gap|rowGap|columnGap)\s*:\s*["'`]\s*\d+(?:\.\d+)?(?:px|rem|em)/i,
    ],
  },
  {
    category: "radius",
    label: "Hardcoded border radius",
    patterns: [
      /\bborder-radius\s*:(?!\s*var\()[^;]*(?:\d+(?:\.\d+)?(?:px|rem|em)|999\w*)/i,
      /\brounded(?:-[trblxy]+)?-\[[^\]]+\]/i,
      /\bborderRadius\s*:\s*["'`]\s*\d+(?:\.\d+)?(?:px|rem|em)/i,
    ],
  },
  {
    category: "typography",
    label: "Hardcoded typography",
    patterns: [
      /\bfont-(?:size|family|weight)\s*:(?!\s*var\()[^;]+/i,
      /\bline-height\s*:(?!\s*var\()[^;]+/i,
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
          violations.push({ category: rule.category, label: rule.label, filename, line: index + 1, excerpt: match[0].trim() });
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
  return collectFiles(target).flatMap((filename) => scanText(fs.readFileSync(filename, "utf8"), path.relative(ROOT, filename)));
}

export function summarize(violations) {
  return Object.fromEntries(rules.map((rule) => [rule.category, violations.filter((item) => item.category === rule.category).length]));
}

function run() {
  const targets = process.argv.length > 2
    ? process.argv.slice(2).map((target) => path.resolve(process.cwd(), target))
    : DEFAULT_TARGETS;
  const violations = targets.flatMap((target) => scanDirectory(target));
  const summary = summarize(violations);

  console.log(`Aven hardcode gate: ${violations.length === 0 ? "PASS" : "FAIL"}`);
  console.log(`Scopes: ${targets.map((target) => path.relative(ROOT, target)).join(", ")}`);
  console.log(`Hardcoded colors: ${summary.colors}`);
  console.log(`Hardcoded structural spacing: ${summary.spacing}`);
  console.log(`Hardcoded border radius: ${summary.radius}`);
  console.log(`Hardcoded typography: ${summary.typography}`);

  if (violations.length) {
    console.error("\nViolations:");
    for (const violation of violations) {
      console.error(`- ${violation.filename}:${violation.line} [${violation.category}] ${violation.excerpt}`);
    }
    process.exitCode = 1;
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) run();

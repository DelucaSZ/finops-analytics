import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import { validateCatalogFiles } from "./check-i18n.mjs";

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const NAMESPACE_APIS = new Set(["useTranslations", "getTranslations"]);
function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const filename = path.join(dir, entry.name);
    if (entry.isDirectory()) return walk(filename);
    return entry.isFile() && /\.(ts|tsx)$/.test(filename) && !/\.d\.ts$/.test(filename)
      ? [filename] : [];
  });
}
function flatten(value, prefix = "", map = new Map()) {
  for (const [key, child] of Object.entries(value)) {
    const full = prefix ? prefix + "." + key : key;
    if (typeof child === "string") map.set(full, child);
    else if (child && typeof child === "object") flatten(child, full, map);
  }
  return map;
}
function staticString(node) {
  return node && (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node))
    ? node.text : null;
}
function namespaceOfCall(node) {
  if (!ts.isCallExpression(node) || !ts.isIdentifier(node.expression) ||
      !NAMESPACE_APIS.has(node.expression.text)) return undefined;
  if (node.arguments.length === 0) return "";
  const arg = node.arguments[0];
  const string = staticString(arg);
  if (string !== null) return string;
  if (ts.isObjectLiteralExpression(arg)) {
    const name = arg.properties.find(prop => ts.isPropertyAssignment(prop) &&
      prop.name.getText() === "namespace");
    if (name && ts.isPropertyAssignment(name)) return staticString(name.initializer) ?? undefined;
    return "";
  }
  return undefined;
}

/** Static references only: dynamic keys are logged for review, never guessed. */
export function scanTranslationReferences(source, filename = "fixture.tsx") {
  const sf = ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true,
    filename.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const resolved = [], dynamic = [];
  function visit(node, inherited) {
    const scopeBoundary = ts.isBlock(node) || ts.isSourceFile(node) ||
      ts.isArrowFunction(node) || ts.isFunctionDeclaration(node) ||
      ts.isFunctionExpression(node);
    const scope = scopeBoundary ? new Map(inherited) : inherited;
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
      const expr = ts.isAwaitExpression(node.initializer) ? node.initializer.expression : node.initializer;
      const namespace = namespaceOfCall(expr);
      if (namespace !== undefined) scope.set(node.name.text, namespace);
      else if (ts.isCallExpression(expr) && ts.isIdentifier(expr.expression) &&
          NAMESPACE_APIS.has(expr.expression.text)) {
        dynamic.push({ file: filename, line: sf.getLineAndCharacterOfPosition(node.getStart()).line + 1,
          reason: "Dynamic namespace" });
      }
    }
    if (ts.isCallExpression(node)) {
      let callee = node.expression;
      if (ts.isPropertyAccessExpression(callee) && ["rich", "markup", "raw", "has"].includes(callee.name.text)) {
        callee = callee.expression;
      }
      if (ts.isIdentifier(callee) && scope.has(callee.text) && node.arguments.length > 0) {
        const key = staticString(node.arguments[0]);
        const namespace = scope.get(callee.text);
        const location = { file: filename, line: sf.getLineAndCharacterOfPosition(node.getStart()).line + 1 };
        if (key !== null) resolved.push({ ...location, key: namespace ? namespace + "." + key : key });
        else dynamic.push({ ...location, reason: "Dynamic translation key" });
      }
    }
    ts.forEachChild(node, child => visit(child, scope));
  }
  visit(sf, new Map());
  return { resolved, dynamic };
}

export function checkTranslationReferences(sources, catalogs) {
  const keys = flatten(catalogs["pt-BR"]);
  const referenced = new Set(), missing = [], dynamic = [];
  for (const [filename, source] of sources) {
    const result = scanTranslationReferences(source, filename);
    dynamic.push(...result.dynamic);
    for (const item of result.resolved) {
      referenced.add(item.key);
      if (!keys.has(item.key)) missing.push(item);
    }
  }
  return { referenced: referenced.size, missing, dynamic, orphanCandidates:
    [...keys.keys()].filter(key => !referenced.has(key)) };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    validateCatalogFiles();
    const catalogs = Object.fromEntries(["pt-BR", "en-US"].map(locale => [
      locale, JSON.parse(readFileSync(path.join(FRONTEND, "i18n/messages", locale + ".json"), "utf8")),
    ]));
    const sources = ["app", "components", "lib"].flatMap(dir =>
      walk(path.join(FRONTEND, dir)).map(filename => [
        path.relative(FRONTEND, filename).replace(/\\/g, "/"),
        readFileSync(filename, "utf8"),
      ]));
    const result = checkTranslationReferences(sources, catalogs);
    console.log("[Aven i18n references] " + result.referenced + " distinct static keys, " +
      result.missing.length + " missing, " + result.dynamic.length + " dynamic reference sites, " +
      result.orphanCandidates.length + " possible orphans (never auto-delete)");
    for (const entry of result.missing) console.error(entry.file + ":" + entry.line + " missing " + entry.key);
    if (process.argv.includes("--report")) {
      console.log(JSON.stringify({dynamic: result.dynamic, orphanCandidates: result.orphanCandidates}, null, 2));
    }
    if (result.missing.length) process.exitCode = 1;
  } catch (error) {
    console.error("[Aven i18n references] " + String(error));
    process.exitCode = 1;
  }
}

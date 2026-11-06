import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "@formatjs/icu-messageformat-parser";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const CATALOG_DIR = path.join(ROOT, "i18n", "messages");

/** JSON.parse alone silently accepts duplicate keys. Detect them before parsing. */
export function parseUniqueJson(source) {
  let cursor = 0;
  const skip = () => { while (/\s/.test(source[cursor] ?? "")) cursor++; };

  function parseString() {
    const start = cursor;
    if (source[cursor] !== '"') throw new Error("Expected JSON string at " + cursor);
    cursor++;
    while (cursor < source.length) {
      if (source[cursor] === "\\") { cursor += 2; continue; }
      if (source[cursor++] === '"') return JSON.parse(source.slice(start, cursor));
    }
    throw new Error("Unterminated JSON string");
  }

  function parseValue(location) {
    skip();
    if (source[cursor] === "{") {
      cursor++;
      const seen = new Set();
      skip();
      if (source[cursor] === "}") { cursor++; return; }
      while (cursor < source.length) {
        skip();
        const key = parseString();
        const fullPath = location ? location + "." + key : key;
        if (seen.has(key)) throw new Error("Duplicate translation key: " + fullPath);
        seen.add(key);
        skip();
        if (source[cursor++] !== ":") throw new Error("Expected ':' in " + fullPath);
        parseValue(fullPath);
        skip();
        const separator = source[cursor++];
        if (separator === "}") return;
        if (separator !== ",") throw new Error("Expected ',' or '}' in " + location);
      }
      throw new Error("Unterminated JSON object");
    }
    if (source[cursor] === "[") {
      cursor++;
      skip();
      if (source[cursor] === "]") { cursor++; return; }
      for (let index = 0; cursor < source.length; index++) {
        parseValue(location + "[" + index + "]");
        skip();
        const separator = source[cursor++];
        if (separator === "]") return;
        if (separator !== ",") throw new Error("Expected ',' or ']' in " + location);
      }
      throw new Error("Unterminated JSON array");
    }
    if (source[cursor] === '"') { parseString(); return; }
    const start = cursor;
    while (cursor < source.length && !/[\s,\]}]/.test(source[cursor])) cursor++;
    if (start === cursor) throw new Error("Expected JSON value at " + cursor);
    JSON.parse(source.slice(start, cursor));
  }

  parseValue("");
  skip();
  if (cursor !== source.length) throw new Error("Unexpected trailing JSON content");
  return JSON.parse(source);
}

function flatten(value, pathName = "", output = {}) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Expected translation namespace object: " + pathName);
  }
  for (const [key, child] of Object.entries(value)) {
    const name = pathName ? pathName + "." + key : key;
    if (!/^[a-z][A-Za-z0-9]*$/.test(key)) {
      throw new Error("Invalid semantic key: " + name);
    }
    if (typeof child === "string") {
      if (!child.trim()) throw new Error("Empty translation: " + name);
      output[name] = child;
    } else {
      flatten(child, name, output);
    }
  }
  return output;
}

/** Parse full ICU syntax, then compare arguments and their types across locales. */
function signature(message, key) {
  let ast;
  try {
    ast = parse(message, { ignoreTag: false });
  } catch (error) {
    throw new Error("Invalid ICU message in " + key + ": " + String(error));
  }
  const argumentsByName = new Map();

  function visit(nodes) {
    for (const node of nodes) {
      const type = node.type;
      if ([1, 2, 3, 4, 5, 6].includes(type)) {
        const kind = ({ 1: "argument", 2: "number", 3: "date", 4: "time", 5: "select", 6: "plural" })[type];
        const previous = argumentsByName.get(node.value);
        if (previous && previous !== kind) {
          throw new Error("Conflicting ICU argument types in " + key + ": " + node.value);
        }
        argumentsByName.set(node.value, kind);
      }
      if (node.options) {
        if (!node.options.other) throw new Error("Missing ICU other case in " + key);
        for (const option of Object.values(node.options)) visit(option.value);
      }
      if (node.children) visit(node.children);
    }
  }
  visit(ast);
  return JSON.stringify([...argumentsByName.entries()].sort(([a], [b]) => a.localeCompare(b)));
}

export function validateCatalogObjects(ptBR, enUS) {
  const pt = flatten(ptBR), en = flatten(enUS);
  const ptKeys = Object.keys(pt).sort(), enKeys = Object.keys(en).sort();
  if (JSON.stringify(ptKeys) !== JSON.stringify(enKeys)) {
    throw new Error("Catalog parity mismatch; missing in en-US: " +
      ptKeys.filter((key) => !(key in en)).join(", ") + "; missing in pt-BR: " +
      enKeys.filter((key) => !(key in pt)).join(", "));
  }
  for (const key of ptKeys) {
    const ptArgs = signature(pt[key], "pt-BR." + key);
    const enArgs = signature(en[key], "en-US." + key);
    if (ptArgs !== enArgs) {
      throw new Error("ICU parameter mismatch for " + key + ": " + ptArgs + " vs " + enArgs);
    }
  }
  return { keys: ptKeys.length, namespaces: Object.keys(ptBR).length };
}

export function validateCatalogFiles(dir = CATALOG_DIR) {
  const pt = parseUniqueJson(readFileSync(path.join(dir, "pt-BR.json"), "utf8"));
  const en = parseUniqueJson(readFileSync(path.join(dir, "en-US.json"), "utf8"));
  return validateCatalogObjects(pt, en);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  try {
    const result = validateCatalogFiles();
    console.log("Aven i18n catalogs valid: " + result.keys + " keys / " + result.namespaces + " namespaces");
  } catch (error) {
    console.error("[Aven i18n] " + String(error));
    process.exitCode = 1;
  }
}

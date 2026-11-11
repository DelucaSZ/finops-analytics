import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import { scanTranslationReferences } from "./check-i18n-references.mjs";
import { scanFileCandidates } from "./check-i18n-coverage.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const FRONTEND = path.join(ROOT, "frontend");
const CSV = path.join(ROOT, "docs/i18n/25.9-coverage-reconciliation.csv");
export const EXPECTED_IDS = 2608;
export const EXTRA_FIELDS = ["current_file","current_line","current_component","translation_namespace",
  "translation_key","pt_br_value","en_us_value","match_strategy","confidence","verification_method","pending_action"];

export function parseCsv(input) {
  const rows=[]; let row=[], field="", quote=false;
  for(let i=0;i<input.length;i++) {
    const c=input[i];
    if(quote) {
      if(c==='"' && input[i+1]==='"'){field+='"';i++;}
      else if(c==='"')quote=false;
      else field+=c;
    } else if(c==='"')quote=true;
    else if(c===','){row.push(field);field="";}
    else if(c==='\n'){row.push(field);rows.push(row);row=[];field="";}
    else if(c!=='\r')field+=c;
  }
  if(quote)throw Error("Unterminated CSV quoted cell");
  if(row.length||field){row.push(field);rows.push(row);}
  const header=rows.shift();
  if(!header||!header.includes("id"))throw Error("Missing CSV ID header");
  return {header,rows:rows.filter(a=>a.some(Boolean)).map(a=>Object.fromEntries(header.map((h,i)=>[h,a[i]??""])))};
}
export function csvSerialize(rows,fields) {
  const escaped=value=>{const s=String(value??"");return /[,\"\r\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;};
  return [fields.join(","),...rows.map(r=>fields.map(k=>escaped(r[k])).join(","))].join("\n")+"\n";
}
function flatten(tree,prefix="",out=new Map()) {
  for(const [key,value] of Object.entries(tree)) {
    const full=prefix?prefix+"."+key:key;
    if(typeof value==="string")out.set(full,value);
    else if(value&&typeof value==="object")flatten(value,full,out);
  }
  return out;
}
function normalize(text){return String(text??"").replace(/\s+/g," ").trim();}
function scanPaths(folder,list=[]) {
  if(!existsSync(folder))return list;
  for(const entry of readdirSync(folder,{withFileTypes:true})) {
    const target=path.join(folder,entry.name);
    if(entry.isDirectory())scanPaths(target,list);
    else if(entry.isFile()&&/\.(tsx|ts|mjs)$/.test(target)&&!/\.(d|test|spec)\.ts$/.test(target))list.push(target);
  }
  return list;
}
function normalizeImportPath(sourceFile,target) {
  let stem;
  if(target.startsWith("@/"))stem=path.join(FRONTEND,target.slice(2));
  else if(target.startsWith("."))stem=path.resolve(path.dirname(sourceFile),target);
  else return [];
  return [stem,stem+".tsx",stem+".ts",stem+".mjs",path.join(stem,"index.tsx"),path.join(stem,"index.ts")].map(p=>path.relative(ROOT,p).replace(/\\/g,"/"));
}
export function indexSource(content,filename) {
  const translations=scanTranslationReferences(content,filename).resolved;
  const candidates=scanFileCandidates(content,filename);
  const sf=ts.createSourceFile(filename,content,ts.ScriptTarget.Latest,true,
    filename.endsWith(".tsx")?ts.ScriptKind.TSX:ts.ScriptKind.TS);
  const usedComponents=new Set();
  const imports=[];
  function visit(node) {
    if(ts.isJsxOpeningElement(node)||ts.isJsxSelfClosingElement(node))usedComponents.add(node.tagName.getText(sf).split(".")[0]);
    if(ts.isImportDeclaration(node)&&ts.isStringLiteral(node.moduleSpecifier)) {
      const names=[];
      const clause=node.importClause;
      if(clause?.name)names.push(clause.name.text);
      const bindings=clause?.namedBindings;
      if(bindings&&ts.isNamedImports(bindings))names.push(...bindings.elements.map(e=>e.name.text));
      imports.push({source:node.moduleSpecifier.text,names});
    }
    ts.forEachChild(node,visit);
  }
  visit(sf);
  const linked=imports.filter(i=>i.names.some(n=>usedComponents.has(n)))
    .flatMap(i=>normalizeImportPath(path.join(ROOT,filename),i.source));
  return {translations,candidates,linked:[...new Set(linked)]};
}
function technicalReason(row) {
  const text=normalize(row.original_text);
  if(row.category==="html_lang")return "HTML lang is a locale-controlled attribute, not translated copy";
  if(["locale_constant","locale_format"].includes(row.category))return "locale/formatter expression, not standalone interface copy";
  if(/^(?:xMidYMid meet|ocid1\.|arn:|[A-Z_][A-Z_0-9./-]+$)/.test(text))return "technical code or SVG property";
  if(/^(?:rotate\(|translate\(|scale\(|0 0 \$\{)/.test(text))return "SVG geometry expression";
  return null;
}
/** Every historical ID gets an evidence trail; catalog-only strings remain needs_review. */
export function reconcile(records,sources,ptCatalog,enCatalog,devGuard) {
  const pt=flatten(ptCatalog),en=flatten(enCatalog);
  const valueKeys=new Map();
  for(const [key,value] of pt){const text=normalize(value);if(!valueKeys.has(text))valueKeys.set(text,[]);valueKeys.get(text).push(key);}
  const index=new Map([...sources].map(([file,source])=>[file,indexSource(source,file)]));
  const output=[];const ids=new Set();
  for(const historic of records) {
    const r={...historic};
    if(ids.has(r.id))throw Error("Duplicate ID "+r.id);
    ids.add(r.id);
    for(const field of EXTRA_FIELDS)r[field]="";
    const file=r.historical_file,src=sources.get(file),facts=index.get(file),value=normalize(r.original_text);
    r.current_file=src===undefined?"":file;
    r.current_component=src===undefined?"":r.component;
    function result(status,strategy,confidence,evidence,pending="") {
      Object.assign(r,{status,match_strategy:strategy,verification_method:strategy,confidence,evidence,
        pending_action:pending,pending_verification:pending});
    }
    if(devGuard&&file.startsWith("frontend/app/dev/ui/")) {
      result("obsolete","production_route_guard","high",
        "frontend/app/dev/ui/layout.tsx: NODE_ENV production triggers notFound() for laboratory interface",
        "Confirm proxy/HTTP status in staging if relevant.");
    } else if(src===undefined) {
      result("needs_review","historical_path_missing","low",file+": source path absent",
        "Trace moved JSX, component imports or route removal for "+JSON.stringify(value)+".");
    } else if(r.category==="dynamic_backend"||r.category==="backend_message_key") {
      if(src.includes(value))result("external_content","backend_expression_trace","medium",
        file+": dynamic expression still present: "+value,
        "Verify upstream structured error code and frontend localization contract.");
      else result("needs_review","external_origin_unverified","low",
        file+": prior backend expression not found: "+value,
        "Trace current API error handling before excluding this historical record.");
    } else if(r.historical_translation_required==="no"&&technicalReason(r)) {
      result("non_translatable","technical_expression","medium",
        file+": "+technicalReason(r)+"; category "+r.category);
    } else {
      const literal=facts.candidates.find(c=>normalize(c.text)===value);
      if(r.historical_translation_required==="yes"&&literal) {
        r.current_line=String(literal.line);
        result("missing_translation","ast_visible_literal","high",
          file+": AST visible "+literal.kind+" literal "+JSON.stringify(value),
          "Localize verified rendered literal; confirm route and state prior to fix.");
      } else {
        const candidateKeys=valueKeys.get(value)||[];
        const direct=facts.translations.filter(t=>candidateKeys.includes(t.key));
        const indirect=facts.linked.flatMap(p=>(index.get(p)?.translations||[])
          .filter(t=>candidateKeys.includes(t.key)));
        const keys=[...new Set((direct.length?direct:indirect).map(t=>t.key))];
        if(keys.length===1) {
          const chosen=(direct.length?direct:indirect).find(t=>t.key===keys[0]);
          const key=chosen.key;const sameFile=direct.length>0;
          r.current_file=chosen.file||file;
          r.current_line=String(chosen.line);
          r.translation_namespace=key.includes(".")?key.slice(0,key.lastIndexOf(".")):"";
          r.translation_key=key;
          r.pt_br_value=pt.get(key)||"";
          r.en_us_value=en.get(key)||"";
          if(!en.has(key))result("partial_translation","missing_en_catalog_entry","high",
            r.current_file+": static translation reference "+key+" lacks en-US value",
            "Add en-US key with equivalent semantic meaning and ICU parameters.");
          else result("translated",sameFile?"ast_direct_exact_value":"ast_rendered_import_exact_value",
            sameFile?"high":"medium",
            r.current_file+": AST static call "+key+" and exact pt-BR value; en-US key present");
        } else {
          const reason=keys.length>1?"Multiple static keys match the value: "+keys.join(", "):
            candidateKeys.length?"Catalog text exists but static contextual use cannot be established":
            facts.translations.length?"Text likely moved, rewritten or parameterized; existing AST references require semantic check":
            "No direct translation reference; possible dynamic/helper/technical/obsolete text";
          result("needs_review","context_not_proven","low",file+": "+reason+"; original "+JSON.stringify(value),
            "Inspect source AST and rendered locale/state for "+JSON.stringify(value)+".");
        }
      }
    }
    output.push(r);
  }
  if(output.length!==records.length)throw Error("Historical inventory cardinality changed");
  return output;
}
function inventory() {
  const result=new Map();
  for(const folder of ["app","components","lib"])for(const file of scanPaths(path.join(FRONTEND,folder))) {
    result.set(path.relative(ROOT,file).replace(/\\/g,"/"),readFileSync(file,"utf8"));
  }
  return result;
}
export function validateEvidence(rows,sources,ptCatalog,enCatalog) {
  const pt=flatten(ptCatalog),en=flatten(enCatalog);
  const indexed=new Map([...sources].map(([f,s])=>[f,indexSource(s,f)]));
  for(const r of rows) {
    if(r.status!=="translated")continue;
    if(!r.translation_key)throw Error("Translated row lacks key "+r.id);
    if(!pt.has(r.translation_key)||!en.has(r.translation_key))throw Error("Catalog mismatch "+r.id);
    const refs=indexed.get(r.current_file)?.translations||[];
    if(!refs.some(ref=>ref.key===r.translation_key))throw Error("No AST source use: "+r.id);
  }
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  try {
    const {header,rows}=parseCsv(readFileSync(CSV,"utf8"));
    if(rows.length!==EXPECTED_IDS||new Set(rows.map(r=>r.id)).size!==EXPECTED_IDS)
      throw Error("Historical ID count/uniqueness violated (expected 2608)");
    const catalogs=Object.fromEntries(["pt-BR","en-US"].map(locale=>[locale,
      JSON.parse(readFileSync(path.join(FRONTEND,"i18n/messages",locale+".json"),"utf8"))]));
    const sources=inventory();
    const devGuard=/process\.env\.NODE_ENV\s*===\s*["']production["']\)\s*notFound\(\)/
      .test(sources.get("frontend/app/dev/ui/layout.tsx")||"");
    const generated=reconcile(rows,sources,catalogs["pt-BR"],catalogs["en-US"],devGuard);
    validateEvidence(generated,sources,catalogs["pt-BR"],catalogs["en-US"]);
    const fields=[...new Set([...header,...EXTRA_FIELDS])];
    const first=csvSerialize(generated,fields);
    const second=csvSerialize(reconcile(rows,sources,catalogs["pt-BR"],catalogs["en-US"],devGuard),fields);
    if(first!==second)throw Error("Non-deterministic reconciliation");
    const count=Object.fromEntries([...new Set(generated.map(r=>r.status))].sort()
      .map(status=>[status,generated.filter(r=>r.status===status).length]));
    console.log("[Aven 25.9A] "+JSON.stringify({ids:generated.length,statuses:count,sourceFiles:sources.size}));
    if(process.argv.includes("--write"))writeFileSync(CSV,first);
    else if(process.argv.includes("--check")) {
      const existing=parseCsv(readFileSync(CSV,"utf8")).rows;
      validateEvidence(existing,sources,catalogs["pt-BR"],catalogs["en-US"]);
    }
  } catch(error){console.error("[Aven 25.9A] "+String(error));process.exitCode=1;}
}

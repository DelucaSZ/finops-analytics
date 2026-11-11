import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  parseCsv, csvSerialize, indexSource, reconcile, validateEvidence, EXPECTED_IDS, EXTRA_FIELDS,
} from "../scripts/reconcile-i18n-baseline.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const historic = (overrides={}) => ({
  id:"I25-1-00001",module:"billing",route:"/billing",historical_file:"frontend/app/demo/page.tsx",
  historical_line:"10",component:"page",original_text:"Salvar",category:"jsx_text",
  historical_translation_required:"yes",status:"needs_review",evidence:"",pending_verification:"",...overrides,
});
const catalogs = {
  pt: {common:{save:"Salvar",other:"Outra ação",count:"{count} itens"}},
  en: {common:{save:"Save",other:"Other action",count:"{count} items"}},
};
function sample(source,rows=[historic()],extras=[],pt=catalogs.pt,en=catalogs.en) {
  const sources=new Map([["frontend/app/demo/page.tsx",source],...extras]);
  return reconcile(rows,sources,pt,en,false);
}
test("all 2608 historical IDs are preserved and unique",()=>{
  const csv=parseCsv(readFileSync(path.join(ROOT,"docs/i18n/25.9-coverage-reconciliation.csv"),"utf8"));
  assert.equal(csv.rows.length,EXPECTED_IDS);
  assert.equal(new Set(csv.rows.map(r=>r.id)).size,EXPECTED_IDS);
  assert.equal(csv.rows[0].id,"I25-1-00001");
  assert.equal(csv.rows.at(-1).id,"I25-1-02608");
  for(const k of EXTRA_FIELDS)assert.ok(csv.header.includes(k),k);
  assert.deepEqual(parseCsv(csvSerialize(csv.rows,csv.header)).rows,csv.rows);
});
test("exact catalog text is NOT proof without AST use",()=>{
  const [r]=sample("export function Page(){return <div>{'dynamic'}</div>}");
  assert.equal(r.status,"needs_review");
  assert.match(r.evidence,/Catalog text exists/);
});
test("direct AST reference with namespace and catalog pair provides translation evidence",()=>{
  const source='import {useTranslations} from "next-intl"; export function Page(){const t=useTranslations("common"); return <button>{t("save")}</button>}';
  const [r]=sample(source);
  assert.equal(r.status,"translated");
  assert.equal(r.translation_key,"common.save");
  assert.equal(r.match_strategy,"ast_direct_exact_value");
  assert.equal(r.en_us_value,"Save");
  assert.ok(r.evidence.includes("common.save"));
  validateEvidence([r],new Map([["frontend/app/demo/page.tsx",source]]),catalogs.pt,catalogs.en);
});
test("missing en-US catalog counterpart yields partial_translation",()=>{
  const source='export function Page(){const t=useTranslations("common"); return <p>{t("save")}</p>}';
  const [r]=sample(source,[historic()],[],catalogs.pt,{common:{other:"Other"}});
  assert.equal(r.status,"partial_translation");
});
test("visible JSX and presentation attributes remain actionable source defects",()=>{
  for(const source of ['export function Page(){return <button>Salvar</button>}',
    'export function Page(){return <input aria-label="Salvar" />}']) {
    const [r]=sample(source);
    assert.equal(r.status,"missing_translation");
    assert.equal(r.match_strategy,"ast_visible_literal");
  }
});
test("duplicate and inconsistent historical IDs are rejected",()=>{
  assert.throws(()=>sample("",[historic(),historic()]),/Duplicate ID/);
});
test("ICU parameterized references resolve structurally when original value matches",()=>{
  const s='export function Page(){const t=useTranslations("common"); return <div>{t("count",{count:2})}</div>}';
  const [r]=sample(s,[historic({original_text:"{count} itens"})]);
  assert.equal(r.translation_key,"common.count");
  assert.equal(r.status,"translated");
});
test("ambiguous same-text keys do not become translated",()=>{
  const pt={common:{save:"Salvar",saveAgain:"Salvar"}};
  const en={common:{save:"Save",saveAgain:"Save again"}};
  const s='function Page(){const t=useTranslations("common"); return <div>{t("save")}{t("saveAgain")}</div>}';
  const [r]=sample(s,[historic()],[],pt,en);
  assert.equal(r.status,"needs_review");
  assert.match(r.evidence,/Multiple static keys/);
});
test("a component rendered from a direct import can prove a moved label",()=>{
  const page='import {SharedWidget} from "@/components/shared-widget"; export function Page(){return <SharedWidget />}';
  const widget='export function SharedWidget(){const t=useTranslations("common"); return <span>{t("save")}</span>}';
  const [r]=sample(page,[historic()],[["frontend/components/shared-widget.tsx",widget]]);
  assert.equal(r.status,"translated");
  assert.equal(r.match_strategy,"ast_rendered_import_exact_value");
  assert.equal(r.current_file,"frontend/components/shared-widget.tsx");
});
test("non-rendered imports cannot prove translation usage",()=>{
  const page='import {SharedWidget} from "@/components/shared-widget"; export function Page(){return <span>Unrelated</span>}';
  const widget='export function SharedWidget(){const t=useTranslations("common"); return <span>{t("save")}</span>}';
  const [r]=sample(page,[historic()],[["frontend/components/shared-widget.tsx",widget]]);
  assert.equal(r.status,"needs_review");
});
test("SVG/code snippets remain technical, while English UI copy is not exempted",()=>{
  const [technical]=sample('function Page(){return <svg preserveAspectRatio="xMidYMid meet" />}',
    [historic({original_text:"xMidYMid meet",category:"attribute",historical_translation_required:"no"})]);
  assert.equal(technical.status,"non_translatable");
  const [ui]=sample('function Page(){return <p>Failed</p>}',
    [historic({original_text:"Failed",category:"jsx_text"})]);
  assert.equal(ui.status,"missing_translation");
});
test("backend field is external only with verified source expression",()=>{
  const [yes]=sample("function Page(){return <p>{error.message}</p>}",
    [historic({original_text:"error.message",category:"dynamic_backend",historical_translation_required:"no"})]);
  assert.equal(yes.status,"external_content");
  const [unknown]=sample("function Page(){return <p>{message}</p>}",
    [historic({original_text:"error.message",category:"dynamic_backend",historical_translation_required:"no"})]);
  assert.equal(unknown.status,"needs_review");
});
test("production-blocked development laboratory is out of production i18n scope",()=>{
  const s="export default function Page(){return <h1>Test lab</h1>}";
  const source=new Map([["frontend/app/dev/ui/page.tsx",s]]);
  const row=historic({historical_file:"frontend/app/dev/ui/page.tsx"});
  assert.equal(reconcile([row],source,catalogs.pt,catalogs.en,true)[0].status,"obsolete");
  assert.equal(reconcile([row],source,catalogs.pt,catalogs.en,false)[0].status,"needs_review");
});
test("repeated reconciliation is deterministic and never rewrites technical inputs",()=>{
  const s='export function Page(){const t=useTranslations("common");return <div>{t("save")}</div>}';
  const inputs=[historic()];const sources=new Map([["frontend/app/demo/page.tsx",s]]);
  const first=reconcile(inputs,sources,catalogs.pt,catalogs.en,false);
  const second=reconcile(inputs,sources,catalogs.pt,catalogs.en,false);
  assert.deepEqual(first,second);
  assert.equal(inputs[0].status,"needs_review");
  assert.equal(indexSource(s,"frontend/app/demo/page.tsx").translations[0].key,"common.save");
});

test("historical JSX-scanner false positives are technical, even when baseline said yes",()=>{
  const examples=["(): SectionState",'0 ? "up" : variation.percent',"0 && total",
    "sa-east-1, us-east-1","sa-saopaulo-1, us-ashburn-1","aa:bb:cc:...",
    "UI","API","MFA","api","occurred_at","CollectionRun",
    "extends Omit","= SelectorCommonProps","= 1 && value",": costError ?",
    ": runIds.length === 0 ?","0 && absolute"];
  for(let i=0;i<examples.length;i++) {
    const [r]=sample("export function Page(){return <section />} ",[
      historic({id:"I25-1-"+String(i+1).padStart(5,"0"),original_text:examples[i],category:"jsx_text"})
    ]);
    assert.equal(r.status,"non_translatable",examples[i]);
  }
});
test("real visible user-facing labels remain gaps, not technical exclusions",()=>{
  for(const text of ["AWS Account ID","External ID","Correlation ID",
    "Anterior","Próxima","Perfil","Executar coleta","Fingerprint"]) {
    const [r]=sample("export function Page(){return <p>"+text+"</p>}",[historic({original_text:text})]);
    assert.equal(r.status,"missing_translation",text);
  }
});

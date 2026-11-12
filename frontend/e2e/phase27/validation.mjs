import assert from "node:assert/strict";

// Task 27.6: actual Chromium against the production Next build, isolated pricing
// contracts and deterministic responses. No live cloud prices, IAM or database writes.
const SIZES = [
  {width:1920,height:1080},{width:1440,height:900},{width:1366,height:768},
  {width:1280,height:800},{width:1024,height:768},{width:768,height:1024},
  {width:390,height:844},{width:360,height:780},
];
const LOCALES = ["pt-BR","en-US"];
const BASE_ROUTE = "/calculator";
const clean = value => value.replace(/[^a-zA-Z0-9_-]/g,"_");

async function selectValue(page,value) {
  const field=page.locator("main select[data-aven-native-select]")
    .filter({has:page.locator('option[value="'+value+'"]')}).first();
  await field.waitFor({state:"attached"});
  await field.selectOption(value);
  assert.equal(await field.inputValue(),value);
}
async function chooseRegion(page,provider) {
  if (provider==="aws") {
    await page.locator('main option[value="sa-east-1"]').first().waitFor({state:"attached"});
    await selectValue(page,"sa-east-1");
  } else {
    await page.locator('main input[type="text"]').first().fill("sa-saopaulo-1");
  }
}
async function checkDropdown(page,width,height) {
  const field=page.locator('main [data-aven-select] [role="combobox"]:not([disabled])').first();
  await field.focus();
  await field.press("ArrowDown");
  assert.equal(await field.getAttribute("aria-expanded"),"true");
  const list=page.getByRole("listbox").last();
  await list.waitFor({state:"visible"});
  await page.waitForFunction(()=>Boolean(document.querySelector('[role="listbox"][data-positioned="true"]')));
  const rect=await list.boundingBox();
  assert.ok(rect && rect.width>40 && rect.x>=-2 && rect.y>=-2
    && rect.x+rect.width<=width+2 && rect.y+rect.height<=height+2,
    "Aven dropdown clipped: "+JSON.stringify(rect));
  await field.press("Escape");
  await list.waitFor({state:"hidden"});
}
async function checkLayout(page,viewport,locale,theme) {
  assert.equal(await page.locator("html").getAttribute("lang"),locale);
  assert.equal(await page.locator("html").getAttribute("data-theme-preference"),theme);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+3);
  assert.equal(overflow,false,"global horizontal overflow at "+viewport.width+"px");
  assert.equal(await page.locator("main select:not([data-aven-native-select])").count(),0,
    "native unstyled select found");
  const results=page.getByRole("status").filter({has:page.locator('[aria-atomic="true"]')});
  // The calculator has its own live status announcement; other shell statuses may coexist.
  assert.ok(await page.locator('main [role="status"][aria-live="polite"]').count()>0,
    "calculator estimate status is not announced");
  await checkDropdown(page,viewport.width,viewport.height);
}
async function visitCase(deps,{locale,viewport,theme="light",scheme="light",collapsed=false,scenario}) {
  const {createContext,visit,watch,report,fail,out}=deps;
  const {ctx,requests}=await createContext(locale,{viewport,colorScheme:scheme,theme});
  const page=await ctx.newPage(),errors=[];
  watch(page,errors);
  const record={route:BASE_ROUTE,locale,viewport:viewport.width,theme,collapsed,scenario,
    status:"not_run",pageErrors:errors};
  report.cases.push(record);
  try{
    await visit(page,BASE_ROUTE,locale,record);
    await checkLayout(page,viewport,locale,theme);
    if(collapsed && viewport.width>850) {
      const before=await page.locator("main").boundingBox();
      await page.locator('button[aria-controls="aven-desktop-sidebar"]').click();
      await page.waitForFunction(()=>document.documentElement.dataset.sidebar==="collapsed");
      const after=await page.locator("main").boundingBox();
      assert.ok(after && before && after.width>=before.width,
        "calculator content did not expand when sidebar collapsed");
    }
    assert.deepEqual(errors,[],"browser runtime errors");
    record.unknownEndpoints=requests.filter(r=>r.unsupported).map(r=>r.path);
    assert.deepEqual(record.unknownEndpoints,[],"missing fixture endpoints");
    await page.screenshot({path:out+"/calculator-"+scenario+"-"+locale+"-"+theme+"-"+viewport.width+
      (collapsed?"-collapsed":"")+".png",animations:"disabled",fullPage:true});
    record.status="passed";
  }catch(error){fail(record,error)}
  finally{await page.close();await ctx.close()}
}
async function priceCase(deps,{locale,provider,service,convert=false,scenario}) {
  const {createContext,visit,watch,report,fail,out}=deps;
  const viewport={width:1366,height:768};
  const {ctx,requests}=await createContext(locale,{viewport,colorScheme:"dark",theme:"dark"});
  const page=await ctx.newPage(),errors=[];
  watch(page,errors);
  const record={route:BASE_ROUTE,locale,scenario,provider,service,convert,
    status:"not_run",pageErrors:errors};
  report.cases.push(record);
  try{
    await visit(page,BASE_ROUTE,locale,record);
    if(provider==="oci")await selectValue(page,"oci");
    await chooseRegion(page,provider);
    if(service==="rds" || service==="db_system")await selectValue(page,service);
    if(provider==="aws"){
      await page.locator('main input[type="text"]').first().fill(service==="rds"?"db.t3":"t3");
      await page.locator('main option[value="'+(service==="rds"?"db.t3.medium":"t3.medium")+'"]').first()
        .waitFor({state:"attached"});
      await selectValue(page,service==="rds"?"db.t3.medium":"t3.medium");
      await selectValue(page,service==="rds"?"single-az":"linux");
      if(convert){
        await page.getByLabel(locale==="pt-BR"?"Desconto (%)":"Discount (%)").fill("10");
        await page.getByRole("switch",{name:locale==="pt-BR"?"Converter para BRL":"Convert to BRL"}).click();
        await page.getByLabel(locale==="pt-BR"?"Dólar (USD/BRL)":"USD/BRL exchange rate").fill("5,0");
      }
    } else if(service==="compute") {
      await page.locator('main option[value="VM.Standard.E5.Flex"]').first().waitFor({state:"attached"});
      await selectValue(page,"VM.Standard.E5.Flex");
      await selectValue(page,"linux");
    } else if(service==="db_system") {
      await page.getByText(locale==="pt-BR"?"Preços de DB System pendentes":"DB System prices pending")
        .waitFor({state:"visible"});
    }
    await page.getByRole("button",{name:locale==="pt-BR"?"Calcular custo":"Calculate cost"}).click();
    const expected=provider==="aws"
      ? convert ? "508" : "100" : service==="db_system" ? "72" : "300";
    await page.waitForFunction(value=>document.querySelector("main")?.innerText.includes(value),expected);
    const estimate=requests.filter(r=>r.method==="POST" && r.path==="/calculator/estimate");
    assert.equal(estimate.length,1,"calculator did not send exactly one estimate request");
    assert.equal(estimate[0].payload.provider,provider);
    assert.equal(estimate[0].payload.resource_configuration.service,service);
    assert.equal(estimate[0].payload.aws_financial===undefined,provider==="oci",
      "OCI must never send AWS financial adjustments");
    if(convert){
      assert.equal(estimate[0].payload.aws_financial.discount_percent,"10");
      assert.equal(estimate[0].payload.aws_financial.usd_brl_rate,"5.0");
      assert.equal(estimate[0].payload.aws_financial.tax_percent,"13");
      assert.equal(estimate[0].payload.aws_financial.conversion_enabled,true);
    }
    const displayed=await page.locator("main").innerText();
    if(service==="db_system"){
      assert.ok(displayed.includes("72"),"known subtotal missing");
      assert.ok(!displayed.includes("300,10") && !displayed.includes("300.10"),
        "a complete OCI total was invented");
      assert.ok(await page.locator('main [title^="DB_LICENSE_"]').count()>0,
        "the missing SKU is not exposed in full");
    } else if(convert){
      assert.match(displayed,/508[.,]50/,"backend BRL result missing");
    }
    assert.ok(await page.locator('main [title^="ocid1."]').count()>0,
      "full-length technical SKU tooltip unavailable");
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+3),false,
      "priced result has global horizontal overflow");
    assert.deepEqual(errors,[],"calculator browser runtime errors");
    assert.deepEqual(requests.filter(r=>r.unsupported).map(r=>r.path),[],
      "missing isolated calculator fixture");
    await page.screenshot({path:out+"/calculator-"+scenario+"-"+locale+".png",animations:"disabled",fullPage:true});
    record.status="passed";
  }catch(error){fail(record,error)}
  finally{await page.close();await ctx.close()}
}
async function invalidCase(deps,locale) {
  const {createContext,visit,report,fail}=deps;
  const {ctx,requests}=await createContext(locale);
  const page=await ctx.newPage();
  const record={route:BASE_ROUTE,locale,scenario:"accessible-field-errors",status:"not_run"};
  report.cases.push(record);
  try {
    await visit(page,BASE_ROUTE,locale,record);
    await chooseRegion(page,"aws");
    await page.getByLabel(locale==="pt-BR"?"Desconto (%)":"Discount (%)").fill("101");
    await page.getByRole("button",{name:locale==="pt-BR"?"Calcular custo":"Calculate cost"}).click();
    assert.equal(requests.some(r=>r.method==="POST"&&r.path==="/calculator/estimate"),false,
      "invalid financial inputs reached the backend");
    const error=page.locator('main [aria-invalid="true"]').first();
    await error.waitFor({state:"visible"});
    assert.ok(await error.getAttribute("aria-describedby"),
      "field error not associated with the invalid control");
    record.status="passed";
  }catch(error){fail(record,error)}
  finally{await page.close();await ctx.close()}
}
async function localeSwitchCase(deps,locale) {
  const {createContext,visit,report,fail,out}=deps;
  const other=locale==="pt-BR"?"en-US":"pt-BR";
  const {ctx,requests}=await createContext(locale,{viewport:{width:1440,height:900},theme:"dark",colorScheme:"dark"});
  const page=await ctx.newPage();
  const record={route:BASE_ROUTE,locale,scenario:"locale-change-with-preserved-quote",status:"not_run"};
  report.cases.push(record);
  try {
    await visit(page,BASE_ROUTE,locale,record);
    await chooseRegion(page,"aws");
    await page.locator('main input[type="text"]').first().fill("t3");
    await page.locator('main option[value="t3.medium"]').first().waitFor({state:"attached"});
    await selectValue(page,"t3.medium");
    await selectValue(page,"linux");
    await page.getByLabel(locale==="pt-BR"?"Desconto (%)":"Discount (%)").fill("10");
    await page.getByRole("switch",{name:locale==="pt-BR"?"Converter para BRL":"Convert to BRL"}).click();
    await page.getByLabel(locale==="pt-BR"?"Dólar (USD/BRL)":"USD/BRL exchange rate").fill("5,0");
    await page.getByRole("button",{name:locale==="pt-BR"?"Calcular custo":"Calculate cost"}).click();
    await page.waitForFunction(()=>document.querySelector("main")?.innerText.includes("508"));
    await page.getByRole("button",{name:/^(Idioma|Language):/}).click();
    await page.getByRole("menuitemradio",{name:other==="en-US"?/English/:/Português/}).click();
    await page.waitForFunction(expected=>document.documentElement.lang===expected,other);
    assert.equal(await page.locator("html").getAttribute("data-theme-preference"),"dark");
    assert.equal(await page.locator('main select[data-aven-native-select]').filter({
      has:page.locator('option[value="t3.medium"]'),
    }).first().inputValue(),"t3.medium","instance selection lost across locale change");
    assert.equal(await page.getByLabel(other==="pt-BR"?"Desconto (%)":"Discount (%)").inputValue(),"10");
    assert.equal(await page.getByLabel(other==="pt-BR"?"Dólar (USD/BRL)":"USD/BRL exchange rate").inputValue(),"5,0");
    assert.equal(await page.getByRole("switch",{name:other==="pt-BR"?"Converter para BRL":"Convert to BRL"}).getAttribute("aria-checked"),"true");
    const text=await page.locator("main").innerText();
    assert.match(text,/R\\$\\s*508[.,]50/,"locale change altered currency or lost quoted total");
    assert.equal(requests.filter(r=>r.method==="POST"&&r.path==="/calculator/estimate").length,1,
      "locale switch unexpectedly recalculated quote");
    await page.screenshot({path:out+"/calculator-locale-switch-"+locale+"-to-"+other+".png",
      animations:"disabled",fullPage:true});
    record.status="passed";
  }catch(error){fail(record,error)}
  finally{await page.close();await ctx.close()}
}
export async function runPhase27(deps) {
  for(const locale of LOCALES){
    for(const viewport of SIZES) {
      await visitCase(deps,{locale,viewport,scenario:"responsive"});
      if(viewport.width>=1024)await visitCase(deps,{
        locale,viewport,collapsed:true,scenario:"sidebar",
      });
    }
    for(const theme of ["dark","system"])for(const width of [1366,390]){
      await visitCase(deps,{locale,viewport:SIZES.find(v=>v.width===width),
        theme,scheme:"dark",scenario:"themes"});
    }
    await priceCase(deps,{locale,provider:"aws",service:"ec2",scenario:"aws-ec2-usd"});
    await priceCase(deps,{locale,provider:"aws",service:"ec2",convert:true,scenario:"aws-ec2-brl"});
    await priceCase(deps,{locale,provider:"aws",service:"rds",scenario:"aws-rds"});
    await priceCase(deps,{locale,provider:"oci",service:"compute",scenario:"oci-compute"});
    await priceCase(deps,{locale,provider:"oci",service:"db_system",scenario:"oci-db-partial"});
    await invalidCase(deps,locale);
    await localeSwitchCase(deps,locale);
  }
}

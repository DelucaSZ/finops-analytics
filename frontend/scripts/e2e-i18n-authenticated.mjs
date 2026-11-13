import assert from 'node:assert/strict';
import {existsSync,mkdirSync,mkdtempSync,readFileSync,rmSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createServer as httpsServer} from 'node:https';
import {request as httpRequest} from 'node:http';
import {execFileSync,spawn} from 'node:child_process';
import {setTimeout as delay} from 'node:timers/promises';
import {chromium} from 'playwright-core';
import {apiFixture,FIXTURE_FINANCIAL} from '../e2e/i18n/fixtures.mjs';
import {PROTECTED_ROUTES,PUBLIC_ROUTES,TECHNICAL_ROUTES,INVENTORIED_COUNT} from '../e2e/i18n/routes.mjs';
import {runPhase26} from '../e2e/phase26/validation.mjs';
import {runPhase26Extensions} from '../e2e/phase26/extended-validation.mjs';
import {calculatorFixture} from '../e2e/phase27/fixtures.mjs';
import {runPhase27} from '../e2e/phase27/validation.mjs';

// Real Chromium + production Next build. Only API responses are simulated.
// Usage: node scripts/e2e-i18n-authenticated.mjs --smoke | --full
const full = process.argv.includes('--full');
const phase26 = process.argv.includes('--phase26');
const phase27 = process.argv.includes('--phase27');
const PORT = Number(process.env.AVEN_E2E_PORT||3239);
const TLS_PORT=PORT+1,BASE='https://localhost:'+TLS_PORT,UPSTREAM='http://127.0.0.1:'+PORT;
const OUT=phase26?'artifacts/phase26':phase27?'artifacts/phase27':'artifacts/i18n-authenticated', START=Date.now();
const browserBin=process.env.CHROME_BIN||['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium'].find(existsSync);
if(!browserBin)throw new Error('Chromium not installed; do not report this as a passed browser QA');
mkdirSync(OUT,{recursive:true});
const tlsDir=mkdtempSync(join(tmpdir(),'aven-25-9b-'));
const key=join(tlsDir,'key.pem'),cert=join(tlsDir,'cert.pem');
execFileSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-keyout',key,
  '-out',cert,'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],{stdio:'ignore'});
const proxy=httpsServer({key:readFileSync(key),cert:readFileSync(cert)},(request,response)=>{
  const upstream=httpRequest({hostname:'127.0.0.1',port:PORT,path:request.url,method:request.method,
    headers:{...request.headers,host:'localhost:'+TLS_PORT,
      'x-forwarded-host':'localhost:'+TLS_PORT,'x-forwarded-proto':'https'}},remote=>{
    response.writeHead(remote.statusCode??502,remote.headers);remote.pipe(response);
  });
  upstream.on('error',err=>{if(!response.headersSent)response.writeHead(502);response.end(String(err))});
  request.pipe(upstream);
});
let server, browser;
const report={task:phase27?'27.6':phase26?'26.3':'25.9B',
  mode:phase27?'phase27':phase26?'phase26':full?'full':'smoke',backend:'simulated',
  commit:process.env.GITHUB_SHA||'local',
  inventory:{total:INVENTORIED_COUNT,protected:PROTECTED_ROUTES.length,public:PUBLIC_ROUTES.length,
    technical:TECHNICAL_ROUTES.length},
  cases:[],failures:[],limitations:[],started:new Date().toISOString()};
const toSlug=(path)=>path==='/'?'dashboard':path.replaceAll('/','_').replace(/[^a-z0-9_-]/gi,'_');
const timeout=full?12000:10000;
const setLang=async(context,locale)=>context.addCookies([{name:'aven.locale',value:locale,url:BASE}]);
const selector=page=>page.getByRole('button',{name:/^(?:Idioma|Language):/});
function fail(record,error){
  record.status='failed';record.error=String(error?.stack||error);
  report.failures.push({route:record.route,locale:record.locale,scenario:record.scenario,error:String(error)});
}
async function createContext(locale,{viewport={width:1440,height:900},colorScheme='light',theme=null,longIdentity=false,manyAccounts=false,emptyBillingProfiles=false}={}){
  const ctx=await browser.newContext({viewport,ignoreHTTPSErrors:true,
    timezoneId:'America/Sao_Paulo',reducedMotion:'reduce',colorScheme});
  if(theme)await ctx.addInitScript(preference=>{localStorage.setItem('deepops.theme',preference)},theme);
  await setLang(ctx,locale);
  const requests=[];
  await ctx.route('**/api/v1/**',async route=>{
    const req=route.request(),url=new URL(req.url()),path=url.pathname.replace(/^\/api\/v1/,'')+url.search;
    let body=null;try{body=req.postDataJSON()}catch{}
    const fixture=(phase27 ? calculatorFixture(path,req.method(),body) : null)
      ?? apiFixture(path,req.method(),body);
    if(emptyBillingProfiles && path==='/billing/aws/profiles' && req.method()==='GET' && fixture.status===200)fixture.body=[];
    if(manyAccounts && path==='/cloud-accounts' && req.method()==='GET' && fixture.status===200){
      const original=fixture.body.find(account=>account.provider==='aws');
      fixture.body=[...fixture.body,...Array.from({length:14},(_,index)=>({
        ...original,id:index+3,provider:'aws',native_account_id:String(100000000003+index),
        name:'QA Additional AWS '+String(index+3).padStart(2,'0')
      }))];
    }
    if(longIdentity&&path==='/auth/me'&&req.method()==='GET'&&fixture.status===200){
      fixture.body={...fixture.body,name:'QA Account With An Exceptionally Long Display Name For Topbar Validation',
        full_name:'QA Account With An Exceptionally Long Display Name For Topbar Validation',
        email:'topbar-layout-regression-very-long-user-identity@example.test'};
    }
    requests.push({method:req.method(),path,status:fixture.status,unsupported:!!fixture.unsupported,
      payload:body});
    await route.fulfill({status:fixture.status,contentType:'application/json',
      headers:{'access-control-allow-origin':BASE,'access-control-allow-credentials':'true'},
      body:JSON.stringify(fixture.body)});
  });
  return {ctx,requests};
}
function watch(page,errors){
  page.on('pageerror',error=>errors.push('pageerror: '+error.message));
  page.on('console',message=>{
    if(message.type()!=='error')return;
    const location=message.location()?.url||'';
    if(location.includes('/api/v1/')&&/503|403/.test(message.text()))return;
    errors.push('console: '+message.text().slice(0,500));
  });
}
async function visit(page,route,locale,record,{screenshot=false}={}){
  const response=await page.goto(BASE+route,{waitUntil:'domcontentloaded',timeout:timeout});
  assert.ok(response&&response.status()<500,'SSR failed: '+route+' HTTP '+response?.status());
  await page.waitForFunction(expected=>document.documentElement.lang===expected,locale,{timeout});
  await selector(page).waitFor({state:'visible',timeout});
  assert.equal(new URL(page.url()).pathname,new URL(route,BASE).pathname,'protected route redirected or navigated away');
  await page.locator('h1').first().waitFor({state:'visible',timeout});
  const content=await page.locator('body').innerText();
  assert.ok(content.trim().length>35,'page has no visible content');
  assert.doesNotMatch(content,/MISSING_MESSAGE|MISSING_TRANSLATION|FORMAT_ERROR|\{[a-zA-Z]+\}/,
    'unresolved translation or ICU placeholder');
  const checked=await page.locator('html').getAttribute('lang');
  assert.equal(checked,locale);
  record.heading=(await page.locator('h1').first().innerText()).slice(0,150);
  if(screenshot)await page.screenshot({path:OUT+'/'+toSlug(route)+'-'+locale+'-1440.png',
    fullPage:true,animations:'disabled'});
}
async function routeSuite(locale){
  const {ctx,requests}=await createContext(locale);
  try{
    for(const route of PROTECTED_ROUTES){
      const record={route,locale,scenario:'authenticated-navigation',status:'not_run',
        fixture:'browser E2E with simulated backend',unknownEndpoints:[],pageErrors:[]};
      report.cases.push(record);
      const page=await ctx.newPage();
      watch(page,record.pageErrors);
      const offset=requests.length;
      try{
        await visit(page,route,locale,record,{screenshot:full});
        await page.waitForTimeout(550); // allow the domain queries to settle
        const seen=requests.slice(offset);
        assert.ok(seen.some(r=>r.path==='/auth/me'&&r.status===200),
          'protected route did not exercise authenticated identity fixture');
        record.requests=seen.length;
        record.unknownEndpoints=seen.filter(r=>r.unsupported).map(r=>r.method+' '+r.path);
        // This scenario asserts mounting and SSR only, NOT successful business API semantics.
        assert.deepEqual(record.pageErrors,[],'unexpected browser errors');
        record.status=record.unknownEndpoints.length?'blocked':'passed';
        if(record.status==='blocked')report.limitations.push({
          route,locale,reason:'API contract fixture not implemented',endpoints:record.unknownEndpoints
        });
      }catch(error){fail(record,error)}
      finally{await page.close()}
    }
  }finally{await ctx.close()}
}
async function scenario(locale,route,action){
  const {ctx,requests}=await createContext(locale);
  const record={route,locale,scenario:'locale-switch-functional',status:'not_run',
    fixture:'domain success and explicit unsupported-response fixtures',pageErrors:[]};
  report.cases.push(record);
  const page=await ctx.newPage();watch(page,record.pageErrors);
  try{
    await visit(page,route,locale,record);
    await page.waitForTimeout(700);
    await action(page,requests);
    const formState=await page.locator('main select').evaluateAll(elements=>
      Object.fromEntries(elements.filter(el=>el.id).map(el=>[el.id,el.value])));
    const beforeUrl=new URL(page.url());
    const beforePath=beforeUrl.pathname,beforeSearch=beforeUrl.search;
    const requestCheckpoint=requests.length;
    const beforePayloads=requests.filter(r=>r.status===200&&
      /^(\/billing\/aws\/|\/inventory\/resources|\/finops\/flow\/|\/opportunities\?|\/rds\/reservations-dashboard\/)/.test(r.path))
      .map(r=>({method:r.method,path:r.path,payload:r.payload}));
    await page.evaluate(()=>{window.__avenQaPreserved='25.9B'});
    const other=locale==='pt-BR'?'en-US':'pt-BR';
    await selector(page).click();
    await page.getByRole('menuitemradio',{name:other==='en-US'?/English/:/Português/}).click();
    await page.waitForFunction(expected=>document.documentElement.lang===expected,other,{timeout});
    assert.equal(new URL(page.url()).pathname,beforePath,'locale switch changed route');
    const afterQuery=new URL(page.url()).searchParams;
    const beforeQuery=new URLSearchParams(beforeSearch);
    // Billing writes its default profile to history.replaceState, while
    // Next router.refresh can restore the originally supplied URL. A missing
    // implicit default is semantically equivalent; explicit user filters are not.
    if(route.startsWith('/billing') && !new URL(route,BASE).searchParams.has('profile')
      && beforeQuery.get('profile')==='qa-profile')beforeQuery.delete('profile');
    for(const [key,value] of beforeQuery)
      assert.equal(afterQuery.get(key),value,'locale switch dropped explicit filter '+key);
    for(const [key,value] of afterQuery)
      assert.ok(beforeQuery.get(key)===value||
        (key==='profile'&&value==='qa-profile'&&route.startsWith('/billing')),
        'locale switch introduced unexpected filter '+key);
    const afterFormState=await page.locator('main select').evaluateAll(elements=>
      Object.fromEntries(elements.filter(el=>el.id).map(el=>[el.id,el.value])));
    // Newly mounted paging controls may appear asynchronously after a query;
    // compare only existing select IDs, not an unstable positional DOM array.
    for(const [id,value] of Object.entries(formState))
      assert.equal(afterFormState[id],value,
        'locale switch reset selected filter '+id);
    assert.equal(await page.evaluate(()=>window.__avenQaPreserved),'25.9B',
      'locale switch remounted client state');
    assert.equal((await ctx.cookies(BASE)).find(c=>c.name==='aven.locale')?.value,other);
    assert.deepEqual(record.pageErrors,[],'runtime errors after locale switch');
    const afterPayloads=requests.slice(requestCheckpoint).filter(r=>r.status===200&&
      /^(\/billing\/aws\/|\/inventory\/resources|\/finops\/flow\/|\/opportunities\?|\/rds\/reservations-dashboard\/)/.test(r.path))
      .map(r=>({method:r.method,path:r.path,payload:r.payload}));
    // A locale may refetch business queries, but must not change their technical parameters.
    for(const next of afterPayloads){
      const previous=beforePayloads.find(p=>p.path===next.path&&p.method===next.method);
      if(previous)assert.deepEqual(next.payload,previous.payload,'locale modified a business request');
    }
    record.payloadsBefore=beforePayloads.length;
    record.payloadsAfter=afterPayloads.length;
    record.unexpectedBackend= requests.filter(r=>r.unsupported).map(r=>r.path);
    await page.reload({waitUntil:'domcontentloaded'});
    await page.waitForFunction(expected=>document.documentElement.lang===expected,other,{timeout});
    assert.equal((await ctx.cookies(BASE)).find(c=>c.name==='aven.locale')?.value,other,
      'cookie not persisted across reload');
    record.status=record.unexpectedBackend.length?'blocked':'passed';
    if(record.status==='blocked')report.limitations.push({
      route,locale,reason:'functional scenario lacks API contract fixtures',endpoints:record.unexpectedBackend
    });
  }catch(error){fail(record,error)}
  finally{await page.close();await ctx.close()}
}
async function runFunctional(){
  for(const locale of ['pt-BR','en-US']){
    await scenario(locale,'/billing?period=custom&from=2026-10-01&to=2026-10-31&accounts=1',
      async(page,requests)=>{
        await page.waitForFunction(()=>document.body.innerText.includes('FinOps'),null,{timeout});
        assert.ok(requests.some(r=>r.path.startsWith('/billing/aws/summary')&&r.status===200),
          'billing financial fixture was not consumed');
        assert.ok(requests.filter(r=>r.path==='/billing/aws/summary')
          .every(r=>r.payload?.account_ids?.includes(1)), 'billing account ID altered');
        assert.ok((await page.locator('body').innerText()).includes(
          new Intl.NumberFormat(locale,{minimumFractionDigits:2,maximumFractionDigits:2})
            .format(Number(FIXTURE_FINANCIAL.billingAmount))),'billing amount missing from UI');
      });
    await scenario(locale,'/inventory',async(page,requests)=>{
      await page.getByText('QA compute 1').first().waitFor({timeout});
      const search=page.getByRole('textbox').first();
      await search.fill('qa-resource');
      await page.waitForTimeout(450);
      assert.ok(requests.some(r=>r.path.includes('/inventory/resources?')&&
        r.path.includes('search=qa-resource')),'inventory search not sent to API');
    });
    await scenario(locale,'/settings/pricing/aws',async(page,requests)=>{
      await page.getByText('Fixture only · EC2 Linux shared').first().waitFor({timeout});
      assert.ok(requests.some(r=>r.path.includes('/pricing/aws/rates?')&&
        r.path.includes('region=sa-east-1')&&r.status===200),
        'AWS pricing catalog fixture was not fetched for São Paulo');
      const rateText=locale==='pt-BR'?'0,00425000':'0.00425000';
      assert.ok((await page.locator('body').innerText()).includes(rateText),
        'precise AWS price not displayed');
      const region=page.locator('[data-aven-select]').filter({
        has:page.locator('option[value="us-east-1"]')
      }).getByRole('combobox');
      await region.click();
      await page.getByRole('option',{name:'us-east-1',exact:true}).click();
      await page.waitForFunction(()=>
        document.body.innerText.includes(document.documentElement.lang==='pt-BR'?'0,00250000':'0.00250000'),
        null,{timeout});
      assert.ok(requests.some(r=>r.path.includes('/pricing/aws/rates?')&&
        r.path.includes('region=us-east-1')&&r.status===200),
        'AWS pricing selection did not request the new region');
      assert.ok(!(await page.locator('body').innerText()).includes(rateText),
        'AWS pricing reused the previous region rate');
      await page.getByRole('button',{name:locale==='pt-BR'?'Detalhes':'Details'}).first().click();
      await page.getByRole('dialog').getByText('QA-EC2-HOUR').first().waitFor({timeout});
      await page.getByRole('dialog').getByRole('button',{name:locale==='pt-BR'?'Fechar':'Close'}).click();
    });
    await scenario(locale,'/flow',async(page,requests)=>{
      await page.locator('h3').first().waitFor({timeout});
      const previousSummaryRequests=requests.filter(r=>r.path.startsWith('/finops/flow/summary')).length;
      const first=page.locator('select').first();
      const trigger=page.locator('[data-aven-select] [role="combobox"]').first();
      await trigger.focus();
      await trigger.press('ArrowDown');
      assert.equal(await trigger.getAttribute('aria-expanded'),'true',
        'Aven dropdown did not open from keyboard');
      const list=page.getByRole('listbox');
      await list.waitFor({state:'visible',timeout});
      const bounds=await list.boundingBox();
      assert.ok(bounds&&bounds.x>=0&&bounds.y>=0&&bounds.x+bounds.width<=1441,
        'Aven dropdown escaped the viewport');
      await trigger.press('Escape');
      assert.equal(await trigger.getAttribute('aria-expanded'),'false',
        'Aven dropdown did not close with Escape');
      await trigger.click();
      const label=(await first.locator('option[value="previous_month"]').textContent())?.trim();
      assert.ok(label,'period option label is empty');
      await page.getByRole('option',{name:label,exact:true}).click();
      assert.equal(await first.inputValue(),'previous_month',
        'Aven dropdown failed to retain the native filter value');
      // The first render still contains the old period; wait for the new API cycle
      // before checking the finalized UI rather than matching a stale value.
      for(let attempt=0;attempt<30;attempt++){
        if(requests.filter(r=>r.path.startsWith('/finops/flow/summary')).length>previousSummaryRequests)break;
        await page.waitForTimeout(100);
      }
      const summaryRequests=requests.filter(r=>r.path.startsWith('/finops/flow/summary'));
      assert.ok(summaryRequests.length>previousSummaryRequests,
        'custom dropdown did not request updated Flow summary');
      assert.ok(summaryRequests.at(-1).status===200,
        'custom dropdown Flow refresh failed');
      await page.waitForTimeout(450);
      const expected=new Intl.NumberFormat(locale,{
        minimumFractionDigits:2,maximumFractionDigits:2
      }).format(Number(FIXTURE_FINANCIAL.estimatedSavings));
      assert.ok((await page.locator('body').innerText()).includes(expected),
        'flow savings disappeared after selection; latest requests: '+
        JSON.stringify(summaryRequests.slice(-2)));
    });
    await scenario(locale,'/opportunities',async(page,requests)=>{
      await page.getByText('QA opportunity').first().waitFor({timeout});
      const severity=page.locator('select').filter({has:page.locator('option[value="high"]')}).first();
      await severity.selectOption('high');
      await page.waitForFunction(
        ()=>new URL(location.href).searchParams.get('severity')==='high',null,{timeout}
      );
      assert.match(page.url(),/severity=high/);
      assert.ok(requests.some(r=>r.path.startsWith('/opportunities?')&&r.status===200));
    });
    await scenario(locale,'/rds/reservations',async(page,requests)=>{
      await page.getByText('qa-rds').first().waitFor({timeout});
      assert.ok((await page.locator('body').innerText()).includes('50'),
        'RDS coverage ratio not rendered');
      assert.ok(requests.some(r=>r.path.startsWith('/rds/reservations-dashboard/coverage')&&r.status===200));
    });
    await scenario(locale,'/settings/appearance',async(page)=>{
      const radio=page.locator('input[name="aven-theme"][value="dark"]');
      await radio.check();
      assert.equal(await page.locator('html').getAttribute('data-theme-preference'),'dark');
    });
  }
}

async function awsPricingVisualMatrix(){
  const widths=[1920,1440,1366,1280,1024,768,390,360];
  for(const locale of ['pt-BR','en-US']){
    for(const theme of ['light','dark','system']){
      const {ctx}=await createContext(locale,{
        theme:theme==='system'?null:theme,
        colorScheme:theme==='dark'?'dark':'light'
      });
      const page=await ctx.newPage();
      const record={
        route:'/settings/pricing/aws',locale,theme,
        scenario:'task-28.5-visual-matrix',status:'not_run',pageErrors:[]
      };
      report.cases.push(record);
      watch(page,record.pageErrors);
      try{
        await visit(page,'/settings/pricing/aws',locale,record);
        await page.getByText('Fixture only · EC2 Linux shared').first().waitFor({timeout});
        for(const width of widths){
          await page.setViewportSize({width,height:width<=768?844:900});
          const overflow=await page.evaluate(()=>
            document.documentElement.scrollWidth>window.innerWidth+3);
          assert.equal(overflow,false,'AWS pricing document overflow at '+width+'px');
          await page.screenshot({
            path:OUT+'/aws-pricing-'+locale+'-'+theme+'-'+width+'.png',
            fullPage:true,animations:'disabled'
          });
        }
        assert.deepEqual(record.pageErrors,[],'AWS pricing browser runtime errors');
        record.status='passed';
      }catch(error){fail(record,error)}
      finally{await page.close();await ctx.close()}
    }
  }
}
async function visualAndAccessibility(){
  const {ctx}=await createContext('en-US');
  try{
    for(const route of ['/settings/appearance','/settings/pricing/aws','/billing','/inventory','/opportunities','/rds/reservations']){
      const page=await ctx.newPage();
      const record={route,locale:'en-US',scenario:'visual-a11y-representative',status:'not_run'};
      report.cases.push(record);
      try{
        await visit(page,route,'en-US',record);
        // Keyboard operability and accessible roles of the Language Selector.
        await selector(page).focus();
        await page.keyboard.press('Enter');
        const radios=page.getByRole('menuitemradio');
        await radios.first().waitFor({state:'visible',timeout});
        assert.equal(await radios.count(),2,'locale options must expose two radio roles');
        assert.equal(await radios.filter({hasText:/English/}).first().getAttribute('aria-checked'),'true');
        await page.keyboard.press('Escape');
        // Runtime WCAG checks complement, but do not replace, assistive-technology review.
        const axePath='node_modules/axe-core/axe.min.js';
        assert.ok(existsSync(axePath),'axe-core is required for full accessibility QA');
        await page.addScriptTag({path:axePath});
        const issues=await page.evaluate(async()=>{
          const result=await window.axe.run(document,{
            runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}
          });
          return result.violations.map(v=>({id:v.id,impact:v.impact,
            nodes:v.nodes.length,description:v.help,
            affected:v.nodes.map(node=>({target:node.target,
              html:node.html?.slice(0,400),failureSummary:node.failureSummary?.slice(0,450)}))}));
        });
        record.axeViolations=issues;
        assert.deepEqual(issues.filter(v=>v.impact==='critical'||v.impact==='serious'),[],
          'critical or serious accessibility violations');
        for(const size of [{width:768,height:1024},{width:390,height:844}]){
          await page.setViewportSize(size);
          await page.screenshot({path:OUT+'/'+toSlug(route)+'-en-US-'+size.width+'.png',
            animations:'disabled',fullPage:true});
          const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+3);
          assert.equal(overflow,false,'horizontal overflow at '+size.width+'px');
        }
        record.status='passed';
      }catch(error){fail(record,error)}
      finally{await page.close()}
    }
  }finally{await ctx.close()}
}
try{
  await new Promise((resolve,reject)=>proxy.once('error',reject).listen(TLS_PORT,'127.0.0.1',resolve));
  browser=await chromium.launch({executablePath:browserBin,headless:true,args:['--no-sandbox']});
  server=spawn(process.execPath,['./node_modules/next/dist/bin/next','start','-p',String(PORT)],
    {stdio:'inherit',env:{...process.env,PORT:String(PORT)}});
  let ready=false;
  for(let i=0;i<60;i++){
    if(server.exitCode!==null)break;
    try{const result=await fetch(UPSTREAM+'/login');if(result.ok){ready=true;break}}catch{}
    await delay(1000);
  }
  assert.ok(ready,'production Next server did not start');
  if(phase26 || phase27){
    const deps={browser,createContext,visit,watch,report,fail,out:OUT,timeout};
    if(phase26){
      await runPhase26(deps);
      await runPhase26Extensions(deps);
    }else await runPhase27(deps);
  }else{
    await routeSuite('pt-BR');await routeSuite('en-US');
    if(full){await runFunctional();await visualAndAccessibility();await awsPricingVisualMatrix()}
  }
  // Public/technical paths are already covered by the existing browser smoke and
  // its separate report; count them in the inventory, never as this suite's passes.
} catch(error){
  report.failures.push({route:'<suite>',scenario:'infrastructure',error:String(error?.stack||error)});
} finally {
  report.finished=new Date().toISOString();
  report.elapsedSeconds=Math.round((Date.now()-START)/1000);
  report.counts={passed:report.cases.filter(c=>c.status==='passed').length,
    failed:report.cases.filter(c=>c.status==='failed').length,
    not_run:report.cases.filter(c=>c.status==='not_run').length,
    blocked:report.cases.filter(c=>c.status==='blocked').length};
  writeFileSync(OUT+'/report.json',JSON.stringify(report,null,2)+'\n');
  if(server)server.kill('SIGTERM');
  if(browser)await browser.close();
  await new Promise(resolve=>proxy.close(resolve));
  rmSync(tlsDir,{recursive:true,force:true});
  console.log('Aven authenticated browser QA: '+JSON.stringify({mode:report.mode,
    cases:report.counts,failures:report.failures.length,report:OUT+'/report.json'}));
}
if(report.failures.length || ((phase26 || phase27) && report.counts.blocked))process.exitCode=1;

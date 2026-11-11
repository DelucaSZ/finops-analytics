import assert from 'node:assert/strict';

// Extended Task 26.3 browser QA. All checks use real Chromium and safe API fixtures.
// The underlying billing requests are inspected; no live cloud account is mutated.
const LOCALES=['pt-BR','en-US'];
const SIZES=[{name:'desktop',width:1440,height:900},{name:'mobile',width:390,height:844}];
const URL='/billing?period=custom&from=2026-10-01&to=2026-10-31&accounts=1';
const wait=async(page,condition)=>page.waitForFunction(condition,null,{timeout:12000});

function withinViewport(rect,width,height) {
  assert.ok(rect && rect.width>32 && rect.height>12,'dropdown missing visible bounds');
  assert.ok(rect.x>=-2 && rect.y>=-2 && rect.x+rect.width<=width+2 &&
    rect.y+rect.height<=height+2,'dropdown clipped outside viewport: '+JSON.stringify(rect));
}

async function verifyMultiSelect(page,requests,viewport,locale,out) {
  const trigger=page.locator('main button[aria-haspopup="menu"]').first();
  await trigger.click();
  const menu=page.getByRole('menu').last();
  await menu.waitFor({state:'visible'});
  await wait(page,()=>document.querySelector('[role="menu"][data-positioned="true"]')!==null);
  withinViewport(await menu.boundingBox(),viewport.width,viewport.height);
  const group=menu.getByRole('group');
  const list=group;
  const visibleCount=await group.locator('input[type="checkbox"]').count();
  assert.ok(visibleCount>=15,'large AWS account list missing: '+JSON.stringify({
    accessible:visibleCount,domCount:await group.locator('input[type="checkbox"]').count(),
    menuText:(await menu.innerText()).slice(0,500),groupHTML:(await group.evaluate(el=>el.outerHTML)).slice(0,1500),
    menuHTML:(await menu.evaluate(el=>el.outerHTML)).slice(0,1800),
    cloudAccountRequests:requests.filter(r=>r.path.includes('cloud-accounts'))
  }));
  const optionSemantics=await group.evaluate(el=>({
    groupLabel:el.getAttribute('aria-label'),
    inputs:[...el.querySelectorAll('label input[type="checkbox"]')].map(input=>({
      checked:input.getAttribute('aria-checked'),
      label:input.closest('label')?.textContent?.trim()
    }))
  }));
  assert.ok(optionSemantics.groupLabel && optionSemantics.inputs.length>=15 &&
    optionSemantics.inputs.every(x=>x.label && x.checked!==null),
    'AWS option accessibility labels or checked semantics missing');
  const scroll=await list.evaluate(el=>({scroll:el.scrollHeight,client:el.clientHeight,
    overflow:getComputedStyle(el).overflowY}));
  assert.ok(scroll.scroll>scroll.client+25 && scroll.overflow==='auto',
    'account list must scroll internally: '+JSON.stringify(scroll));
  const search=menu.getByRole('textbox').first();
  await search.fill('not-a-real-aws-account');
  assert.equal(await group.locator('input[type="checkbox"]').count(),0,'search did not filter accounts');
  await search.fill('QA Additional AWS 16');
  assert.equal(await group.locator('input[type="checkbox"]').count(),1,'search did not find long account');
  await search.fill('');
  assert.ok(await group.locator('input[type="checkbox"]').count()>=15);
  const original=await group.locator('input[type="checkbox"]').first().isChecked();
  assert.equal(original,true,'original AWS account selection lost');

  // Real checkbox clear / select-all actions must update selection and API params.
  const clear=menu.locator('button').last();
  assert.equal(await clear.isDisabled(),false,'clear action unexpectedly disabled');
  await clear.click();
  await wait(page,()=>!new URL(location.href).searchParams.has('accounts'));
  assert.equal(await group.locator('input[type="checkbox"]').first().isChecked(),false,
    'clear action did not deselect AWS account');
  await menu.locator('label').first().click(); // select all available AWS accounts
  await wait(page,()=>new URL(location.href).searchParams.get('accounts')?.split(',').length===15);
  for(let i=0;i<30;i++){
    if(requests.some(r=>r.path.startsWith('/billing/aws/summary') &&
       r.payload?.account_ids?.length===15))break;
    await page.waitForTimeout(100);
  }
  assert.ok(requests.some(r=>r.path.startsWith('/billing/aws/summary') &&
      r.payload?.account_ids?.length===15 &&
      r.payload.account_ids.includes(1) && r.payload.account_ids.includes(16)),
    'multi-account selection not reflected in Billing API payload');
  assert.equal(await group.locator('input[type="checkbox"]').count(),15);
  assert.ok(await group.locator('input[type="checkbox"]').evaluateAll(elements=>elements.every(e=>e.checked)),
    'select-all did not check every AWS account');
  await page.screenshot({path:out+'/phase26-expanded-multiselect-'+locale+'-'+viewport.name+'.png',
    animations:'disabled'});
  await page.locator('h1').first().click();
  await menu.waitFor({state:'hidden'});
  assert.equal(await trigger.getAttribute('aria-expanded'),'false',
    'multi-select did not close on outside click');
}

async function verifySingleSelect(page,requests,viewport) {
  const native=page.locator('main select[data-aven-native-select]')
    .filter({has:page.locator('option[value="UNBLENDED_COST"]')}).first();
  await native.waitFor({state:'attached'});
  const combobox=native.locator('..').getByRole('combobox');
  await combobox.scrollIntoViewIfNeeded();
  await combobox.focus();
  assert.equal(await combobox.evaluate(el=>document.activeElement===el),true);
  await combobox.press('ArrowDown');
  const list=page.getByRole('listbox').first();
  await list.waitFor({state:'visible'});
  await wait(page,()=>document.querySelector('[role="listbox"][data-positioned="true"]')!==null);
  withinViewport(await list.boundingBox(),viewport.width,viewport.height);
  const selected=list.locator('[role="option"][aria-selected="true"]');
  assert.equal(await selected.count(),1,'selected option is not exposed by ARIA');
  const label=(await native.locator('option[value="UNBLENDED_COST"]').textContent())?.trim();
  assert.ok(label,'metric option not translated');
  const target=list.getByRole('option',{name:label,exact:true});
  assert.equal(await target.getAttribute('aria-selected'),'false');
  await target.hover();
  await wait(page,()=>Array.from(document.querySelectorAll('[role="option"]'))
    .some(e=>e.dataset.active==='true'));
  const colors=await target.evaluate(el=>({
    hover:getComputedStyle(el).backgroundColor,
    selected:getComputedStyle(el.closest('[role="listbox"]').querySelector('[aria-selected="true"]')).backgroundColor
  }));
  assert.notEqual(colors.hover,'rgba(0, 0, 0, 0)','hover style missing');
  assert.notEqual(colors.selected,'rgba(0, 0, 0, 0)','selected style missing');
  await target.click();
  assert.equal(await native.inputValue(),'UNBLENDED_COST','single select native value did not update');
  await wait(page,()=>new URL(location.href).searchParams.get('metric')==='UNBLENDED_COST');
  for(let i=0;i<30;i++){
    if(requests.some(r=>r.path.startsWith('/billing/aws/summary') &&
      r.payload?.metric==='UNBLENDED_COST'))break;
    await page.waitForTimeout(100);
  }
  assert.ok(requests.some(r=>r.path.startsWith('/billing/aws/summary') &&
    r.payload?.metric==='UNBLENDED_COST'),'single-select metric not sent to Billing API');
  await combobox.click();
  await page.getByRole('listbox').waitFor({state:'visible'});
  await page.locator('h1').first().click();
  assert.equal(await combobox.getAttribute('aria-expanded'),'false',
    'single-select did not close on outside click');
}

async function verifyDisabled(page) {
  const disabled=page.locator('main [data-aven-select] [role="combobox"][disabled]:visible').first();
  await disabled.waitFor({state:'visible'});
  assert.equal(await disabled.isDisabled(),true,'expected disabled profile dropdown');
  assert.equal(await disabled.getAttribute('aria-expanded'),'false');
  assert.equal(await disabled.evaluate(el=>getComputedStyle(el).cursor),'not-allowed');
  assert.equal(await page.getByRole('listbox').count(),0,
    'disabled dropdown must not have a popup');
}

async function runCase(deps,{locale,viewport,mode}) {
  const {ctx,requests}=await deps.createContext(locale,{
    viewport,theme:mode==='disabled'?'dark':'light',
    manyAccounts:mode==='multi-and-single',emptyBillingProfiles:mode==='disabled'
  });
  const page=await ctx.newPage(),errors=[];
  deps.watch(page,errors);
  const record={scenario:'extended-'+mode,route:URL,locale,theme:mode==='disabled'?'dark':'light',
    viewport:viewport.name,status:'not_run',pageErrors:errors};
  deps.report.cases.push(record);
  try {
    await deps.visit(page,URL,locale,record);
    await page.waitForTimeout(350);
    if(mode==='disabled')await verifyDisabled(page);
    else {
      await verifyMultiSelect(page,requests,viewport,locale,deps.out);
      await verifySingleSelect(page,requests,viewport);
    }
    assert.deepEqual(errors,[],'browser runtime errors');
    record.unknownEndpoints=requests.filter(x=>x.unsupported).map(x=>x.path);
    if(record.unknownEndpoints.length) {
      record.status='blocked';
      deps.report.limitations.push({scenario:record.scenario,locale,route:URL,
        reason:'unknown API fixture',endpoints:record.unknownEndpoints});
    }else record.status='passed';
  }catch(error){deps.fail(record,error)}
  finally{await page.close();await ctx.close()}
}

export async function runPhase26Extensions(deps){
  for(const locale of LOCALES) for(const viewport of SIZES)
    await runCase(deps,{locale,viewport,mode:'multi-and-single'});
  for(const locale of LOCALES)
    await runCase(deps,{locale,viewport:SIZES[0],mode:'disabled'});
}

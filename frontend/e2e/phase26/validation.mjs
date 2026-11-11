import assert from 'node:assert/strict';
import {PROTECTED_ROUTES} from '../i18n/routes.mjs';

// Real Chromium against the production Next build; API data remains synthetic.
// Every checked screen is visited, not inferred from static source inspection.
const VIEWPORTS = [
  {name:'desktop',width:1440,height:900},
  {name:'tablet',width:768,height:1024},
  {name:'mobile',width:390,height:844},
];
const THEMES = ['light','dark','system'];
const LOCALES = ['pt-BR','en-US'];
const BILLING_CUSTOM = '/billing?period=custom&from=2026-10-01&to=2026-10-31&accounts=1';

function measuredBounds(box,width,height) {
  assert.ok(box,'popup has no bounding rectangle');
  assert.ok(box.width>32&&box.height>10,'popup has no usable size');
  assert.ok(box.x>=-2&&box.y>=-2&&box.x+box.width<=width+2&&box.y+box.height<=height+2,
    'popup clipped outside viewport: '+JSON.stringify(box));
}

async function checkAvatar(page) {
  const trigger=page.locator('header button:has(span[data-size="md"])').first();
  await trigger.waitFor({state:'visible'});
  const avatar=trigger.locator('span[data-size="md"]').first();
  const dimensions=await avatar.evaluate(element=>{
    const rect=element.getBoundingClientRect();
    const style=getComputedStyle(element);
    const text=element.querySelector('span');
    const glyph=text?.getBoundingClientRect();
    return {width:rect.width,height:rect.height,radius:parseFloat(style.borderTopLeftRadius),
      flexShrink:style.flexShrink,letters:text?.textContent||'',
      clipped:Boolean(glyph&&(glyph.left<rect.left-1||glyph.right>rect.right+1||
        glyph.top<rect.top-1||glyph.bottom>rect.bottom+1))};
  });
  assert.ok(dimensions.width>=34&&dimensions.width<=38,'avatar not around 36px: '+JSON.stringify(dimensions));
  assert.ok(Math.abs(dimensions.width-dimensions.height)<1,'avatar oval: '+JSON.stringify(dimensions));
  assert.ok(dimensions.radius>=dimensions.width/2-1,'avatar is not circular');
  assert.equal(dimensions.flexShrink,'0','avatar compressed by flexbox');
  assert.ok(dimensions.letters.length>=1&&dimensions.letters.length<=2,'invalid initials');
  assert.equal(dimensions.clipped,false,'avatar initials clipped');

  await trigger.click();
  const menu=page.getByRole('menu').last();
  await menu.waitFor({state:'visible'});
  assert.ok(await menu.getByRole('menuitem').count(),'logout menuitem absent');
  await page.keyboard.press('Escape');
  await menu.waitFor({state:'hidden'});
  assert.equal(await trigger.getAttribute('aria-expanded'),'false');
  return dimensions;
}

async function checkSingleSelect(page,width,height) {
  // Inactive tabs may keep controls mounted but hidden: only interactive visible popups can be audited.
  const triggers=page.locator('main [data-aven-select] [role="combobox"]:not([disabled]):visible');
  const count=await triggers.count();
  if(!count)return 0;
  const trigger=triggers.first();
  await trigger.scrollIntoViewIfNeeded();
  await trigger.focus();
  await trigger.press('ArrowDown');
  assert.equal(await trigger.getAttribute('aria-expanded'),'true','ArrowDown did not open Aven select');
  const list=page.getByRole('listbox').first();
  await list.waitFor({state:'visible'});
  await page.waitForFunction(()=>document.querySelector('[role="listbox"][data-positioned="true"]')!==null);
  measuredBounds(await list.boundingBox(),width,height);
  const visual=await list.evaluate(el=>{
    const style=getComputedStyle(el);
    return {background:style.backgroundColor,border:style.borderTopWidth,radius:parseFloat(style.borderTopLeftRadius)};
  });
  assert.ok(visual.radius>0&&visual.border!=='0px','select popup lost its Aven surface');
  assert.notEqual(visual.background,'rgba(0, 0, 0, 0)','transparent select popup');
  await trigger.press('Escape');
  assert.equal(await trigger.getAttribute('aria-expanded'),'false','Escape did not close select');
  await list.waitFor({state:'hidden'});
  return count;
}

async function checkBilling(page,requests) {
  const period=page.locator('main select[data-aven-native-select]')
    .filter({has:page.locator('option[value="custom"]')}).first();
  await period.waitFor({state:'attached'});
  assert.equal(await period.inputValue(),'custom','custom Billing period changed');
  const dates=page.locator('main input[type="date"]');
  assert.equal(await dates.count(),2,'custom Billing date fields not visible');
  const values=await dates.evaluateAll(inputs=>inputs.map(input=>input.value));
  assert.deepEqual(values,['2026-10-01','2026-10-31'],'custom date range lost');
  const account=page.locator('main button[aria-haspopup="menu"]').first();
  await account.waitFor({state:'visible'});
  await account.click();
  const menu=page.getByRole('menu').last();
  await menu.waitFor({state:'visible'});
  const search=menu.getByRole('textbox').first();
  await search.fill('QA AWS');
  assert.ok(await menu.getByText('QA AWS',{exact:false}).count(),'searchable account disappeared');
  await search.fill('');
  assert.ok(await menu.getByRole('checkbox').count(),'multi-select checkboxes missing');
  await page.keyboard.press('Escape');
  await menu.waitFor({state:'hidden'});
  assert.ok(requests.some(r=>r.path.startsWith('/billing/aws/summary')&&r.status===200),
    'Billing did not query the synthetic cost API');
  assert.ok(requests.filter(r=>r.path.startsWith('/billing/aws/summary'))
    .every(r=>r.payload?.account_ids?.includes(1)),'Billing account filter changed API payload');
}

async function visitCase(deps,{locale,route,viewport,theme='light',scheme='light',collapsed=false,longIdentity=false,screenshot=false,scenario}) {
  const {createContext,visit,watch,report,fail,out,timeout}=deps;
  const {ctx,requests}=await createContext(locale,{viewport,colorScheme:scheme,theme,longIdentity});
  const page=await ctx.newPage();
  const errors=[];
  watch(page,errors);
  const record={scenario,route,locale,viewport:viewport.name,theme,scheme,collapsed,
    longIdentity,status:'not_run',pageErrors:errors};
  report.cases.push(record);
  try{
    await visit(page,route,locale,record);
    await page.waitForTimeout(400);
    if(collapsed&&viewport.width>850){
      const toggle=page.locator('button[aria-controls="aven-desktop-sidebar"]');
      await toggle.click();
      assert.equal(await page.locator('html').getAttribute('data-sidebar'),'collapsed');
    }
    const expected=theme==='system'?scheme:theme;
    assert.equal(await page.locator('html').getAttribute('data-theme'),expected);
    assert.equal(await page.locator('html').getAttribute('data-theme-preference'),theme);
    assert.equal(await page.locator('html').getAttribute('lang'),locale);
    assert.equal(await page.locator('main select:not([data-aven-native-select])').count(),0,
      'unstandardized native select remains in application content');
    record.dropdownCount=await checkSingleSelect(page,viewport.width,viewport.height);
    record.avatar=await checkAvatar(page);
    if(route.startsWith('/billing?'))await checkBilling(page,requests);
    if(longIdentity&&viewport.width>850){
      const text=page.locator('header button:has(span[data-size="md"]) strong').first();
      await text.waitFor({state:'visible'});
      const truncated=await text.evaluate(el=>{
        const style=getComputedStyle(el);
        return style.textOverflow==='ellipsis'&&el.scrollWidth>el.clientWidth;
      });
      assert.equal(truncated,true,'long identity does not truncate beside avatar');
    }
    if(viewport.width<=850){
      assert.equal(await page.locator('#aven-desktop-sidebar').isVisible(),false,
        'desktop sidebar overlaps mobile content');
    }
    const viewportOverflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+3);
    assert.equal(viewportOverflow,false,'document horizontal overflow');
    assert.deepEqual(errors,[],'runtime browser errors');
    record.unknownEndpoints=requests.filter(r=>r.unsupported).map(r=>r.path);
    if(record.unknownEndpoints.length){
      record.status='blocked';
      report.limitations.push({route,locale,scenario,reason:'missing synthetic API fixture',
        endpoints:record.unknownEndpoints});
    }else record.status='passed';
    if(screenshot)await page.screenshot({path:out+'/phase26-'+scenario+'-'+locale+'-'+theme+'-'+viewport.name+(collapsed?'-collapsed':'')+'.png',
      animations:'disabled',fullPage:true});
    record.requestCount=requests.length;
  }catch(error){fail(record,error)}
  finally{await page.close();await ctx.close()}
}

export async function runPhase26(deps) {
  // All 24 protected routes, in both locales, including Settings subroutes.
  for(const locale of LOCALES){
    for(const route of PROTECTED_ROUTES){
      await visitCase(deps,{locale,route,viewport:VIEWPORTS[0],theme:'light',scheme:'light',
        scenario:'route-dropdown-audit'});
    }
  }
  // Pairwise + full theme/locale/viewport coverage of the modified components.
  for(const locale of LOCALES){
    for(const theme of THEMES){
      for(const viewport of VIEWPORTS){
        await visitCase(deps,{locale,route:BILLING_CUSTOM,viewport,theme,
          scheme:theme==='system'?'dark':'light',collapsed:viewport.width>850,
          longIdentity:true,screenshot:true,scenario:'integrated-billing-avatar'});
      }
    }
  }
  // Expanded sidebar + default profile layout remain intact.
  for(const locale of LOCALES){
    await visitCase(deps,{locale,route:'/flow',viewport:VIEWPORTS[0],theme:'dark',
      scenario:'flow-filter-desktop',screenshot:true});
    await visitCase(deps,{locale,route:'/billing',viewport:VIEWPORTS[0],theme:'system',
      scheme:'light',scenario:'billing-default-expanded',screenshot:true});
  }
}

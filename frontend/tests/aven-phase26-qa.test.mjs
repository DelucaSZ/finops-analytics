import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import {fileURLToPath} from 'node:url';
import {PROTECTED_ROUTES} from '../e2e/i18n/routes.mjs';
import {runPhase26} from '../e2e/phase26/validation.mjs';

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const read=(pathFromRoot)=>fs.readFileSync(path.join(ROOT,pathFromRoot),'utf8');
const runner=read('scripts/e2e-i18n-authenticated.mjs');
const qa=read('e2e/phase26/validation.mjs');
const extended=read('e2e/phase26/extended-validation.mjs');
const ci=read('../.github/workflows/ci.yml');
const packageJson=JSON.parse(read('package.json'));

test('Task 26.3 has a runnable real Chromium suite with recorded artifacts',()=>{
  assert.equal(typeof runPhase26,'function');
  assert.equal(packageJson.scripts['test:aven:phase26'],
    'node scripts/e2e-i18n-authenticated.mjs --phase26');
  assert.match(runner,/const phase26 = process\.argv\.includes\('--phase26'\)/);
  assert.match(runner,/await runPhase26\(/);
  assert.match(runner,/await runPhase26Extensions\(/);
  assert.match(runner,/chromium\.launch\(/);
  assert.match(runner,/backend:'simulated'/);
  assert.match(runner,/report\.cases\.filter\(c=>c\.status==='failed'\)/);
  assert.match(ci,/npm run test:aven:phase26/);
  assert.match(ci,/aven-phase26-visual-qa/);
});

test('QA browser matrix explicitly covers the 24 protected routes in both languages',()=>{
  assert.equal(PROTECTED_ROUTES.length,24);
  assert.deepEqual([...new Set(PROTECTED_ROUTES)].sort(),[...PROTECTED_ROUTES].sort());
  for(const route of ['/', '/billing', '/inventory', '/flow', '/opportunities',
    '/rds/reservations', '/settings/accounts', '/settings/usage-costs',
    '/settings/pricing/oci','/collections','/settings/users']){
    assert.ok(PROTECTED_ROUTES.includes(route),route+' absent from QA inventory');
  }
  for(const locale of ["'pt-BR'","'en-US'"])assert.ok(qa.includes(locale));
  for(const theme of ["'light'","'dark'","'system'"])assert.ok(qa.includes(theme));
  for(const width of ['1440','768','390'])assert.ok(qa.includes(width));
  assert.match(qa,/for\(const route of PROTECTED_ROUTES\)/);
  assert.match(qa,/scenario:'integrated-billing-avatar'/);
  assert.match(qa,/collapsed:viewport\.width>850/);
  assert.match(qa,/longIdentity:true/);
});

test('QA explicitly checks Aven dropdown behavior, geometry and functional Billing request contract',()=>{
  for(const evidence of ["role=\"combobox\"","getByRole('listbox')","'ArrowDown'","'Escape'",
    'data-aven-native-select',"getByRole('checkbox')",'/billing/aws/summary',
    'period=custom','from=2026-10-01','to=2026-10-31',
    'account_ids','measuredBounds','page.screenshot']){
    assert.ok(qa.includes(evidence),'missing QA assertion: '+evidence);
  }
  assert.match(qa,/:not\(\[disabled\]\):visible/,'hidden tab controls must not be clicked');
  assert.match(qa,/await checkSingleSelect\(/);
  assert.match(qa,/await checkBilling\(/);
  assert.match(qa,/assert\.deepEqual\(errors,\[\]/);
});

test('Avatar QA prevents oval geometry, cut initials, flex shrink and menu regressions',()=>{
  for(const evidence of ['Math.abs(dimensions.width-dimensions.height)','dimensions.flexShrink',
    'dimensions.clipped','header button:has(span[data-size="md"])',
    "getByRole('menuitem')",'textOverflow','scrollWidth>el.clientWidth']){
    assert.ok(qa.includes(evidence),'missing avatar QA assertion: '+evidence);
  }
  assert.doesNotMatch(qa,/type="file"|uploadImage|uploadAvatar/);
});


test('extended live-Chromium QA validates multiselect mutations, scrolling, disabled and hover state',()=>{
  for(const evidence of ['runPhase26Extensions','group.locator(\'input[type="checkbox"]\')',
    'optionSemantics','aria-label','scrollHeight','clientHeight','account_ids','UNBLENDED_COST',
    'dataset.active','getComputedStyle','hover()','isDisabled()',
    'getByRole(\'listbox\')','aria-selected','clear.click()',
    'accounts','select-all','not-a-real-aws-account']){
    assert.ok(extended.includes(evidence),'missing extended QA evidence: '+evidence);
  }
  assert.match(runner,/emptyBillingProfiles/);
  assert.match(runner,/manyAccounts/);
});

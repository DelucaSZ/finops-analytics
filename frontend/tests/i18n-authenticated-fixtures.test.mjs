import test from 'node:test';
import assert from 'node:assert/strict';
import {PROTECTED_ROUTES,PUBLIC_ROUTES,TECHNICAL_ROUTES,INVENTORIED_COUNT} from '../e2e/i18n/routes.mjs';
import {apiFixture,FIXTURE_FINANCIAL} from '../e2e/i18n/fixtures.mjs';

test('reconciles 33 unique page routes, 24 protected, five public and four technical',()=>{
  assert.equal(INVENTORIED_COUNT,33);
  assert.equal(PROTECTED_ROUTES.length,24);
  assert.equal(PUBLIC_ROUTES.length,5);
  assert.equal(TECHNICAL_ROUTES.length,4);
  assert.equal(new Set([...PROTECTED_ROUTES,...PUBLIC_ROUTES,...TECHNICAL_ROUTES]).size,33);
});
test('synthetic auth fixture represents admin without bypassing production auth',()=>{
  const response=apiFixture('/auth/me');
  assert.equal(response.status,200);
  assert.equal(response.body.role,'admin');
  assert.match(response.body.email,/@example\.test$/);
});
test('billing contract retains precise decimal amounts and technical request IDs',()=>{
  const request={account_ids:[1],start_date:'2026-10-01',end_date:'2026-11-01',profile_id:'qa-profile'};
  const response=apiFixture('/billing/aws/summary','POST',request);
  assert.equal(response.status,200);
  assert.equal(response.body.totals[0].amount,FIXTURE_FINANCIAL.billingAmount);
  assert.equal(response.body.profile_id,'qa-profile');
  assert.equal(response.body.end_date,request.end_date);
  assert.equal(response.body.metric,'AMORTIZED_COST');
});
test('inventory and RDS fixtures keep OCID, normalized units and percentages unchanged',()=>{
  const inventory=apiFixture('/inventory/resources?page=1').body;
  assert.equal(inventory.items[1].resource_id,FIXTURE_FINANCIAL.technicalId);
  assert.ok(inventory.items[1].resource_id.length>60);
  const rds=apiFixture('/rds/reservations-dashboard/summary').body;
  assert.equal(rds.coverage.required_units,FIXTURE_FINANCIAL.rdsRequiredNu);
  assert.equal(rds.coverage.covered_units,FIXTURE_FINANCIAL.rdsCoveredNu);
  assert.equal(rds.coverage.coverage_percentage,FIXTURE_FINANCIAL.rdsCoveragePercent);
});
test('unknown contracts fail closed, and administrative mutations cannot escape fixture layer',()=>{
  assert.deepEqual(apiFixture('/endpoint-not-in-contract'),{status:503,body:{},unsupported:true});
  assert.equal(apiFixture('/users','POST',{email:'someone@example.test'}).status,403);
  assert.equal(apiFixture('/auth/logout','POST').status,403);
});

test('Dashboard fixture exposes arrays required by the executive overview',()=>{
  const dashboard=apiFixture('/dashboard/summary').body;
  for(const key of ['by_service','by_rule','by_provider','by_account','top_opportunities'])
    assert.ok(Array.isArray(dashboard[key]),key+' must be an array');
  assert.equal(dashboard.scope.has_current_data,true);
  assert.equal(dashboard.financial.totals[0].amount,FIXTURE_FINANCIAL.estimatedSavings);
});
test('legacy Collection API arrays coexist with paginated Collection Workspace API',()=>{
  const findings=apiFixture('/collections?limit=100&offset=0').body;
  const scans=apiFixture('/collections?limit=200').body;
  const page=apiFixture('/collections?page=1&page_size=25').body;
  assert.ok(Array.isArray(findings));
  assert.ok(Array.isArray(scans));
  assert.ok(Array.isArray(page.items));
  assert.equal(page.items[0].id,findings[0].id);
});
test('authenticated Settings fixtures have known success contracts',()=>{
  assert.equal(apiFixture('/tls').body.mode,'http');
  assert.equal(apiFixture('/auth/mfa/status').body.enabled,false);
  assert.equal(apiFixture('/pricing/oci').body.total,0);
  assert.equal(apiFixture('/settings/opportunity-policy').body.cycle_mode,'CALENDAR_MONTH');
  assert.ok(Array.isArray(apiFixture('/usage/cloudwatch/summary?group_by=region').body.items));
});

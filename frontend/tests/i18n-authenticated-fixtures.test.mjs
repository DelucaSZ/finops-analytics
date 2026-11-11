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

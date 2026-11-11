// Deterministic, synthetic browser-only API contracts. Types verified against
// frontend/lib/{types,billing,inventory,rds-reservations}.ts and page consumers.
// A missing fixture is NEVER an invented 200 response.
export const FIXTURE_TIME = '2026-11-01T12:00:00.000Z';
export const LONG_OCID = 'ocid1.instance.oc1.sa-saopaulo-1.' + 'q'.repeat(72);
const aws = {
  id:1, provider:'aws', native_account_id:'123456789012', name:'QA AWS',
  enabled:true, connection_status:'connected', last_connection_test_at:null,
  last_error:null, schedule_enabled:false, scan_interval_hours:24,
  next_scan_at:null, created_at:FIXTURE_TIME, updated_at:FIXTURE_TIME,
  aws_configuration:null, oci_configuration:null
};
const oci = {...aws, id:2,provider:'oci',native_account_id:'ocid1.tenancy.qa',name:'QA OCI'};
const accounts = [aws,oci];
const profile = {
  id:'qa-profile',name:'FinOps',description:'Test profile',granularity:'MONTHLY',
  metric:'AMORTIZED_COST',group_by:'NONE',exclude_record_types:['Credit'],
  is_default:true,enabled:true,is_system:true,created_by:null,
  created_at:FIXTURE_TIME,updated_at:FIXTURE_TIME
};
const inv = (id,provider,resourceId) => ({
  id,provider,cloud_account_id:provider==='aws'?1:2,
  native_account_id:provider==='aws'?aws.native_account_id:oci.native_account_id,
  account_name:provider==='aws'?'QA AWS':'QA OCI',
  resource_id:resourceId,resource_type:'instance',native_resource_type:'compute',
  service:'EC2',name:'QA compute '+id,region:'sa-east-1',availability_zone:'sa-east-1a',
  lifecycle_status:'running',native_status:'running',presence_status:'active',
  tags:{},attributes:{},first_seen_at:FIXTURE_TIME,last_seen_at:FIXTURE_TIME,
  last_seen_collection_run_id:'qa-collection'
});
const finding = {
  id:'qa-finding',fingerprint:'qa-fingerprint',provider:'oci',account_id:'ocid1.tenancy.qa',
  account_name:'QA OCI',legacy_account_id:2,rule_key:'qa-idle',service:'Compute',
  region:'sa-saopaulo-1',resource_id:LONG_OCID,resource_name:'QA long OCID',
  resource_type:'instance',provider_metadata:{},title:'QA opportunity',
  description:'Synthetic opportunity',current_monthly_cost:'1234.56',
  estimated_monthly_savings:'123.45',currency:'USD',confidence:'HIGH',
  severity:'high',status:'open',presence_status:'active',missing_count:0,
  missing_since_at:null,resolved_externally_at:null,presence_reconciled_at:null,
  first_seen_at:FIXTURE_TIME,last_seen_at:FIXTURE_TIME,
  first_seen_collection_run_id:'qa-collection',
  last_seen_collection_run_id:'qa-collection',total_occurrence_count:1,needs_review:false
};
const collection = {
  id:'qa-collection',scan_id:null,provider:'aws',account_id:aws.native_account_id,
  scope:{},started_at:FIXTURE_TIME,finished_at:FIXTURE_TIME,status:'success',
  resources_analyzed:2,opportunities_found:1,detailed_observations_available:true,
  analyzer_version:'qa',error_detail:null,created_at:FIXTURE_TIME,
  updated_at:FIXTURE_TIME,account_name:'QA AWS',duration_seconds:30,
  resources_analyzed_available:true,has_warnings:false
};
const rdsAccount = {id:1,name:'QA AWS',account_id:aws.native_account_id};
const page = items => ({items,page:1,page_size:20,total:items.length,total_pages:1});
const money = {amount:'1234.56',currency:'USD',status:'ACTUAL',estimated:false};
const billingBase = request => ({
  metric:request.metric || 'AMORTIZED_COST',
  start_date:request.start_date,end_date:request.end_date,
  profile_id:'qa-profile',profile_name:'FinOps',
  resolved_options:{granularity:request.granularity||'MONTHLY',
    metric:request.metric||'AMORTIZED_COST',
    group_by:request.group_by||'NONE',exclude_record_types:request.exclude_record_types||['Credit']}
});
const flowSummary = {currency:'USD',basis:'MONTHLY',recognized_savings:'123.45',
  reallocated:'0',adjustment_net:'0',balance:'123.45'};
const commonOptions = {providers:['aws','oci'],accounts:[
  {provider:'aws',account_id:aws.native_account_id,account_name:'QA AWS'},
  {provider:'oci',account_id:oci.native_account_id,account_name:'QA OCI'}]};
const operational = {
  last_inventory_collection_at:FIXTURE_TIME,last_coverage_run_at:FIXTURE_TIME,
  last_successful_coverage_run_at:FIXTURE_TIME,coverage_run_id:1,latest_run_id:1,
  pipeline_status:'COMPLETED',pipeline_stage:null,inventory_status:'COMPLETED',
  coverage_status:'COMPLETED',opportunity_status:'COMPLETED',
  billing_validation_status:'NOT_AVAILABLE',data_freshness:'FRESH',
  freshness_threshold_hours:24,error_detail:null
};
const rdsSummary = {
  coverage_run_id:1,rds:{total:1,fully_covered:0,partially_covered:1,uncovered:0,unknown:0},
  coverage:{required_units:8,covered_units:4,uncovered_units:4,coverage_percentage:50},
  reservations:{active:1,reserved_units:8,used_units:4,unused_units:4,utilization_percentage:50},
  expiring_next_30_days:0,
  billing:{technical_coverage_percentage:50,aws_observed_coverage_percentage:null,
    validation_status:'NOT_AVAILABLE',reconciliation_status:'NOT_AVAILABLE',reconciliation_detail:null},
  freshness:{inventory_updated_at:FIXTURE_TIME,coverage_calculated_at:FIXTURE_TIME,
    billing_data_reference:null}
};
const rdsCoverage = {
  instance_id:1,instance:'qa-rds',account:rdsAccount,region:'sa-east-1',
  engine:'postgres',engine_version:'15',instance_class:'db.t3.large',family:'t3',
  size:'large',topology:'single-az',multi_az:false,license_model:null,
  required_units:8,covered_units:4,uncovered_units:4,coverage_percentage:50,
  coverage_status:'PARTIAL',coverage_scope:'REGION',calculation_method:'NORMALIZED_UNITS',
  allocations:[],explanation:{},inventory_updated_at:FIXTURE_TIME
};
export const FIXTURE_FINANCIAL = Object.freeze({
  billingAmount:'1234.56',estimatedSavings:'123.45',
  rdsRequiredNu:8,rdsCoveredNu:4,rdsCoveragePercent:50,technicalId:LONG_OCID
});
export function apiFixture(path,method='GET',body=null) {
  const pathname = new URL(path,'https://qa.local').pathname;
  const request = body && typeof body==='object'?body:{};
  if (pathname==='/auth/me' && method==='GET')
    return {status:200,body:{id:1,full_name:'Aven QA',email:'qa@example.test',role:'admin'}};
  if (pathname==='/auth/csrf' && method==='GET')
    return {status:200,body:{csrf_token:'qa-only-token'}};
  if (method!=='GET' && !['/billing/aws/summary','/billing/aws/timeseries','/billing/aws/breakdown'].includes(pathname))
    return {status:403,body:{}}; // No administrative/financial mutations are authorized.
  if (pathname==='/cloud-accounts')return {status:200,body:accounts};
  if (pathname==='/cloud-accounts/capabilities')return {status:200,body:[]};
  if (pathname==='/accounts')return {status:200,body:[]};
  if (pathname==='/scans')return {status:200,body:[]};
  if (pathname==='/billing/aws/profiles')return {status:200,body:[profile]};
  if (pathname==='/billing/aws/summary')return {status:200,body:{...billingBase(request),totals:[money]}};
  if (pathname==='/billing/aws/timeseries')return {status:200,body:{
    ...billingBase(request),granularity:request.granularity||'MONTHLY',
    group_by:request.group_by||'NONE',
    points:[{...money,start_date:request.start_date,end_date:request.end_date,groups:[]}]
  }};
  if (pathname==='/billing/aws/breakdown')return {status:200,body:{
    ...billingBase(request),group_by:request.group_by||'SERVICE',
    items:[{...money,key:'EC2',label:'EC2',deepops_account_id:1,
      aws_account_id:aws.native_account_id,display_name:'QA AWS'}]
  }};
  if (pathname==='/inventory/options')return {status:200,body:{
    providers:['aws','oci'],accounts:[{id:1,name:'QA AWS',native_account_id:aws.native_account_id,provider:'aws'},
    {id:2,name:'QA OCI',native_account_id:oci.native_account_id,provider:'oci'}],
    regions:['sa-east-1'],resource_types:['instance'],services:['EC2'],
    lifecycle_statuses:['running'],presence_statuses:['active']
  }};
  if (pathname==='/inventory/resources')return {status:200,body:{
    ...page([inv(1,'aws','i-qa-resource'),inv(2,'oci',LONG_OCID)]),page_size:20
  }};
  if (pathname==='/finops/flow/options')return {status:200,body:{
    currencies:['USD'],periodicities:['MONTHLY'],providers:['aws','oci'],sources:['MANUAL']
  }};
  if (pathname==='/finops/flow/summary')return {status:200,body:[flowSummary]};
  if (pathname==='/finops/flow/timeseries')return {status:200,body:{
    granularity:'month',items:[{...flowSummary,bucket:'2026-11',balance_delta:'123.45',
      cumulative_balance:'123.45'}]
  }};
  if (pathname==='/finops/flow/breakdowns')return {status:200,body:{by_account:[],by_source:[]}};
  if (pathname==='/finops/flow/entries')return {status:200,body:{...page([]),page_size:50}};
  if (pathname==='/opportunities/options')return {status:200,body:{
    ...commonOptions,regions:['sa-saopaulo-1'],services:['Compute'],
    resource_types:['instance'],rules:['qa-idle']
  }};
  if (pathname==='/opportunities')return {status:200,body:{...page([finding]),page_size:25}};
  if (pathname==='/opportunities/stats')return {status:200,body:{open:1,treated:0,rejected:0}};
  if (pathname==='/collections/options')return {status:200,body:{
    ...commonOptions,has_more_accounts:false
  }};
  if (pathname==='/collections')return {status:200,body:{
    ...page([collection]),account_summary:null
  }};
  if (pathname==='/collections/qa-collection')return {status:200,body:{
    ...collection,opportunities_observed:1,warning_detail:null,trigger:'MANUAL'
  }};
  if (pathname==='/collections/qa-collection/comparison-options')
    return {status:200,body:[collection]};
  if (pathname==='/collections/qa-collection/compare')return {status:200,body:{
    available:false,reason:'NO_BASELINE',message:null,baseline:null,
    target:{...collection,rules_version:'qa'},summary:null,financial_summary:null,
    rules_version_warning:null,warnings:[],category:'NEW',items:[],page:1,
    page_size:20,total:0,total_pages:0
  }};
  if (pathname==='/collections/qa-collection/opportunities')
    return {status:200,body:{...page([finding]),page_size:25}};
  if (pathname==='/dashboard/summary')return {status:200,body:{
    scope:{provider:null,account_id:null,valid_scope_count:1,has_current_data:true},
    opportunities:{open:1,treated:0,rejected:0,new_since_previous:1},
    severity:{high:1,medium:0,low:0,other:0},
    financial:{metric:'estimated_monthly_savings',label:'Estimated monthly savings',
      period:'month',totals:[{currency:'USD',amount:'123.45'}]},
    by_provider:[],by_account:[],top_opportunities:[],
    recent_changes:{new:1,no_longer_detected:0,changed:0,changed_available:true,
      comparable_scopes:1,scopes_without_baseline:0,rules_version_changed_scopes:0,
      rules_version_unknown_scopes:0}
  }};
  if (pathname==='/rds/reservations/operational-status')return {status:200,body:operational};
  if (pathname==='/rds/reservations-dashboard/summary')return {status:200,body:rdsSummary};
  if (pathname==='/rds/reservations-dashboard/options')return {status:200,body:{
    accounts:[rdsAccount],regions:['sa-east-1'],engines:['postgres'],
    families:['t3'],instance_classes:['db.t3.large']
  }};
  if (pathname==='/rds/reservations-dashboard/coverage')return {status:200,body:page([rdsCoverage])};
  if (pathname==='/rds/reservations-dashboard/reservations')return {status:200,body:page([])};
  if (pathname==='/rds/reservations-dashboard/opportunities')return {status:200,body:page([])};
  if (pathname==='/users')return {status:200,body:[]};
  if (pathname==='/auth/sessions')return {status:200,body:[]};
  if (pathname==='/audit')return {status:200,body:{items:[],total:0}};
  if (pathname==='/audit/users')return {status:200,body:[]};
  if (pathname==='/policies/global'||pathname.startsWith('/policies/accounts/'))
    return {status:200,body:[]};
  // Deliberate error-state contract: api() translates HTTP 503 with an empty
  // payload. Do not turn unknown endpoints into fake domain success payloads.
  return {status:503,body:{},unsupported:true};
}

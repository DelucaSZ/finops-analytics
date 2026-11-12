// Deterministic browser-only Calculator API fixtures. Never imported by production code.
// These are known response samples, not calculated or inferred cloud prices.
const LONG_SKU = "ocid1.pricecomponent.oc1.sa-saopaulo-1." + "x".repeat(90);
const REFERENCE = "2026-11-01T12:00:00.000Z";

function component({ service, sku, currency, priced = true, price = "100.00", description = "QA price component" }) {
  return {
    service, sku, unit: "HOUR", description, pricing_status: priced ? "priced" : "sku_missing",
    unit_price: priced ? price : null, monthly_units: priced ? "730.000000001" : null,
    period_units: priced ? "730.000000001" : null,
    monthly_original_cost: priced ? price : null,
    period_original_cost: priced ? price : null, currency, source: priced ? "TEST_FIXTURE" : null,
    pricing_item_id: null, effective_from: priced ? "2026-11-01" : null,
    effective_until: null,
  };
}
function baseResponse(body, {currency, status = "priced"}) {
  return {
    provider:body.provider,service:body.resource_configuration.service,region:body.region,
    pricing_status:status,pricing_currency:currency,final_currency:currency,
    pricing_source:"TEST_FIXTURE",pricing_reference_date:REFERENCE,period_duration_hours:"730",
    monthly_original_cost:null,period_original_cost:null,monthly_known_subtotal:null,
    period_known_subtotal:null,discount_percent:null,monthly_discount_amount:null,
    period_discount_amount:null,monthly_net_cost:null,period_net_cost:null,
    conversion_enabled:false,usd_brl_rate:null,tax_percent:null,monthly_converted_cost:null,
    period_converted_cost:null,monthly_tax_amount:null,period_tax_amount:null,
    monthly_final_cost:null,period_final_cost:null,pricing_components:[],
    missing_pricing_components:[],warnings:[],
  };
}
function awsEstimate(body) {
  const converted = body.aws_financial?.conversion_enabled === true;
  const discounted = body.aws_financial?.discount_percent === "10";
  const original = "100.00", reduction = discounted ? "10.00" : "0.00";
  const net = discounted ? "90.00" : "100.00";
  const result = baseResponse(body,{currency:"USD"});
  const final = converted ? discounted ? "508.50" : "565.00" : net;
  const tax = discounted ? "58.50" : "65.00";
  return {
    ...result,final_currency:converted?"BRL":"USD",
    monthly_original_cost:original,period_original_cost:original,
    monthly_known_subtotal:original,period_known_subtotal:original,
    discount_percent:discounted?"10":"0",
    monthly_discount_amount:reduction,period_discount_amount:reduction,
    monthly_net_cost:net,period_net_cost:net,conversion_enabled:converted,
    usd_brl_rate:converted?body.aws_financial.usd_brl_rate:null,
    tax_percent:converted?"13":null,
    monthly_converted_cost:converted?(discounted?"450.00":"500.00"):null,
    period_converted_cost:converted?(discounted?"450.00":"500.00"):null,
    monthly_tax_amount:converted?tax:null,period_tax_amount:converted?tax:null,
    monthly_final_cost:final,period_final_cost:final,
    pricing_components:[component({
      service:body.resource_configuration.service,sku:LONG_SKU,currency:"USD",price:original,
    })],
    warnings:["price_snapshot_applied_to_entire_period"],
  };
}
function ociEstimate(body) {
  const db = body.resource_configuration.service === "db_system";
  const result = baseResponse(body,{currency:"BRL",status:db?"partially_priced":"priced"});
  return {
    ...result,
    monthly_known_subtotal:db?"72.00":"300.10",period_known_subtotal:db?"72.00":"300.10",
    monthly_original_cost:db?null:"300.10",period_original_cost:db?null:"300.10",
    monthly_final_cost:db?null:"300.10",period_final_cost:db?null:"300.10",
    pricing_components:[component({
      service:body.resource_configuration.service,sku:LONG_SKU,currency:"BRL",
      price:db?"72.00":"300.10",
    }),...(db?[component({
      service:"db_system",sku:"DB_LICENSE_"+LONG_SKU,currency:"BRL",
      priced:false,description:"Oracle license",
    })]:[])],
    missing_pricing_components:db?["DB_LICENSE_"+LONG_SKU]:[],
    warnings:db?["oci_base_database_quote_requires_verified_product_bindings"]:[],
  };
}

export function calculatorFixture(path, method = "GET", body = null) {
  const request = new URL(path,"https://qa.local");
  const pathname=request.pathname;
  if (method === "GET" && pathname === "/calculator/aws/regions")
    return {status:200,body:{items:["sa-east-1"],source:"TEST_FIXTURE"}};
  if (method === "GET" && pathname === "/calculator/aws/options")
    return {status:200,body:{
      items:request.searchParams.get("service")==="rds"
        ?[{instance_class:"db.t3.medium",deployment:"single-az"}]
        :[{instance_type:"t3.medium",operating_system:"linux"}],
      total:1,status:"priced",supported_engines:["postgres","mysql","mariadb"],source:"TEST_FIXTURE",
    }};
  if (method === "GET" && pathname === "/calculator/oci/options") {
    if (request.searchParams.get("service")==="db_system")
      return {status:200,body:{
        service:"db_system",region:request.searchParams.get("region"),items:[],
        setup_required:true,new_provisioning_shape:"VM.Standard.E5.Flex",capacity_unit:"ECPU",
      }};
    return {status:200,body:{
      service:"compute",region:request.searchParams.get("region"),operating_systems:["linux","windows"],
      vpu_tiers:[0,10,20],items:[{
        shape:"VM.Standard.E5.Flex",max_ocpus:16,max_memory_gb:256,
        max_memory_per_ocpu_gb:64,pricing_status:"priced",region_availability_verified:false,
      }],
    }};
  }
  if (method === "POST" && pathname === "/calculator/estimate" && body?.resource_configuration) {
    if (body.provider === "aws" && ["ec2","rds"].includes(body.resource_configuration.service))
      return {status:200,body:awsEstimate(body)};
    if (body.provider === "oci" && ["compute","db_system"].includes(body.resource_configuration.service))
      return {status:200,body:ociEstimate(body)};
  }
  return null;
}

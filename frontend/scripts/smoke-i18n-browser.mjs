import assert from "node:assert/strict";
import {existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync} from "node:fs";
import {join} from "node:path";
import {tmpdir} from "node:os";
import {createServer as httpsServer} from "node:https";
import {request as httpRequest} from "node:http";
import {execFileSync,spawn} from "node:child_process";
import {setTimeout as delay} from "node:timers/promises";
import {chromium} from "playwright-core";

const PORT = Number(process.env.AVEN_QA_PORT || 3227);
const TLS_PORT = PORT + 1;
const BASE = "https://localhost:" + TLS_PORT;
const UPSTREAM = "http://127.0.0.1:" + PORT;
// Production cookies have Secure=true. Exercise them over a local HTTPS origin,
// never by weakening cookie options or disabling application security.
const certificateDir = mkdtempSync(join(tmpdir(), "aven-i18n-qa-"));
const keyPath = join(certificateDir, "key.pem");
const certPath = join(certificateDir, "cert.pem");
execFileSync("openssl", ["req","-x509","-newkey","rsa:2048","-nodes",
  "-keyout",keyPath,"-out",certPath,"-days","1",
  "-subj","/CN=localhost","-addext","subjectAltName=DNS:localhost"],{stdio:"ignore"});
const proxy = httpsServer({key:readFileSync(keyPath),cert:readFileSync(certPath)}, (request,response) => {
  const upstream = httpRequest({hostname:"127.0.0.1",port:PORT,path:request.url,method:request.method,
    headers:{...request.headers,host:"localhost:" + TLS_PORT,
      "x-forwarded-host":"localhost:" + TLS_PORT,"x-forwarded-proto":"https"}}, (remote) => {
    response.writeHead(remote.statusCode ?? 502,remote.headers);
    remote.pipe(response);
  });
  upstream.on("error",error=>{response.writeHead(502);response.end(String(error));});
  request.pipe(upstream);
});
await new Promise((resolve,reject)=>proxy.once("error",reject).listen(TLS_PORT,"127.0.0.1",resolve));
const BROWSER = process.env.CHROME_BIN || ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium"].find(existsSync);
if (!BROWSER) throw new Error("Browser QA requires Chrome/Chromium; none found on this runner.");
const browser = await chromium.launch({executablePath: BROWSER, headless: true, args: ["--no-sandbox"]});
const server = spawn(process.execPath, ["./node_modules/next/dist/bin/next", "start", "-p", String(PORT)], {stdio: "inherit", env: {...process.env, PORT: String(PORT)}});
const failures = [];
const artifacts = "artifacts/i18n-browser";
mkdirSync(artifacts, {recursive: true});

const check = async (page, locale, heading) => {
  await page.goto(BASE + "/login", {waitUntil: "networkidle"});
  await page.waitForFunction(expected => document.documentElement.lang === expected, locale);
  assert.equal(await page.locator("html").getAttribute("lang"), locale);
  assert.match(await page.locator("h1").first().innerText(), new RegExp(heading, "i"));
};
try {
  let running = false;
  for (let attempt = 0; attempt < 60; attempt++) {
    try {const r=await fetch(UPSTREAM + "/login"); if(r.ok){running=true;break;}} catch {}
    await delay(1000);
  }
  assert.ok(running, "Next production server did not start");
  const clientErrors = [];
  const ctx = await browser.newContext({ignoreHTTPSErrors:true,viewport: {width: 1440, height: 900}});
  const page = await ctx.newPage();
  page.on("console", msg => {if(msg.type()==="error" && /hydration|mismatch|did not match|server rendered/i.test(msg.text())) clientErrors.push(msg.text());});
  page.on("pageerror", err => {if(/hydration|mismatch/i.test(err.message)) clientErrors.push(err.message);});
  await check(page, "pt-BR", "Bem-vindo de volta");
  await ctx.addCookies([{name:"aven.locale",value:"en-US",url: BASE}]);
  await check(page, "en-US", "Welcome back");
  await ctx.addCookies([{name:"aven.locale",value:"pt-BR",url: BASE}]);

  // Browser-fixture authentication only: no production credentials or mutations.
  await ctx.route("**/api/v1/auth/me", async route => {
    await route.fulfill({status:200,contentType:"application/json",headers:{
      "access-control-allow-origin":BASE,"access-control-allow-credentials":"true"
    },body:JSON.stringify({id:1,full_name:"I18n QA",email:"qa@example.test",role:"admin"})});
  });
  await page.goto(BASE + "/settings/appearance", {waitUntil: "domcontentloaded"});
  await page.locator('input[name="aven-theme"][value="dark"]').waitFor({state:"attached",timeout:20000});
  await page.locator('input[name="aven-theme"][value="dark"]').check();
  assert.equal(await page.locator("html").getAttribute("data-theme-preference"), "dark");
  await page.getByRole("button",{name:/Idioma:/}).click();
  await page.getByRole("menuitemradio",{name:/English/}).click();
  await page.waitForFunction(() => document.documentElement.lang === "en-US",null,{timeout:20000});
  await page.getByText("Appearance", {exact:true}).first().waitFor();
  assert.equal(await page.locator("html").getAttribute("data-theme-preference"), "dark");
  assert.ok(page.url().includes("/settings/appearance"));
  const cookie = (await ctx.cookies(BASE)).find(item=>item.name==="aven.locale");
  assert.equal(cookie?.value,"en-US");
  await page.reload({waitUntil:"domcontentloaded"});
  await page.waitForFunction(() => document.documentElement.lang === "en-US");
  assert.equal(await page.locator("html").getAttribute("data-theme-preference"), "dark");

  for (const viewport of [{width:1440,height:900},{width:768,height:1024},{width:390,height:844}]) {
    await page.setViewportSize(viewport);
    await page.screenshot({path:artifacts + "/appearance-en-"+viewport.width+".png",fullPage:true});
    const fits = await page.evaluate(() => document.querySelector("header")?.getBoundingClientRect().right <= window.innerWidth + 2);
    assert.ok(fits, "Topbar exceeds viewport at " + viewport.width);
  }

  const other = await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:390,height:844}});
  const otherPage = await other.newPage();
  await check(otherPage, "pt-BR", "Bem-vindo de volta");
  await other.addCookies([{name:"aven.locale",value:"invalid",url:BASE}]);
  await check(otherPage, "pt-BR", "Bem-vindo de volta");
  assert.equal(await page.locator("html").getAttribute("lang"), "en-US", "Independent contexts must not leak locale");
  await other.close();
  assert.deepEqual(clientErrors, [], "No hydration mismatch in browser console");
  await ctx.close();
  console.log("Aven browser i18n QA: PASS (SSR, cookie, switch, theme, viewport, isolation, hydration)");
} finally {
  server.kill("SIGTERM");
  await browser.close();
  await new Promise(resolve=>proxy.close(resolve));
  rmSync(certificateDir,{recursive:true,force:true});
}

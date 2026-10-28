import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";

const baseURL = process.env.AVEN_VISUAL_BASE_URL || "http://127.0.0.1";
const email = process.env.AVEN_VISUAL_EMAIL || "stage21-admin@example.com";
const password = process.env.AVEN_VISUAL_PASSWORD || "Stage21-test-password-482!";
const outputRoot = path.resolve("visual-evidence");

const viewports = [
  { name: "1280x720", width: 1280, height: 720 },
  { name: "1366x768", width: 1366, height: 768 },
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1600x900", width: 1600, height: 900 },
  { name: "1920x1080", width: 1920, height: 1080 },
  { name: "2560x1440", width: 2560, height: 1440 },
  { name: "1366x650", width: 1366, height: 650 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "768x768", width: 768, height: 768 },
  { name: "480x800", width: 480, height: 800 },
  { name: "375x812", width: 375, height: 812 },
];

const primaryRoutes = [
  ["dashboard", "/"],
  ["billing", "/billing"],
  ["reservations", "/rds/reservations"],
  ["inventory", "/inventory"],
  ["recommendations", "/opportunities"],
  ["settings", "/settings/appearance"],
  ["flow", "/flow"],
  ["collections", "/collections"],
  ["scans", "/scans"],
];

const settingsRoutes = [
  ["settings-accounts", "/settings/accounts"],
  ["settings-appearance", "/settings/appearance"],
  ["settings-audit", "/settings/audit"],
  ["settings-billing-profiles", "/settings/billing/profiles"],
  ["settings-https", "/settings/https"],
  ["settings-opportunities", "/settings/opportunities"],
  ["settings-policies", "/settings/policies"],
  ["settings-pricing-oci", "/settings/pricing/oci"],
  ["settings-security", "/settings/security"],
  ["settings-sessions", "/settings/sessions"],
  ["settings-usage-costs", "/settings/usage-costs"],
  ["settings-users", "/settings/users"],
];

const themeLabels = { light: "Claro", dark: "Escuro", system: "Sistema" };
const results = [];

const keyFor = (routeName, viewportName, theme) => `${routeName}__${viewportName}__${theme}`;
const ensureDir = (dir) => fs.mkdir(dir, { recursive: true });

async function setTheme(page, theme) {
  await page.emulateMedia({
    colorScheme: theme === "system" ? "dark" : theme,
    reducedMotion: "reduce",
  });

  const trigger = page.getByRole("button", { name: /^Tema:/ });
  await trigger.waitFor({ state: "visible", timeout: 10_000 });
  const current = await trigger.getAttribute("aria-label");
  if (!current?.includes(themeLabels[theme])) {
    await trigger.click();
    const option = page.getByRole("menuitem", {
      name: new RegExp(`^${themeLabels[theme]}`),
    });
    await option.waitFor({ state: "visible", timeout: 5_000 });
    await option.click();
  }
  await page.waitForTimeout(120);
}

async function inspectThemeOverlay(page) {
  const trigger = page.getByRole("button", { name: /^Tema:/ });
  await trigger.click();
  const menu = page.getByLabel("Selecionar tema");
  await menu.waitFor({ state: "visible", timeout: 5_000 });
  const rect = await menu.boundingBox();
  const viewport = page.viewportSize();
  const geometryPass = Boolean(
    rect && viewport &&
      rect.x >= -1 && rect.y >= -1 &&
      rect.x + rect.width <= viewport.width + 1 &&
      rect.y + rect.height <= viewport.height + 1
  );
  await page.keyboard.press("Escape");
  await menu.waitFor({ state: "hidden", timeout: 2_000 });
  const focusReturned = await trigger.evaluate((element) => element === document.activeElement);
  return { pass: geometryPass && focusReturned, geometryPass, focusReturned, rect, viewport };
}

async function inspectLayout(page) {
  return page.evaluate(() => {
    const main = document.querySelector("#main-content");
    const h1 = main?.querySelector("h1");
    const mainRect = main?.getBoundingClientRect() ?? null;
    const h1Rect = h1?.getBoundingClientRect() ?? null;
    const style = main ? getComputedStyle(main) : null;
    return {
      htmlOverflow: document.documentElement.scrollWidth - window.innerWidth,
      bodyOverflow: document.body.scrollWidth - window.innerWidth,
      mainRect: mainRect ? { x: mainRect.x, y: mainRect.y, width: mainRect.width, height: mainRect.height } : null,
      h1Rect: h1Rect ? { x: h1Rect.x, y: h1Rect.y, width: h1Rect.width, height: h1Rect.height } : null,
      mainOverflowY: style?.overflowY ?? null,
      mainScrollHeight: main?.scrollHeight ?? null,
      mainClientHeight: main?.clientHeight ?? null,
      pageTitle: h1?.textContent?.trim() ?? null,
      dataTheme: document.documentElement.dataset.theme ?? null,
      sidebarState: document.documentElement.dataset.sidebar ?? null,
    };
  });
}

async function inspectMainScroll(page) {
  return page.evaluate(async () => {
    const main = document.querySelector("#main-content");
    if (!(main instanceof HTMLElement)) {
      return { applicable: false, pass: false, reason: "main missing" };
    }
    if (main.scrollHeight <= main.clientHeight + 1) {
      return { applicable: false, pass: true, reason: "content does not require vertical scroll" };
    }
    const before = main.scrollTop;
    main.scrollTop = Math.min(120, main.scrollHeight - main.clientHeight);
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const after = main.scrollTop;
    main.scrollTop = before;
    return { applicable: true, pass: after > before, before, after };
  });
}

async function inspectSelectContainment(page) {
  return page.evaluate(() => {
    const controls = Array.from(document.querySelectorAll("select"))
      .filter((select) => {
        const rect = select.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      })
      .map((select) => {
        const shell = select.parentElement;
        if (!(shell instanceof HTMLElement)) return { pass: false, reason: "missing shell" };
        const controlRect = select.getBoundingClientRect();
        const shellRect = shell.getBoundingClientRect();
        const pass =
          controlRect.top >= shellRect.top - 1 &&
          controlRect.bottom <= shellRect.bottom + 1 &&
          controlRect.left >= shellRect.left - 1 &&
          controlRect.right <= shellRect.right + 1;
        return {
          pass,
          multiple: select.multiple,
          control: { x: controlRect.x, y: controlRect.y, width: controlRect.width, height: controlRect.height },
          shell: { x: shellRect.x, y: shellRect.y, width: shellRect.width, height: shellRect.height },
        };
      });
    return { pass: controls.every((item) => item.pass), controls };
  });
}

async function captureRoute(page, routeName, route, viewportName, theme) {
  const key = keyFor(routeName, viewportName, theme);
  const shotDir = path.join(outputRoot, "screenshots", viewportName, theme);
  await ensureDir(shotDir);

  const response = await page.goto(`${baseURL}${route}`, {
    waitUntil: "domcontentloaded",
    timeout: 30_000,
  });
  await page.locator("#main-content").waitFor({ state: "visible", timeout: 15_000 });
  await page.waitForTimeout(350);
  await setTheme(page, theme);

  const layout = await inspectLayout(page);
  const scroll = await inspectMainScroll(page);
  const selectContainment = await inspectSelectContainment(page);
  const overlay = await inspectThemeOverlay(page);
  const viewport = page.viewportSize();
  const checks = {
    httpPass: Boolean(response?.ok()),
    globalOverflowPass: layout.htmlOverflow <= 1 && layout.bodyOverflow <= 1,
    headerVisiblePass: Boolean(layout.h1Rect && viewport && layout.h1Rect.y >= -1 && layout.h1Rect.y < viewport.height),
    mainVisiblePass: Boolean(layout.mainRect && layout.mainRect.width > 0 && layout.mainRect.height > 0),
    scroll,
    selectContainment,
    overlay,
  };
  const pass = checks.httpPass && checks.globalOverflowPass && checks.headerVisiblePass && checks.mainVisiblePass && scroll.pass && selectContainment.pass && overlay.pass;

  await page.screenshot({
    path: path.join(shotDir, `${routeName}.png`),
    fullPage: false,
    animations: "disabled",
  });

  results.push({ key, routeName, route, viewport: viewportName, theme, httpStatus: response?.status() ?? null, pass, checks, layout });
}

async function captureSafely(page, routeName, route, viewportName, theme) {
  try {
    await captureRoute(page, routeName, route, viewportName, theme);
  } catch (error) {
    const key = keyFor(routeName, viewportName, theme);
    const shotDir = path.join(outputRoot, "screenshots", viewportName, theme);
    await ensureDir(shotDir);
    try {
      await page.screenshot({ path: path.join(shotDir, `${routeName}-error.png`), fullPage: false });
    } catch {}
    results.push({
      key,
      routeName,
      route,
      viewport: viewportName,
      theme,
      pass: false,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

async function loginAndStorage(browser) {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const page = await context.newPage();
  await page.goto(`${baseURL}/login`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 15_000 });
  if (page.url().includes("/mfa-setup")) {
    throw new Error("Visual validation account unexpectedly requires MFA enrollment");
  }
  await page.locator("#main-content").waitFor({ state: "visible", timeout: 15_000 });
  const state = await context.storageState();
  await context.close();
  return state;
}

async function runMatrix(browser, storageState) {
  for (const viewport of viewports) {
    const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height }, storageState });
    const page = await context.newPage();
    for (const [routeName, route] of primaryRoutes) {
      await captureSafely(page, routeName, route, viewport.name, "light");
    }
    await context.close();
  }

  for (const theme of ["dark", "system"]) {
    const viewport = viewports.find((item) => item.name === "1366x768");
    const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height }, storageState });
    const page = await context.newPage();
    for (const [routeName, route] of primaryRoutes) {
      await captureSafely(page, routeName, route, viewport.name, theme);
    }
    await context.close();
  }

  for (const theme of ["light", "dark", "system"]) {
    const viewport = viewports.find((item) => item.name === "1366x768");
    const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height }, storageState });
    const page = await context.newPage();
    for (const [routeName, route] of settingsRoutes) {
      await captureSafely(page, routeName, route, viewport.name, theme);
    }
    await context.close();
  }
}

async function writeReport() {
  const failed = results.filter((item) => !item.pass);
  const summary = {
    generatedAt: new Date().toISOString(),
    baseURL,
    total: results.length,
    passed: results.length - failed.length,
    failed: failed.length,
    failedKeys: failed.map((item) => item.key),
    results,
  };
  await ensureDir(outputRoot);
  await fs.writeFile(path.join(outputRoot, "report.json"), JSON.stringify(summary, null, 2));
  await fs.writeFile(
    path.join(outputRoot, "README.md"),
    [
      "# Aven 24.19 Visual Evidence",
      "",
      `- Total scenarios: ${summary.total}`,
      `- Passed: ${summary.passed}`,
      `- Failed: ${summary.failed}`,
      "- Browser: Chromium / Playwright headless",
      "- Evidence: viewport screenshots plus geometry/overflow/scroll/select-containment/overlay assertions",
      "",
      "## Failures",
      "",
      ...(failed.length ? failed.map((item) => `- ${item.key}${item.error ? ` — ${item.error}` : ""}`) : ["None."]),
      "",
    ].join("\n"),
  );
  return summary;
}

await fs.rm(outputRoot, { recursive: true, force: true });
await ensureDir(outputRoot);
const browser = await chromium.launch({ headless: true });
let summary;
try {
  const storageState = await loginAndStorage(browser);
  await runMatrix(browser, storageState);
  summary = await writeReport();
} finally {
  await browser.close();
}

if (!summary) {
  summary = await writeReport();
}

if (summary.failed) {
  console.error(`Visual validation failed: ${summary.failed}/${summary.total} scenarios`);
  for (const item of summary.results.filter((result) => !result.pass)) {
    console.error(item.key, item.error || item.checks, item.layout || "");
  }
  process.exitCode = 1;
} else {
  console.log(`Visual validation PASS: ${summary.total}/${summary.total} scenarios`);
}

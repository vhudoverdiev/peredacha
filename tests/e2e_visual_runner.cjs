const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const { PNG } = require("pngjs");
const pixelmatchModule = require("pixelmatch");

const pixelmatch = pixelmatchModule.default || pixelmatchModule;

const root = path.resolve(__dirname, "..");
const visualRoot = path.join(__dirname, "e2e_visual");
const baselineDir = path.join(visualRoot, "baseline");
const currentDir = path.join(visualRoot, "current");
const diffDir = path.join(visualRoot, "diff");
const baseUrl = process.env.E2E_VISUAL_BASE_URL || "http://127.0.0.1:5000";
const updateBaseline = process.env.E2E_VISUAL_UPDATE_BASELINE === "1";
const maxDiffPixels = Number(process.env.E2E_VISUAL_MAX_DIFF_PIXELS || "1000");
const visualThreshold = Number(process.env.E2E_VISUAL_THRESHOLD || "0.1");

const credentials = {
  username: process.env.E2E_VISUAL_USERNAME || "e2e-admin",
  password: process.env.E2E_VISUAL_PASSWORD || "E2E-visual-password-2026!",
};

const viewportFilter = new Set(
  (process.env.E2E_VISUAL_VIEWPORTS || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean)
);

const viewports = [
  {
    name: "desktop",
    width: 1365,
    height: 900,
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
  },
  {
    name: "tablet",
    width: 834,
    height: 1112,
    userAgent:
      "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
  },
  {
    name: "mobile",
    width: 390,
    height: 844,
    userAgent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
  },
];

const scenarios = [
  {
    name: "login",
    public: true,
    path: "/login",
    selectors: [".login-form", "input[name=\"username\"]", "input[name=\"password\"]", ".login-submit"],
  },
  {
    name: "dashboard",
    path: "/",
    selectors: ["h1.dashboard-title", ".dashboard-progress-panel", ".dashboard-overview-grid"],
  },
  {
    name: "apartments",
    path: "/apartments",
    selectors: [".apartments-page", ".apartments-filter-form", "[data-ajax-pagination-sync=\"apartments-export\"]"],
    scenario: async (page) => {
      const disabledCount = await page.locator("button:disabled, input:disabled, select:disabled, .disabled").count();
      if (disabledCount < 1) {
        throw new Error("apartments: expected at least one disabled state before filtering");
      }
      await page.fill("input[name=\"q\"]", "12");
      await Promise.all([
        page.waitForURL((url) => url.searchParams.get("q") === "12", { timeout: 8000 }),
        page.locator(".apartments-filter-form button[type=\"submit\"]").click(),
      ]);
      if (!page.url().includes("q=12")) {
        throw new Error(`Apartment filter did not preserve q=12 in URL: ${page.url()}`);
      }
      await expectVisible(page, ".apartments-page");
    },
  },
  {
    name: "tasks",
    path: "/tasks",
    selectors: [".remarks-filter-form", ".remarks-tabs", ".remarks-page-head"],
  },
  {
    name: "site-errors-custom-selects",
    path: "/site-errors",
    selectors: [".developer-section-tabs", ".site-errors-kind-tabs", ".site-errors-filter-form"],
    viewports: ["desktop"],
    skipScreenshot: true,
    credentials: {
      username: "e2e-developer",
      password: "E2E-developer-password-2026!",
    },
    scenario: async (page) => {
      const assertCustomFilters = async (label) => {
        await page.waitForFunction(
          () => {
            const shells = Array.from(document.querySelectorAll(".site-errors-filter-form .js-developer-custom-select"))
              .filter((shell) => !shell.closest("[hidden]"));
            if (shells.length !== 1) return false;
            return shells.every((shell) => {
              const button = shell.querySelector(".developer-select-button");
              const select = shell.querySelector("select");
              if (!button || !select || select.name !== "status") return false;
              const buttonStyle = getComputedStyle(button);
              const buttonRect = button.getBoundingClientRect();
              const selectStyle = getComputedStyle(select);
              const nativeVisible = selectStyle.visibility !== "hidden"
                && selectStyle.display !== "none"
                && Number(selectStyle.opacity || "1") > 0.01
                && select.getBoundingClientRect().height > 1;
              return buttonStyle.display !== "none"
                && buttonStyle.visibility !== "hidden"
                && buttonRect.width > 1
                && buttonRect.height > 1
                && !nativeVisible;
            });
          },
          null,
          { timeout: 8000 },
        ).catch(async (error) => {
          const state = await page.locator(".site-errors-filter-form .js-developer-custom-select").evaluateAll((shells) => shells.map((shell) => {
            const button = shell.querySelector(".developer-select-button");
            const select = shell.querySelector("select");
            const buttonRect = button?.getBoundingClientRect();
            const selectRect = select?.getBoundingClientRect();
            const selectStyle = select ? getComputedStyle(select) : null;
            return {
              className: shell.className,
              hiddenAncestor: Boolean(shell.closest("[hidden]")),
              hasButton: Boolean(button),
              buttonHidden: Boolean(button?.hidden),
              buttonRect: buttonRect ? { width: buttonRect.width, height: buttonRect.height } : null,
              selectClassName: select?.className || "",
              selectVisibility: selectStyle?.visibility || "",
              selectOpacity: selectStyle?.opacity || "",
              selectRect: selectRect ? { width: selectRect.width, height: selectRect.height } : null,
            };
          }));
          throw new Error(`${label}: site error filters are not custom selects after AJAX navigation: ${JSON.stringify(state)}\n${error.message}`);
        });
      };

      await assertCustomFilters("initial");
      await Promise.all([
        page.waitForURL((url) => url.pathname === "/developer/statistics", { timeout: 8000 }),
        page.locator('.developer-section-tabs .remarks-tab-link[href*="/developer/statistics"]').click(),
      ]);
      await waitForStablePage(page);
      await Promise.all([
        page.waitForURL((url) => url.pathname === "/site-errors", { timeout: 8000 }),
        page.locator('.developer-section-tabs .remarks-tab-link[href="/site-errors"]').click(),
      ]);
      await waitForStablePage(page);
      await assertCustomFilters("messages-all");

      const clickKindTab = async (name, selector) => {
        await page.locator(selector).click();
        await page.waitForFunction(
          (targetSelector) => document.querySelector(targetSelector)?.classList.contains("active"),
          selector,
          { timeout: 8000 },
        ).catch(async (error) => {
          const state = await page.evaluate((targetSelector) => ({
            href: document.querySelector(targetSelector)?.getAttribute("href") || "",
            url: window.location.href,
            tabs: Array.from(document.querySelectorAll(".site-errors-kind-tabs .remarks-tab-link")).map((link) => ({
              text: link.textContent.trim(),
              href: link.getAttribute("href"),
              className: link.className,
            })),
          }), selector);
          throw new Error(`site-errors kind tab did not become active for ${name}: ${JSON.stringify(state)}\n${error.message}`);
        });
      };

      for (const [name, selector] of [
        ["user", '.site-errors-kind-tabs .remarks-tab-link[href*="kind=user"]'],
        ["registration", '.site-errors-kind-tabs .remarks-tab-link[href*="kind=registration"]'],
        ["system", '.site-errors-kind-tabs .remarks-tab-link[href*="kind=system"]'],
      ]) {
        await clickKindTab(name, selector);
        await waitForStablePage(page);
        await assertCustomFilters(`kind-${name}`);
      }
    },
  },
];

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function cleanDir(dir) {
  ensureDir(dir);
  for (const entry of fs.readdirSync(dir)) {
    fs.rmSync(path.join(dir, entry), { recursive: true, force: true });
  }
}

function scenarioFileName(scenarioName, viewportName) {
  return `${scenarioName}-${viewportName}.png`;
}

async function expectVisible(page, selector, label) {
  const locator = page.locator(selector).first();
  try {
    await locator.waitFor({ state: "visible", timeout: 8000 });
  } catch (error) {
    const snippet = (await page.content().catch(() => "")).slice(0, 1200);
    throw new Error(
      `${label}: selector ${selector} not visible at ${page.url()}\n${snippet}\n${error.message}`
    );
  }
}

async function waitForStablePage(page) {
  await page.waitForLoadState("domcontentloaded", { timeout: 5000 }).catch(() => {});
  await page.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});
  await page.waitForFunction(
    () =>
      !document.documentElement.classList.contains("desktop-styles-pending") &&
      !document.documentElement.classList.contains("mobile-styles-pending"),
    null,
    { timeout: 15000 }
  ).catch(() => {});
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-delay: 0s !important;
        animation-duration: 0s !important;
        animation-iteration-count: 1 !important;
        scroll-behavior: auto !important;
        transition-delay: 0s !important;
        transition-duration: 0s !important;
      }
      html { caret-color: transparent !important; }
    `,
  });
}

async function login(page, loginCredentials = credentials) {
  await page.goto(`${baseUrl}/login`, { waitUntil: "commit", timeout: 15000 });
  await waitForStablePage(page);
  await page.fill("input[name=\"username\"]", loginCredentials.username);
  await page.fill("input[name=\"password\"]", loginCredentials.password);
  await page.locator(".login-form").evaluate((form) => {
    form.dataset.csrfReady = "1";
  });
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 10000 }),
    page.locator(".login-submit").click(),
  ]);
  await waitForStablePage(page);
}

async function assertNoHorizontalScroll(page, label) {
  const metrics = await page.evaluate(() => ({
    documentScrollWidth: document.documentElement.scrollWidth,
    documentClientWidth: document.documentElement.clientWidth,
    bodyScrollWidth: document.body ? document.body.scrollWidth : 0,
    bodyClientWidth: document.body ? document.body.clientWidth : 0,
  }));
  const documentOverflow = metrics.documentScrollWidth - metrics.documentClientWidth;
  const bodyOverflow = metrics.bodyScrollWidth - metrics.bodyClientWidth;
  if (documentOverflow > 1 || bodyOverflow > 1) {
    throw new Error(`${label}: horizontal scroll detected ${JSON.stringify(metrics)}`);
  }
}

async function assertKeyboardAccess(page, label) {
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  const active = await page.evaluate(() => {
    const element = document.activeElement;
    if (!element || element === document.body) return null;
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return {
      tagName: element.tagName,
      role: element.getAttribute("role"),
      tabIndex: element.tabIndex,
      visible: rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none",
      focusIndicator:
        style.outlineStyle !== "none" ||
        style.outlineWidth !== "0px" ||
        style.boxShadow !== "none" ||
        style.borderColor !== "",
    };
  });
  if (!active || !active.visible) {
    throw new Error(`${label}: keyboard focus did not land on a visible element`);
  }
  if (!["A", "BUTTON", "INPUT", "SELECT", "TEXTAREA"].includes(active.tagName) && active.tabIndex < 0 && !active.role) {
    throw new Error(`${label}: keyboard focus landed on a non-interactive element ${JSON.stringify(active)}`);
  }
  if (!active.focusIndicator) {
    throw new Error(`${label}: focused element has no detectable focus indicator`);
  }
}

async function assertInteractiveStates(page, label) {
  const candidates = page.locator("button:not([disabled]), a[href], input, select");
  const count = await candidates.count();
  let locator = null;
  for (let index = 0; index < count; index += 1) {
    const candidate = candidates.nth(index);
    if (await candidate.isVisible()) {
      locator = candidate;
      break;
    }
  }
  if (!locator) {
    throw new Error(`${label}: no visible interactive element found`);
  }
  await locator.hover();
  const hoverVisible = await locator.isVisible();
  await locator.focus();
  const focusVisible = await locator.isVisible();
  if (!hoverVisible || !focusVisible) {
    throw new Error(`${label}: hover/focus made the first interactive element invisible`);
  }
}

function compareOrUpdateScreenshot(name) {
  const baselinePath = path.join(baselineDir, name);
  const currentPath = path.join(currentDir, name);
  const diffPath = path.join(diffDir, name);

  if (updateBaseline) {
    fs.copyFileSync(currentPath, baselinePath);
    return { diffPixels: 0, updated: true };
  }

  if (!fs.existsSync(baselinePath)) {
    throw new Error(`Missing visual baseline: ${path.relative(root, baselinePath)}. Run with E2E_VISUAL_UPDATE_BASELINE=1 first.`);
  }

  const baseline = PNG.sync.read(fs.readFileSync(baselinePath));
  const current = PNG.sync.read(fs.readFileSync(currentPath));
  if (baseline.width !== current.width || baseline.height !== current.height) {
    throw new Error(`${name}: screenshot dimensions changed from ${baseline.width}x${baseline.height} to ${current.width}x${current.height}`);
  }

  const diff = new PNG({ width: baseline.width, height: baseline.height });
  const diffPixels = pixelmatch(
    baseline.data,
    current.data,
    diff.data,
    baseline.width,
    baseline.height,
    { threshold: visualThreshold }
  );
  if (diffPixels > maxDiffPixels) {
    fs.writeFileSync(diffPath, PNG.sync.write(diff));
    throw new Error(`${name}: visual diff has ${diffPixels} pixels, threshold is ${maxDiffPixels}. Diff: ${path.relative(root, diffPath)}`);
  }
  return { diffPixels, updated: false };
}

async function exerciseScenario(page, scenario, viewport, errors) {
  const label = `${scenario.name}/${viewport.name}`;
  await page.goto(`${baseUrl}${scenario.path}`, { waitUntil: "commit", timeout: 15000 });
  await waitForStablePage(page);
  for (const selector of scenario.selectors) {
    await expectVisible(page, selector, label);
  }
  if (scenario.scenario) {
    await scenario.scenario(page, viewport);
    await waitForStablePage(page);
  }
  await assertNoHorizontalScroll(page, label);
  await assertKeyboardAccess(page, label);
  await assertInteractiveStates(page, label);
  if (errors.length) {
    throw new Error(`${label}: browser console/page errors:\n${errors.join("\n")}`);
  }

  if (scenario.skipScreenshot) {
    return { diffPixels: 0, skippedScreenshot: true };
  }

  const screenshotName = scenarioFileName(scenario.name, viewport.name);
  await page.screenshot({
    path: path.join(currentDir, screenshotName),
    fullPage: true,
    animations: "disabled",
  });
  return compareOrUpdateScreenshot(screenshotName);
}

async function newScenarioPage(browser, viewport, errors) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    userAgent: viewport.userAgent,
    deviceScaleFactor: 1,
    locale: "ru-RU",
    serviceWorkers: "block",
  });
  const page = await context.newPage();
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console error: ${message.text()}`);
  });
  page.on("pageerror", (error) => errors.push(`page error: ${error.message}`));
  return { context, page };
}

async function runPublicScenario(browser, scenario, viewport) {
  console.log(`E2E_VISUAL_START ${scenario.name}/${viewport.name}`);
  const errors = [];
  const { context, page } = await newScenarioPage(browser, viewport, errors);
  try {
    return await exerciseScenario(page, scenario, viewport, errors);
  } finally {
    await context.close();
  }
}

async function runAuthenticatedScenarios(browser, viewport, authenticatedScenarios) {
  console.log(`E2E_VISUAL_LOGIN ${viewport.name}`);
  const errors = [];
  const { context, page } = await newScenarioPage(browser, viewport, errors);

  try {
    await login(page);
    let activeUsername = credentials.username;
    const results = [];
    for (const scenario of authenticatedScenarios) {
      console.log(`E2E_VISUAL_START ${scenario.name}/${viewport.name}`);
      errors.length = 0;
      if (scenario.credentials && scenario.credentials.username !== activeUsername) {
        await page.request.post(`${baseUrl}/logout`).catch(() => {});
        await login(page, scenario.credentials);
        activeUsername = scenario.credentials.username;
      }
      results.push({
        scenario: scenario.name,
        viewport: viewport.name,
        ...(await exerciseScenario(page, scenario, viewport, errors)),
      });
    }
    return results;
  } finally {
    await context.close();
  }
}

async function main() {
  ensureDir(visualRoot);
  ensureDir(baselineDir);
  cleanDir(currentDir);
  cleanDir(diffDir);

  const launchOptions = { headless: true };
  if (process.env.E2E_VISUAL_BROWSER_EXECUTABLE) {
    launchOptions.executablePath = process.env.E2E_VISUAL_BROWSER_EXECUTABLE;
  }
  const browser = await chromium.launch(launchOptions);
  const results = [];
  try {
    for (const viewport of viewports.filter((item) => !viewportFilter.size || viewportFilter.has(item.name))) {
      const allowedInViewport = (scenario) => !scenario.viewports || scenario.viewports.includes(viewport.name);
      const publicScenarios = viewport.name === "desktop"
        ? scenarios.filter((scenario) => scenario.public && allowedInViewport(scenario))
        : [];
      const authenticatedScenarios = scenarios.filter((scenario) => !scenario.public && allowedInViewport(scenario));
      for (const scenario of publicScenarios) {
        const result = await runPublicScenario(browser, scenario, viewport);
        results.push({ scenario: scenario.name, viewport: viewport.name, ...result });
      }
      if (authenticatedScenarios.length) {
        results.push(...(await runAuthenticatedScenarios(browser, viewport, authenticatedScenarios)));
      }
    }
  } finally {
    await browser.close();
  }

  console.log(JSON.stringify({ updateBaseline, maxDiffPixels, results }, null, 2));
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});

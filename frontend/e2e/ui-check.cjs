// Browser end-to-end check of the whole case workspace (Playwright, Chromium).
//
//   CW_WEB=http://127.0.0.1:3100 CW_USER=admin CW_PASSWORD=... CW_CASE=CW-XXXXXX \
//   [CW_API_PROXY_FROM=http://127.0.0.1:8010 CW_API_PROXY_TO=http://127.0.0.1:8110] \
//   [CW_RUN_PIPELINE=1 CW_SAMPLE_DIR=".../Sample test case"] node e2e/ui-check.cjs <tag>
//
// With CW_RUN_PIPELINE=1 the script creates a case through the UI, uploads the sample evidence through the UI,
// clicks "Run pipeline", waits for it and then runs the same checks as for an existing case (CW_CASE).
// CW_API_PROXY_* forwards a hard-coded API address to another port (used only to test older builds).
// Writes e2e/out/<tag>.json and screenshots to e2e/out/<tag>-*.png. Exit code 1 if any check failed.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const TAG = process.argv[2] || "run";
const WEB = process.env.CW_WEB || "http://127.0.0.1:3000";
const USER = process.env.CW_USER || "admin";
const PASSWORD = process.env.CW_PASSWORD;
const OUT = path.join(__dirname, "out");
fs.mkdirSync(OUT, { recursive: true });
if (!PASSWORD) {
  console.error("Set CW_PASSWORD (the admin password of the API under test).");
  process.exit(2);
}

const report = { tag: TAG, web: WEB, checks: [], consoleErrors: [], pageErrors: [], failedRequests: [] };
function check(name, ok, detail = "") {
  report.checks.push({ name, ok: !!ok, detail: String(detail).slice(0, 300) });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? "  " + String(detail).slice(0, 160) : ""));
}
const save = () => fs.writeFileSync(path.join(OUT, `${TAG}.json`), JSON.stringify(report, null, 1));

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 }, acceptDownloads: true });
  const page = await ctx.newPage();
  page.on("console", (m) => { if (m.type() === "error") report.consoleErrors.push(m.text().slice(0, 300)); });
  page.on("pageerror", (e) => report.pageErrors.push(String(e).slice(0, 300)));
  page.on("response", (r) => { if (r.status() >= 400) report.failedRequests.push(`${r.status()} ${r.request().method()} ${r.url().replace(/^https?:\/\/[^/]+/, "")}`); });
  page.on("dialog", (d) => d.accept(d.type() === "prompt" ? "UI test: verified against the source exhibit" : undefined));

  if (process.env.CW_API_PROXY_FROM) {
    const from = process.env.CW_API_PROXY_FROM, to = process.env.CW_API_PROXY_TO;
    await ctx.route(from + "/**", async (route) => {
      const url = route.request().url().replace(from, to);
      try { await route.fulfill({ response: await route.fetch({ url }) }); } catch (e) { await route.abort(); }
    });
  }
  const shot = (n) => page.screenshot({ path: path.join(OUT, `${TAG}-${n}.png`), fullPage: false }).catch(() => {});
  const tabButton = (label) => page.getByRole("button", { name: label });

  try {
    // ---- login
    await page.goto(WEB + "/login");
    await page.getByRole("textbox").first().fill(USER);
    await page.locator('input[type="password"]').fill("definitely-wrong-password");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForTimeout(1500);
    check("wrong password is rejected with a message", await page.getByText(/invalid username or password/i).count() > 0);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL(WEB + "/", { timeout: 20000 }).catch(() => {});
    check("login lands on the command center", await page.getByText("Case Command Center").count() > 0, page.url());
    await shot("1-command-center");

    let caseId = process.env.CW_CASE;
    if (process.env.CW_RUN_PIPELINE === "1") {
      const dir = process.env.CW_SAMPLE_DIR;
      await page.getByPlaceholder(/New case title/i).fill("UI-driven: MedVantage Pharmacy Burglary & Narcotics Theft");
      await page.getByRole("button", { name: "New case" }).click();
      await page.waitForURL(/\/case\/CW-/, { timeout: 20000 });
      caseId = page.url().split("/case/")[1];
      check("case created from the UI", !!caseId, caseId);
      await tabButton("Evidence Explorer").click();
      const files = ["01_forensic_inspection_report.pdf", "02_intrusion_alarm_log.json", "03_cctv_alleyway_log.txt", "04_witness_statement_sundaram.txt",
        "05_witness_statement_pharmacist.txt", "photos/01_tampered_rear_shutter.jpg", "photos/02_toppled_narcotics_cabinet.jpg",
        "photos/03_discarded_crowbar_and_glove.jpg", "photos/04_cash_drawer_and_counter.jpg"].map((f) => path.join(dir, f));
      await page.locator('input[type="file"]').first().setInputFiles(files);
      await page.waitForFunction((n) => document.body.innerText.includes("05_witness_statement_pharmacist.txt"), null, { timeout: 120000 }).catch(() => {});
      await shot("2-uploaded");
      check("all nine files visible after upload", (await page.getByText(/\.(pdf|json|txt|jpg)/).count()) >= 9);
      await page.getByPlaceholder(/legal|query|admissib/i).first().fill("Admissibility of electronic intrusion logs and CCTV timestamp discrepancies under Section 63 Bharatiya Sakshya Adhiniyam 2023").catch(() => {});
      await page.getByRole("button", { name: /run (pipeline|analysis)/i }).first().click();
      const t0 = Date.now();
      let finished = false;
      while (Date.now() - t0 < 40 * 60 * 1000) {
        const body = await page.locator("body").innerText();
        if (/Finished in \d+s/.test(body)) { finished = true; break; }
        if (/Failed:/.test(body)) break;
        await page.waitForTimeout(10000);
      }
      check("pipeline run from the UI finishes", finished, `${Math.round((Date.now() - t0) / 1000)}s`);
    }
    if (!caseId) throw new Error("no case id (set CW_CASE or CW_RUN_PIPELINE=1)");
    report.caseId = caseId;

    // ---- case workspace
    await page.goto(`${WEB}/case/${caseId}`);
    await page.waitForSelector("text=Evidence items", { timeout: 20000 });
    await page.waitForSelector("text=/audit chain: /", { timeout: 20000 }).catch(() => {});
    check("case header shows audit chain PASSED", await page.getByText(/audit chain: PASSED/).count() > 0);

    // studio
    await tabButton(/Incident Reconstruction Studio/).click();
    await page.waitForTimeout(2500);
    const body1 = await page.locator("body").innerText();
    check("studio shows timeline events with clock times", /\b0?\d:\d{2}\b/.test(body1));
    await shot("3-studio");
    const ask = page.locator("textarea").first();
    if (await ask.count()) {
      await ask.fill("What time did the rear shutter alarm trigger according to the alarm log?");
      await ask.press("Enter");
      await page.waitForFunction(() => /02:2\d/.test(document.body.innerText) && /Sources|EV-/.test(document.body.innerText), null, { timeout: 90000 }).catch(() => {});
      check("evidence chat answers with the alarm time and sources", /02:2\d/.test(await page.locator("body").innerText()));
    } else check("chat input present", false);

    // 3D scene: a case with no scene yet gets one built from the UI button
    const genBtn = page.getByRole("button", { name: /Generate scene from evidence/ });
    if (await genBtn.count() && await genBtn.first().isVisible()) {
      await genBtn.first().click();
      await page.waitForSelector("canvas", { timeout: 25 * 60 * 1000 }).catch(() => {});
      check("scene generated from the UI button", await page.locator("canvas").count() > 0);
    }
    await page.waitForSelector("canvas", { timeout: 60000 }).catch(() => {});
    check("3D scene canvas is rendered", await page.locator("canvas").count() > 0);
    const canvas = page.locator("canvas").first();
    if (await canvas.count()) {
      const box = await canvas.boundingBox();
      check("3D canvas has a real size", box && box.width > 300 && box.height > 200, JSON.stringify(box));
      await canvas.hover().catch(() => {});
      await page.mouse.wheel(0, -400).catch(() => {});
    }
    const scenarioBtns = page.locator("button", { hasText: /^#\d/ });
    check("scenario tabs listed", await scenarioBtns.count() >= 1, await scenarioBtns.count());
    if (await scenarioBtns.count() > 1) { await scenarioBtns.nth(1).click(); await page.waitForTimeout(800); }
    await shot("4-scene");

    // conflicts
    await tabButton(/Conflict Analysis/).click();
    await page.waitForTimeout(1200);
    const conflictCount = Number(((await tabButton(/Conflict Analysis/).innerText()).match(/\((\d+)\)/) || [])[1] || 0);
    report.conflictCount = conflictCount;
    check("conflict tab reachable", true, `${conflictCount} conflicts`);
    await shot("5-conflicts");
    const row = page.locator("button, div").filter({ hasText: /^CFL-/ }).first();
    if (conflictCount > 0 && await row.count()) {
      await row.click().catch(() => {});
      const confirmBtn = page.getByRole("button", { name: /^confirm/i }).first();
      if (await confirmBtn.count()) {
        await confirmBtn.click();
        await page.waitForTimeout(1500);
        check("reviewing a conflict records a reason and updates status", /confirmed/i.test(await page.locator("body").innerText()));
      }
    }

    // patterns / legal / report
    await tabButton(/Pattern Intelligence/).click();
    await page.waitForFunction(() => !/Scanning case signatures/.test(document.body.innerText), null, { timeout: 120000 }).catch(() => {});
    check("pattern tab renders a signature or an honest unavailable notice", /Modus Operandi|M\.O\.|signature|unavailable|not established/i.test(await page.locator("body").innerText()));
    await shot("6-patterns");
    await tabButton(/Legal Section/).click();
    await page.waitForFunction(() => !/Synthesizing statutory charges/.test(document.body.innerText), null, { timeout: 180000 }).catch(() => {});
    const legalText = await page.locator("body").innerText();
    check("legal tab renders sections", /BNS|BNSS|Section/i.test(legalText));
    report.legalHasSuspectFabrication = /dark hooded jacket|blue nitrile gloves/i.test(legalText);
    check("legal tab does not invent suspect demographics", !report.legalHasSuspectFabrication);
    await shot("7-legal");
    await tabButton(/^Report$/).click();
    await page.waitForTimeout(1500);
    const viewBtn = page.getByRole("button", { name: /view|load|show/i }).first();
    if (await viewBtn.count()) await viewBtn.click();
    await page.waitForTimeout(2500);
    check("report tab shows the report", /CaseWeave Report|Evidence Inventory|Case Overview/.test(await page.locator("body").innerText()));
    const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 60000 }).catch(() => null), page.getByRole("button", { name: /Download formatted PDF/ }).click().catch(() => {})]);
    check("PDF report downloads", !!dl, dl && dl.suggestedFilename());
    await shot("8-report");

    // sign out clears browser-stored chat
    await page.goto(WEB + "/");
    await page.getByText("sign out").click();
    await page.waitForURL(/login/, { timeout: 10000 }).catch(() => {});
    const leftover = await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("cw_chat_") || k === "cw_token"));
    check("sign-out removes the token and saved chat from the browser", leftover.length === 0, leftover.join(","));
    // unauthenticated deep link bounces to login
    await page.goto(`${WEB}/case/${caseId}`);
    await page.waitForURL(/login/, { timeout: 10000 }).catch(() => {});
    check("deep link without a session goes to the login page", /login/.test(page.url()));
  } catch (e) {
    check("script ran to the end", false, e && e.message);
    await page.screenshot({ path: path.join(OUT, `${TAG}-crash.png`) }).catch(() => {});
  }
  report.failed = report.checks.filter((c) => !c.ok).length;
  console.log(`console errors: ${report.consoleErrors.length}, page errors: ${report.pageErrors.length}, failed requests: ${report.failedRequests.length}`);
  save();
  await browser.close();
  process.exit(report.failed ? 1 : 0);
})();

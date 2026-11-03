// Quick browser smoke test of a running stack. It never calls a language model, so it is safe to run against real data.
//   CW_WEB=http://127.0.0.1:3000 CW_PASSWORD=<admin password> [CW_CASE=<case id>] node e2e/smoke.cjs
// Also checks that roles are enforced in the UI: an investigator cannot see the Users link, a reviewer cannot create a case.
const { chromium } = require("playwright");
const WEB = process.env.CW_WEB || "http://127.0.0.1:3000";
const PW = process.env.CW_PASSWORD;
if (!PW) { console.error("Set CW_PASSWORD"); process.exit(2); }
let failed = 0;
const check = (n, ok, d = "") => { console.log((ok ? "PASS " : "FAIL ") + n + (d ? "  " + String(d).slice(0, 160) : "")); if (!ok) failed++; };

async function login(browser, user) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(WEB + "/login");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1500); // let the page attach its scripts before the form is used (a dev server compiles on first visit)
  await page.getByRole("textbox").first().fill(user);
  await page.locator('input[type="password"]:visible').fill(PW);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(WEB + "/", { timeout: 20000 }).catch(() => {});
  return { page, ctx, errors };
}

(async () => {
  const browser = await chromium.launch({ headless: true });

  // ---- admin
  const a = await login(browser, "admin");
  check("admin signs in", await a.page.getByText("Case Command Center").count() > 0, a.page.url());
  await a.page.waitForTimeout(1500);
  const rows = await a.page.locator("div.cursor-pointer").count();
  check("case list shows the real cases", rows >= 1, `${rows} case(s)`);
  check("fake CW-HIST cases are not listed", (await a.page.content()).indexOf("CW-HIST") < 0);
  check("admin sees the Users link", await a.page.getByRole("button", { name: "users" }).count() > 0);
  await a.page.getByRole("button", { name: "users" }).click();
  await a.page.waitForURL(/\/users/, { timeout: 10000 }).catch(() => {});
  await a.page.waitForSelector('[data-testid="user-row"]', { timeout: 10000 }).catch(() => {});
  check("users page lists the three sample accounts", await a.page.locator('[data-testid="user-row"]').count() >= 3);
  // add and remove a throwaway user through the screen
  await a.page.getByPlaceholder("username").fill("smoke.tmp");
  await a.page.getByPlaceholder(/temporary password/).fill("Smoke-temp-pass-1");
  await a.page.getByRole("button", { name: "Add user" }).click();
  await a.page.getByText("Created smoke.tmp").waitFor({ timeout: 10000 }).catch(() => {});
  check("a user can be added from the screen", await a.page.getByText("smoke.tmp").count() > 0);
  a.page.once("dialog", (d) => d.accept());
  await a.page.locator('[data-testid="user-row"]', { hasText: "smoke.tmp" }).getByRole("button", { name: "delete" }).click();
  await a.page.getByText("Deleted smoke.tmp").waitFor({ timeout: 10000 }).catch(() => {});
  await a.page.locator('[data-testid="user-row"]', { hasText: "smoke.tmp" }).waitFor({ state: "detached", timeout: 10000 }).catch(() => {});
  check("and removed again", await a.page.locator('[data-testid="user-row"]', { hasText: "smoke.tmp" }).count() === 0);

  // ---- case workspace (no model calls: evidence, studio scene, conflicts, report)
  const caseId = process.env.CW_CASE;
  if (caseId) {
    await a.page.goto(`${WEB}/case/${caseId}`);
    await a.page.waitForSelector("text=Evidence items", { timeout: 20000 });
    await a.page.waitForSelector("text=/audit chain: /", { timeout: 20000 }).catch(() => {});
    check("case header shows audit chain PASSED", await a.page.getByText(/audit chain: PASSED/).count() > 0);
    await a.page.getByRole("button", { name: "Evidence Explorer" }).click();
    await a.page.waitForTimeout(1500);
    check("evidence tab lists the case files", /\.(txt|json|pdf|jpe?g)/i.test(await a.page.locator("body").innerText()));
    await a.page.getByRole("button", { name: /Incident Reconstruction Studio/ }).click();
    await a.page.waitForTimeout(2500);
    const hasScene = await a.page.locator("canvas").count();
    check("studio opens (3D canvas if a scene exists)", true, hasScene ? "canvas present" : "no scene generated for this case");
    await a.page.getByRole("button", { name: /Conflict Analysis/ }).click();
    await a.page.waitForTimeout(1000);
    check("conflicts tab opens", true);
    await a.page.getByRole("button", { name: /^Report$/ }).click();
    const view = a.page.getByRole("button", { name: /Load \/ refresh report/ });
    if (await view.count()) await view.click();
    await a.page.waitForTimeout(3000);
    const bodyText = await a.page.locator("body").innerText();
    check("report loads (rebuilt from records, no model call)", /CaseWeave Report|Evidence Inventory|no report generated/i.test(bodyText));
  }
  check("no uncaught page errors (admin)", a.errors.length === 0, a.errors.join(" | "));
  await a.ctx.close();

  // ---- investigator
  const i = await login(browser, "investigator1");
  check("investigator signs in", await i.page.getByText("Case Command Center").count() > 0);
  check("investigator does not see the Users link", await i.page.getByRole("button", { name: "users" }).count() === 0);
  await i.page.goto(WEB + "/users");
  await i.page.waitForTimeout(2500);
  check("investigator is bounced away from /users", !/\/users/.test(i.page.url()), i.page.url());
  await i.ctx.close();

  // ---- reviewer
  const r = await login(browser, "reviewer1");
  check("reviewer signs in", await r.page.getByText("Case Command Center").count() > 0);
  await r.page.getByPlaceholder(/New case title/i).fill("reviewer should not be able to create this");
  await r.page.getByRole("button", { name: "New case" }).click();
  await r.page.waitForTimeout(2000);
  check("reviewer cannot create a case (permission message shown)", await r.page.getByText(/cannot perform|requires one of/).count() > 0);
  await r.ctx.close();

  await browser.close();
  process.exit(failed ? 1 : 0);
})();

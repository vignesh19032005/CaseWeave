// Browser check of the account-safety flow: a user flagged "must change password" is sent to the change page,
// cannot reach anything else until they change it, and the new password then works.
//   CW_WEB=http://127.0.0.1:3100 CW_TEST_USER=<username> CW_TEST_OLD=<old password> CW_TEST_NEW=<new password> node e2e/auth-ui.cjs
// (create the user with must_change_password=1 first; see backend/tests/test_hardening.py for how)
const { chromium } = require("playwright");
const WEB = process.env.CW_WEB || "http://127.0.0.1:3000";
const { CW_TEST_USER: U, CW_TEST_OLD: OLD, CW_TEST_NEW: NEW } = process.env;
if (!U || !OLD || !NEW) { console.error("Set CW_TEST_USER, CW_TEST_OLD and CW_TEST_NEW"); process.exit(2); }
let failed = 0;
const check = (n, ok, d = "") => { console.log((ok ? "PASS " : "FAIL ") + n + (d ? "  " + d : "")); if (!ok) failed++; };

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await (await browser.newContext()).newPage();
  await page.goto(WEB + "/login");
  await page.getByRole("textbox").first().fill(U);
  await page.locator('input[type="password"]:visible').fill(OLD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/change-password/, { timeout: 15000 }).catch(() => {});
  check("flagged account is sent to the change-password page", /change-password/.test(page.url()), page.url());
  check("the login page no longer prints a default password", !(await (async () => { await page.goto(WEB + "/login"); return (await page.content()).includes("changeme123"); })()));
  await page.goto(WEB + "/");
  await page.waitForTimeout(2500);
  check("home is not usable while the change is pending (bounced to change page)", /change-password/.test(page.url()), page.url());

  const pw = page.locator('input[type="password"]:visible');
  await pw.nth(0).fill(OLD);
  await pw.nth(1).fill("short");
  await pw.nth(2).fill("short");
  await page.getByRole("button", { name: /change password/i }).click();
  check("a too-short new password is refused with a message", await page.getByText(/at least 10 characters/).count() > 0);
  await pw.nth(1).fill(NEW);
  await pw.nth(2).fill(NEW + "x");
  await page.getByRole("button", { name: /change password/i }).click();
  check("mismatched repeat is refused", await page.getByText(/do not match/).count() > 0);
  await pw.nth(2).fill(NEW);
  await page.getByRole("button", { name: /change password/i }).click();
  await page.waitForURL(WEB + "/", { timeout: 15000 }).catch(() => {});
  check("after changing, the user reaches the command center", await page.getByText("Case Command Center").count() > 0, page.url());

  await page.getByText("sign out").click();
  await page.waitForURL(/login/, { timeout: 10000 }).catch(() => {});
  await page.getByRole("textbox").first().fill(U);
  await page.locator('input[type="password"]:visible').fill(OLD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForTimeout(1500);
  check("the old password no longer works", await page.getByText(/invalid username or password/i).count() > 0);
  await page.locator('input[type="password"]:visible').fill(NEW);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(WEB + "/", { timeout: 15000 }).catch(() => {});
  check("the new password works", await page.getByText("Case Command Center").count() > 0);
  await browser.close();
  process.exit(failed ? 1 : 0);
})();

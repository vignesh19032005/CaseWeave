const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function runBrowserTest() {
  console.log('=== Starting CaseWeave End-to-End Browser UI Test ===');

  const screenshotsDir = path.join(__dirname, 'test-screenshots');
  if (!fs.existsSync(screenshotsDir)) {
    fs.mkdirSync(screenshotsDir, { recursive: true });
  }

  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();

  try {
    // 1. Visit root (auto-redirects to /login if unauthenticated)
    console.log('\n[1] Navigating to http://localhost:3000 ...');
    await page.goto('http://localhost:3000', { waitUntil: 'load' });
    await page.waitForTimeout(1000);
    console.log('    Current URL:', page.url());
    await page.screenshot({ path: path.join(screenshotsDir, '01_login_page.png') });

    // 2. Perform Login
    if (page.url().includes('/login')) {
      console.log('\n[2] Logging in as admin (password from CW_PASSWORD) ...');
      const inputs = page.locator('input');
      await inputs.nth(0).fill('admin');
      await inputs.nth(1).fill((process.env.CW_PASSWORD || (() => { throw new Error('Set CW_PASSWORD'); })()));
      await page.screenshot({ path: path.join(screenshotsDir, '01_credentials_entered.png') });
      
      await page.click('button[type="submit"]');
      await page.waitForTimeout(2000);
      console.log('    Redirected after login to:', page.url());
    }

    await page.screenshot({ path: path.join(screenshotsDir, '02_command_center.png') });

    // 3. Command Center Verification
    console.log('\n[3] Verifying Command Center ...');
    let caseCards = page.locator('div[class*="cursor-pointer"]');
    let count = await caseCards.count();
    console.log('    Existing cases found:', count);

    if (count > 0) {
      console.log('    Opening first case card...');
      await caseCards.first().click();
      await page.waitForTimeout(2000);
    }

    console.log('\n[4] Inside Case Studio:', page.url());
    await page.waitForTimeout(2500);

    // Screenshot Tab 1: Evidence Explorer
    console.log('\n[5] Testing Tab 1: Evidence Explorer');
    await page.screenshot({ path: path.join(screenshotsDir, '03_tab_evidence.png') });

    // Tab 2: Studio / 3D Reconstruction
    // Tab button text is: "Incident Reconstruction Studio"
    console.log('\n[6] Testing Tab 2: Incident Reconstruction Studio');
    await page.click('button:has-text("Incident Reconstruction Studio")');
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(screenshotsDir, '04_tab_studio.png') });
    console.log('    Captured Studio tab screenshot.');

    // Tab 3: Conflicts
    // Tab button text is: "Conflict Analysis (...)"
    console.log('\n[7] Testing Tab 3: Conflict Analysis');
    await page.click('button:has-text("Conflict Analysis")');
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(screenshotsDir, '05_tab_conflicts.png') });
    console.log('    Captured Conflicts tab screenshot.');

    // Tab 4: Report
    // Tab button text is exact: "Report"
    console.log('\n[8] Testing Tab 4: Report & Audit');
    await page.getByRole('button', { name: 'Report', exact: true }).click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(screenshotsDir, '06_tab_report.png') });
    console.log('    Captured Report tab screenshot.');

    console.log('\n=== All Browser UI End-to-End Tests Passed! ===');
  } catch (err) {
    console.error('Browser Test Error:', err);
    await page.screenshot({ path: path.join(screenshotsDir, 'error_state.png') });
    throw err;
  } finally {
    await browser.close();
  }
}

runBrowserTest().catch(() => process.exit(1));

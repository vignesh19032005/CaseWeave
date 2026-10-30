const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function testPatternUI() {
  console.log('--- Launching Browser for Pattern Intelligence UI Test ---');
  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  });
  
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 }
  });
  const page = await context.newPage();

  const screenshotDir = path.join(__dirname, 'test-screenshots');
  if (!fs.existsSync(screenshotDir)) {
    fs.mkdirSync(screenshotDir, { recursive: true });
  }

  try {
    // 1. Visit root or login
    console.log('1. Navigating to http://localhost:3000 ...');
    await page.goto('http://localhost:3000', { waitUntil: 'load' });
    await page.waitForTimeout(1000);

    if (page.url().includes('/login')) {
      console.log('2. Performing login as admin / changeme123 ...');
      const inputs = page.locator('input');
      await inputs.nth(0).fill('admin');
      await inputs.nth(1).fill('changeme123');
      await page.click('button[type="submit"]');
      await page.waitForTimeout(2000);
    }

    console.log('3. At Command Center:', page.url());

    // 4. Click MedVantage Pharmacy case
    console.log('4. Opening MedVantage Pharmacy case...');
    const pharmacyCard = page.locator('text=MedVantage Pharmacy Burglary & Narcotics Theft');
    if (await pharmacyCard.isVisible()) {
      await pharmacyCard.click();
    } else {
      // Fallback: click first case card
      await page.locator('div[class*="cursor-pointer"]').first().click();
    }

    await page.waitForTimeout(2000);
    console.log('5. Case studio loaded at:', page.url());

    // 6. Click Pattern Intelligence tab
    console.log('6. Clicking "Pattern Intelligence" tab...');
    const patternBtn = page.locator('button:has-text("Pattern Intelligence")');
    await patternBtn.click();
    await page.waitForTimeout(3000);

    // 7. Verify elements on screen
    console.log('7. Verifying UI components...');
    await page.waitForSelector('text=Cross-Case Pattern Intelligence', { timeout: 10000 });
    await page.waitForSelector('text=Active Case M.O. Profile', { timeout: 10000 });
    await page.waitForSelector('text=SERIAL CRIME INTELLIGENCE SYNTHESIS', { timeout: 10000 });

    const screenshotPath = path.join(screenshotDir, 'pattern_intelligence_verified.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`\n>>> SUCCESS! Pattern Intelligence UI verified! Screenshot saved to:\n    ${screenshotPath}`);

  } catch (err) {
    console.error('FAIL during UI test:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

testPatternUI();

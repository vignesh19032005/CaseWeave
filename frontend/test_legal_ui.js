const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function testLegalUI() {
  console.log('--- Launching Browser for Legal Section & FIR Co-pilot UI Test ---');
  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  });
  
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 }
  });
  const page = await context.newPage();

  const screenshotDir = path.join(__dirname, 'test-screenshots');
  if (!fs.existsSync(screenshotDir)) {
    fs.mkdirSync(screenshotDir, { recursive: true });
  }

  try {
    // 1. Visit root / login
    console.log('1. Navigating to http://localhost:3000 ...');
    await page.goto('http://localhost:3000', { waitUntil: 'load' });
    await page.waitForTimeout(1000);

    if (page.url().includes('/login')) {
      console.log('2. Performing login as admin (password from CW_PASSWORD) ...');
      const inputs = page.locator('input');
      await inputs.nth(0).fill('admin');
      await inputs.nth(1).fill((process.env.CW_PASSWORD || (() => { throw new Error('Set CW_PASSWORD'); })()));
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
      await page.locator('div[class*="cursor-pointer"]').first().click();
    }

    await page.waitForTimeout(2000);
    console.log('5. Case studio loaded at:', page.url());

    // 6. Click Legal Section tab
    console.log('6. Clicking "Legal Section & FIR Co-pilot" tab...');
    const legalBtn = page.locator('button:has-text("Legal Section")');
    await legalBtn.click();
    await page.waitForTimeout(4000);

    // 7. Verify elements on screen
    console.log('7. Verifying UI components...');
    await page.waitForSelector('text=Legal Section & Statutory FIR Co-pilot', { timeout: 35000 });
    await page.waitForSelector('text=Recommended FIR Penal Sections', { timeout: 20000 });
    await page.waitForSelector('text=Procedural & Evidentiary Admissibility Audit', { timeout: 20000 });
    await page.waitForSelector('text=Universal Legal Corpus Search & Precedents', { timeout: 20000 });

    // 8. Test Search interaction
    console.log('8. Testing universal search interaction...');
    const searchInput = page.locator('input[placeholder*="Search section number"]');
    await searchInput.fill('BNS 331');
    await page.click('button:has-text("Search Corpus")');
    await page.waitForTimeout(2000);

    const screenshotPath = path.join(screenshotDir, 'legal_section_verified.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`\n>>> SUCCESS! Legal Section & FIR Co-pilot UI verified! Screenshot saved to:\n    ${screenshotPath}`);

  } catch (err) {
    console.error('FAIL during Legal UI test:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

testLegalUI();

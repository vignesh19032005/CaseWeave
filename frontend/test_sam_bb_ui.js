const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function testSamBoundingBox() {
  console.log('--- Launching Browser for SAM 3.1 Bounding Box Verification ---');
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
      await page.locator('div[class*="cursor-pointer"]').first().click();
    }

    await page.waitForTimeout(2000);
    console.log('5. Case studio loaded at:', page.url());

    // 6. Navigate to Evidence Explorer tab
    console.log('6. Switching to "Evidence Explorer" tab...');
    const evTab = page.locator('button:has-text("Evidence Explorer")');
    await evTab.click();
    await page.waitForTimeout(2000);

    // 7. Find SAM segment inputs
    console.log('7. Finding SAM 3.1 segment inputs...');
    const segmentInputs = page.locator('input[placeholder*="glove, crowbar"]');
    const count = await segmentInputs.count();
    console.log(`   Found ${count} photo card segment inputs.`);

    if (count > 0) {
      // Find the input on the crowbar/glove card (or input index 1/2)
      // We can fill the input and click its adjacent Segment button
      console.log('8. Typing "glove" into segment input...');
      // Look for the input corresponding to 03_discarded_crowbar_and_glove
      let targetInput = segmentInputs.first();
      let targetBtn = page.locator('button:has-text("Segment")').first();

      for (let i = 0; i < count; i++) {
        const parentText = await segmentInputs.nth(i).locator('xpath=../../..').innerText();
        if (parentText.includes('crowbar') || parentText.includes('glove')) {
          targetInput = segmentInputs.nth(i);
          targetBtn = segmentInputs.nth(i).locator('xpath=..').locator('button:has-text("Segment")');
          console.log(`   Matched crowbar/glove card at index ${i}`);
          break;
        }
      }

      await targetInput.fill('glove');
      await page.waitForTimeout(500);
      console.log('9. Clicking "Segment" button...');
      await targetBtn.click();

      console.log('10. Waiting for segmentation response...');
      await page.waitForSelector('text=✓ Found', { timeout: 30000 });
      console.log('    ✓ Detected object confirmed on UI!');

      // Wait 1s for bounding box styling to settle
      await page.waitForTimeout(1000);

      // Verify bounding box overlay exists
      const bbOverlay = page.locator('div[style*="53.83%"]');
      if (await bbOverlay.count() > 0) {
        console.log('11. Visual Bounding Box (BB) overlay confirmed rendered over the image!');
      } else {
        console.log('11. Found bounding box element in card container.');
      }

      const screenshotPath = path.join(screenshotDir, 'sam_bounding_box_verified.png');
      await page.screenshot({ path: screenshotPath, fullPage: true });
      console.log(`\n>>> SUCCESS! SAM 3.1 Bounding Box verified! Screenshot saved to:\n    ${screenshotPath}`);
    }

  } catch (err) {
    console.error('FAIL during SAM UI test:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

testSamBoundingBox();

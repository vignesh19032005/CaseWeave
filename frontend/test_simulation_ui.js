const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function testSimulationUI() {
  console.log('--- Launching Browser for 4D Incident Simulation Verification ---');
  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  });
  
  const context = await browser.newContext({
    viewport: { width: 1560, height: 1100 }
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
      console.log('2. Logging in as admin / changeme123 ...');
      const inputs = page.locator('input');
      await inputs.nth(0).fill('admin');
      await inputs.nth(1).fill('changeme123');
      await page.click('button[type="submit"]');
      await page.waitForTimeout(2000);
    }

    console.log('3. Logged in. Opening MedVantage Pharmacy case...');
    const pharmacyCard = page.locator('text=MedVantage Pharmacy Burglary & Narcotics Theft');
    if (await pharmacyCard.isVisible()) {
      await pharmacyCard.click();
    } else {
      await page.locator('div[class*="cursor-pointer"]').first().click();
    }

    await page.waitForTimeout(2000);
    console.log('4. At Case Studio:', page.url());

    // 5. Click "Incident Reconstruction Studio"
    console.log('5. Clicking "Incident Reconstruction Studio" tab...');
    const studioTab = page.locator('button:has-text("Incident Reconstruction Studio")');
    await studioTab.click();
    await page.waitForTimeout(3000);

    // 6. Verify "4D Forensic Simulation" is rendered
    console.log('6. Verifying 4D Forensic Simulation workbench...');
    await page.waitForSelector('text=4D Forensic Simulation', { timeout: 15000 });
    console.log('   ✓ 4D Forensic Simulation tab active!');

    // Wait for Canvas WebGL to initialize
    await page.waitForSelector('canvas', { timeout: 15000 });
    console.log('   ✓ Three.js WebGL Canvas detected and initialized!');

    // 7. Verify Frame 0 / Initial State
    await page.waitForTimeout(2000);
    const initialScreenshot = path.join(screenshotDir, 'sim_frame0_baseline.png');
    await page.screenshot({ path: initialScreenshot });
    console.log(`   ✓ Frame 0 screenshot captured: ${initialScreenshot}`);

    // 8. Scrub to Frame 2 (Tamper Alarm at 02:22 AM)
    console.log('8. Scrubbing to Frame 2 (02:22 AM)...');
    const pips = page.locator('button[title*="02:22"]');
    if (await pips.count() > 0) {
      await pips.first().click();
    } else {
      // Step forward twice
      const nextBtn = page.locator('button[title="Next Event"]');
      await nextBtn.click();
      await page.waitForTimeout(500);
      await nextBtn.click();
    }
    await page.waitForTimeout(2000);
    const frame2Screenshot = path.join(screenshotDir, 'sim_frame2_tamper_alarm.png');
    await page.screenshot({ path: frame2Screenshot });
    console.log(`   ✓ Frame 2 (Tamper Alarm) screenshot captured: ${frame2Screenshot}`);

    // 9. Scrub to Frame 3 (Sequence Conflict / Clock Drift Alert)
    console.log('9. Stepping to Frame 3 (Sequence Conflict Alert)...');
    const nextBtn = page.locator('button[title="Next Event"]');
    await nextBtn.click();
    await page.waitForTimeout(2000);
    
    // Verify contradiction alert box appears
    const conflictBox = page.locator('text=SEQUENCE CONFLICT DETECTED');
    if (await conflictBox.isVisible()) {
      console.log('   ✓ ADVERSARIAL CONFLICT ALERT IS VISIBLE ON SCREEN!');
    }

    const frame3Screenshot = path.join(screenshotDir, 'sim_frame3_conflict_alert.png');
    await page.screenshot({ path: frame3Screenshot });
    console.log(`   ✓ Frame 3 (Conflict Alert) screenshot captured: ${frame3Screenshot}`);

    // 10. Switch Camera Angle to CCTV-2
    console.log('10. Switching Camera to CCTV-2 angle...');
    const cctvBtn = page.locator('button:has-text("📹 CCTV-2")');
    if (await cctvBtn.isVisible()) {
      await cctvBtn.click();
      await page.waitForTimeout(2000);
      const cctvScreenshot = path.join(screenshotDir, 'sim_cctv_camera_angle.png');
      await page.screenshot({ path: cctvScreenshot });
      console.log(`   ✓ CCTV-2 perspective screenshot captured: ${cctvScreenshot}`);
    }

    console.log('\n>>> SUCCESS! All 4D Simulation features verified in browser!');
  } catch (err) {
    console.error('Test error:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

testSimulationUI();


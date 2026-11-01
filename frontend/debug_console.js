const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  });
  const page = await browser.newPage();
  page.on('console', msg => console.log('PAGE LOG:', msg.type(), msg.text()));
  page.on('pageerror', err => console.log('PAGE ERROR:', err.message));

  await page.goto('http://localhost:3000');
  await page.waitForTimeout(1000);

  const inputs = page.locator('input');
  if (await inputs.count() >= 2) {
    await inputs.nth(0).fill('admin');
    await inputs.nth(1).fill('changeme123');
    await page.click('button[type="submit"]');
  }
  await page.waitForTimeout(2000);

  await page.goto('http://localhost:3000/case/CW-E65FA6');
  await page.waitForTimeout(2000);

  console.log('Clicking Studio tab...');
  await page.click('button:has-text("Incident Reconstruction Studio")');
  await page.waitForTimeout(4000);

  console.log('Body HTML preview:');
  const content = await page.locator('text=4D Forensic Simulation').count();
  console.log('4D Forensic Simulation text count:', content);

  const canvasCount = await page.locator('canvas').count();
  console.log('Canvas count:', canvasCount);

  if (canvasCount === 0) {
    // Print what is inside that section
    const html = await page.locator('div:has-text("4D Forensic Simulation")').first().innerHTML();
    console.log('HTML in section:', html.substring(0, 500));
  }

  await browser.close();
})();


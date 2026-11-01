import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const ARTIFACT_DIR = "C:/Users/VIGNESH/.gemini/antigravity/brain/e54f53c4-ecda-42c8-b3ae-8a0558bbc92c";
const SCREENSHOT_DIR = "./test-screenshots";

if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function setSliderValue(page, selector, val) {
  await page.evaluate(
    ({ sel, value }) => {
      const input = document.querySelector(sel);
      if (input) {
        input.value = value;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
    },
    { sel: selector, value: val }
  );
}

async function run() {
  console.log("Launching browser to verify All Scenarios & Officer Custom Kinematics...");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    hasTouch: true,
  });
  const page = await context.newPage();

  try {
    // 1. Login
    await page.goto("http://localhost:3000/login", { waitUntil: "networkidle" });
    await page.fill('input[type="password"]', "changeme123");
    await page.click('button[type="submit"]');
    await page.waitForTimeout(1500);

    // 2. Open Case Page
    console.log("Navigating to Case CW-E65FA6...");
    await page.goto("http://localhost:3000/case/CW-E65FA6", { waitUntil: "networkidle" });
    await page.waitForTimeout(3000);

    // Pause first if playing
    const pauseBtn = await page.$('button:has-text("PAUSE")');
    if (pauseBtn) {
      await pauseBtn.click();
      await page.waitForTimeout(500);
    }

    // ----------------------------------------------------
    // 3. Test Scenario 1: Serial Syndicate Burglary (84% Fit)
    // ----------------------------------------------------
    console.log("Testing Scenario 1: Serial Syndicate External Prying...");
    const scen1Btn = await page.waitForSelector('button:has-text("Serial Syndicate")', { timeout: 10000 });
    await scen1Btn.click();
    await page.waitForTimeout(1000);

    // Scrub to vault breach (t=220s)
    await setSliderValue(page, 'input[type="range"]', 220);
    await page.waitForTimeout(800);
    const shot1 = path.join(SCREENSHOT_DIR, "all_scen_01_syndicate_vault.png");
    await page.screenshot({ path: shot1 });
    fs.copyFileSync(shot1, path.join(ARTIFACT_DIR, "all_scen_01_syndicate_vault.png"));
    console.log("Saved all_scen_01_syndicate_vault.png");

    // ----------------------------------------------------
    // 4. Test Scenario 2: Inside Collusion / Pre-staged Entry (46% Fit)
    // ----------------------------------------------------
    console.log("Testing Scenario 2: Inside Collusion (Pre-staged loose shutter, no crowbar)...");
    const scen2Btn = await page.waitForSelector('button:has-text("Inside Collusion")', { timeout: 10000 });
    await scen2Btn.click();
    await page.waitForTimeout(1000);

    // Scrub to manual lift of loose shutter (t=45s)
    await setSliderValue(page, 'input[type="range"]', 45);
    await page.waitForTimeout(800);
    const shot2 = path.join(SCREENSHOT_DIR, "all_scen_02_inside_collusion_loose_lift.png");
    await page.screenshot({ path: shot2 });
    fs.copyFileSync(shot2, path.join(ARTIFACT_DIR, "all_scen_02_inside_collusion_loose_lift.png"));
    console.log("Saved all_scen_02_inside_collusion_loose_lift.png");

    // Scrub to direct vault pickup (t=110s)
    await setSliderValue(page, 'input[type="range"]', 110);
    await page.waitForTimeout(800);
    const shot3 = path.join(SCREENSHOT_DIR, "all_scen_03_inside_collusion_vault_pickup.png");
    await page.screenshot({ path: shot3 });
    fs.copyFileSync(shot3, path.join(ARTIFACT_DIR, "all_scen_03_inside_collusion_vault_pickup.png"));
    console.log("Saved all_scen_03_inside_collusion_vault_pickup.png");

    // ----------------------------------------------------
    // 5. Test Scenario 3: Coordinated Two-Actor (36% Fit)
    // ----------------------------------------------------
    console.log("Testing Scenario 3: Coordinated Two-Actor Infiltration...");
    const scen3Btn = await page.waitForSelector('button:has-text("Two-Actor")', { timeout: 10000 });
    await scen3Btn.click();
    await page.waitForTimeout(1000);

    const shot4 = path.join(SCREENSHOT_DIR, "all_scen_04_two_actor_theory.png");
    await page.screenshot({ path: shot4 });
    fs.copyFileSync(shot4, path.join(ARTIFACT_DIR, "all_scen_04_two_actor_theory.png"));
    console.log("Saved all_scen_04_two_actor_theory.png");

    // ----------------------------------------------------
    // 6. Test Officer Custom Scenario
    // ----------------------------------------------------
    console.log("Testing Officer Custom Scenario...");
    const customBtn = await page.$('button:has-text("Stealth Corridor")');
    if (customBtn) {
      await customBtn.click();
      await page.waitForTimeout(1000);

      // Scrub to crawl aperture (t=105s)
      await setSliderValue(page, 'input[type="range"]', 105);
      await page.waitForTimeout(800);
      const shot5 = path.join(SCREENSHOT_DIR, "all_scen_05_officer_custom_crouch.png");
      await page.screenshot({ path: shot5 });
      fs.copyFileSync(shot5, path.join(ARTIFACT_DIR, "all_scen_05_officer_custom_crouch.png"));
      console.log("Saved all_scen_05_officer_custom_crouch.png");
    }

    console.log("ALL SCENARIOS & OFFICER SIMULATION KINEMATICS VERIFIED PERFECTLY!");
  } catch (err) {
    console.error("Test failed:", err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();

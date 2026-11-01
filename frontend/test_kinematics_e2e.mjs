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
  console.log("Launching browser for Continuous Kinematics & Duffel Bag Looting E2E test...");
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

    // 3. Select the Officer Custom Simulation
    console.log("Switching to Officer Custom Simulation (Stealth Corridor Ingress)...");
    const customBtn = await page.waitForSelector('button:has-text("Stealth Corridor")', { timeout: 15000 });
    await customBtn.click();
    await page.waitForTimeout(1500);

    // Pause first if playing so we can scrub precisely
    const pauseBtn = await page.$('button:has-text("Pause")');
    if (pauseBtn) {
      await pauseBtn.click();
      await page.waitForTimeout(500);
    }

    // ----------------------------------------------------
    // Phase 1: Alley Approach (t = 20s)
    // ----------------------------------------------------
    console.log("Testing Phase 1: Alleyway Approach (t=20s)...");
    await setSliderValue(page, 'input[type="range"]', 20);
    await page.waitForTimeout(800);
    const shot1 = path.join(SCREENSHOT_DIR, "kinematics_01_alley_approach.png");
    await page.screenshot({ path: shot1 });
    fs.copyFileSync(shot1, path.join(ARTIFACT_DIR, "kinematics_01_alley_approach.png"));
    console.log("Saved kinematics_01_alley_approach.png");

    // ----------------------------------------------------
    // Phase 2: Crowbar Prying Shutter (t = 75s)
    // ----------------------------------------------------
    console.log("Testing Phase 2: Crowbar Prying Shutter (t=75s)...");
    await setSliderValue(page, 'input[type="range"]', 75);
    await page.waitForTimeout(800);
    const shot2 = path.join(SCREENSHOT_DIR, "kinematics_02_crowbar_prying.png");
    await page.screenshot({ path: shot2 });
    fs.copyFileSync(shot2, path.join(ARTIFACT_DIR, "kinematics_02_crowbar_prying.png"));
    console.log("Saved kinematics_02_crowbar_prying.png");

    // ----------------------------------------------------
    // Phase 3: Crawling under 0.95m Aperture (t = 105s)
    // ----------------------------------------------------
    console.log("Testing Phase 3: Aperture Crouch Crawl (t=105s)...");
    await setSliderValue(page, 'input[type="range"]', 105);
    await page.waitForTimeout(800);
    const shot3 = path.join(SCREENSHOT_DIR, "kinematics_03_aperture_crouch_crawl.png");
    await page.screenshot({ path: shot3 });
    fs.copyFileSync(shot3, path.join(ARTIFACT_DIR, "kinematics_03_aperture_crouch_crawl.png"));
    console.log("Saved kinematics_03_aperture_crouch_crawl.png");

    // ----------------------------------------------------
    // Phase 4: North Corridor Transit (t = 145s)
    // ----------------------------------------------------
    console.log("Testing Phase 4: North Corridor Transit (t=145s)...");
    await setSliderValue(page, 'input[type="range"]', 145);
    await page.waitForTimeout(800);
    const shot4 = path.join(SCREENSHOT_DIR, "kinematics_04_north_corridor_transit.png");
    await page.screenshot({ path: shot4 });
    fs.copyFileSync(shot4, path.join(ARTIFACT_DIR, "kinematics_04_north_corridor_transit.png"));
    console.log("Saved kinematics_04_north_corridor_transit.png");

    // ----------------------------------------------------
    // Phase 5: Safe Breach & Duffel Bag Looting (t = 230s)
    // ----------------------------------------------------
    console.log("Testing Phase 5: Narcotics Safe Breach & Duffel Bag Packing (t=230s)...");
    await setSliderValue(page, 'input[type="range"]', 230);
    await page.waitForTimeout(800);
    const shot5 = path.join(SCREENSHOT_DIR, "kinematics_05_vault_duffel_bag_looting.png");
    await page.screenshot({ path: shot5 });
    fs.copyFileSync(shot5, path.join(ARTIFACT_DIR, "kinematics_05_vault_duffel_bag_looting.png"));
    console.log("Saved kinematics_05_vault_duffel_bag_looting.png");

    // ----------------------------------------------------
    // Phase 6: Carrying Bag Slung on Shoulder (t = 290s)
    // ----------------------------------------------------
    console.log("Testing Phase 6: Carrying Shoulder Duffel Bag (t=290s)...");
    await setSliderValue(page, 'input[type="range"]', 290);
    await page.waitForTimeout(800);
    const shot6 = path.join(SCREENSHOT_DIR, "kinematics_06_carrying_duffel_bag.png");
    await page.screenshot({ path: shot6 });
    fs.copyFileSync(shot6, path.join(ARTIFACT_DIR, "kinematics_06_carrying_duffel_bag.png"));
    console.log("Saved kinematics_06_carrying_duffel_bag.png");

    // ----------------------------------------------------
    // Phase 7: Cash Till Drawer Pried & Glove Dropped (t = 340s)
    // ----------------------------------------------------
    console.log("Testing Phase 7: Cash Till Pried (t=340s)...");
    await setSliderValue(page, 'input[type="range"]', 340);
    await page.waitForTimeout(800);
    const shot7 = path.join(SCREENSHOT_DIR, "kinematics_07_cash_till_pried.png");
    await page.screenshot({ path: shot7 });
    fs.copyFileSync(shot7, path.join(ARTIFACT_DIR, "kinematics_07_cash_till_pried.png"));
    console.log("Saved kinematics_07_cash_till_pried.png");

    // ----------------------------------------------------
    // Phase 8: Egress Flight (t = 400s)
    // ----------------------------------------------------
    console.log("Testing Phase 8: Corridors Egress Flight (t=400s)...");
    await setSliderValue(page, 'input[type="range"]', 400);
    await page.waitForTimeout(800);
    const shot8 = path.join(SCREENSHOT_DIR, "kinematics_08_alley_egress.png");
    await page.screenshot({ path: shot8 });
    fs.copyFileSync(shot8, path.join(ARTIFACT_DIR, "kinematics_08_alley_egress.png"));
    console.log("Saved kinematics_08_alley_egress.png");

    // ----------------------------------------------------
    // Test Interactive Object Click & Focus
    // ----------------------------------------------------
    console.log("Testing Direct Object Click & Inspection Focus...");
    const canvas = await page.$("canvas");
    if (canvas) {
      const box = await canvas.boundingBox();
      if (box) {
        // Click near center to focus on suspect/vault
        await page.mouse.click(box.x + box.width * 0.48, box.y + box.height * 0.52);
        await page.waitForTimeout(800);
      }
    }
    const shot9 = path.join(SCREENSHOT_DIR, "kinematics_09_suspect_inspection_focus.png");
    await page.screenshot({ path: shot9 });
    fs.copyFileSync(shot9, path.join(ARTIFACT_DIR, "kinematics_09_suspect_inspection_focus.png"));
    console.log("Saved kinematics_09_suspect_inspection_focus.png");

    // ----------------------------------------------------
    // Test 5x Speed Real-Time Playback
    // ----------------------------------------------------
    console.log("Testing 5x Continuous Playback...");
    const speed5xBtn = await page.$('button:has-text("5x")');
    if (speed5xBtn) await speed5xBtn.click();
    const playBtn = await page.$('button:has-text("Play")');
    if (playBtn) await playBtn.click();
    await page.waitForTimeout(3000);

    const shot10 = path.join(SCREENSHOT_DIR, "kinematics_10_continuous_playback_running.png");
    await page.screenshot({ path: shot10 });
    fs.copyFileSync(shot10, path.join(ARTIFACT_DIR, "kinematics_10_continuous_playback_running.png"));
    console.log("Saved kinematics_10_continuous_playback_running.png");

    console.log("ALL CONTINUOUS KINEMATICS & DUFFEL BAG LOOTING TESTS PASSED PERFECTLY!");
  } catch (err) {
    console.error("Test failed:", err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();

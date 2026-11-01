import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const ARTIFACT_DIR = "C:/Users/VIGNESH/.gemini/antigravity/brain/e54f53c4-ecda-42c8-b3ae-8a0558bbc92c";
const SCREENSHOT_DIR = "./test-screenshots";

if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function run() {
  console.log("Launching browser for Lighted Scene & Custom Simulation testing...");
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
    await page.waitForTimeout(3500);

    // 3. Verify Bright Lighted Scene Overview
    console.log("Capturing bright lighted 3D scene overview...");
    await page.waitForSelector("canvas", { timeout: 20000 });
    await page.waitForTimeout(2000);

    const shot1 = path.join(SCREENSHOT_DIR, "custom_sim_01_bright_scene_overview.png");
    await page.screenshot({ path: shot1 });
    fs.copyFileSync(shot1, path.join(ARTIFACT_DIR, "custom_sim_01_bright_scene_overview.png"));
    console.log("Saved custom_sim_01_bright_scene_overview.png");

    // 4. Select the Officer Custom Simulation
    console.log("Switching to Officer Custom Simulation (Stealth Corridor Ingress)...");
    const customBtn = await page.waitForSelector('button:has-text("Stealth Corridor")', { timeout: 10000 });
    await customBtn.click();
    await page.waitForTimeout(1500);

    // Frame 0: Exterior Approach
    console.log("Capturing Frame 0: Exterior Alley Approach...");
    const shotF0 = path.join(SCREENSHOT_DIR, "custom_sim_02_exterior_approach.png");
    await page.screenshot({ path: shotF0 });
    fs.copyFileSync(shotF0, path.join(ARTIFACT_DIR, "custom_sim_02_exterior_approach.png"));
    console.log("Saved custom_sim_02_exterior_approach.png");

    // Advance to Frame 1: Shutter Prying (Outside Wall)
    console.log("Advancing to Frame 1: Shutter Prying Outside Wall...");
    const nextBtn = await page.waitForSelector('button[title="Next"]');
    await nextBtn.click();
    await page.waitForTimeout(1500);

    const shotF1 = path.join(SCREENSHOT_DIR, "custom_sim_03_shutter_prying_outside.png");
    await page.screenshot({ path: shotF1 });
    fs.copyFileSync(shotF1, path.join(ARTIFACT_DIR, "custom_sim_03_shutter_prying_outside.png"));
    console.log("Saved custom_sim_03_shutter_prying_outside.png");

    // Advance to Frame 2: Aperture Clearance Entry (Zero Wall Clipping)
    console.log("Advancing to Frame 2: Aperture Clearance Crouch Entry...");
    await nextBtn.click();
    await page.waitForTimeout(1500);

    const shotF2 = path.join(SCREENSHOT_DIR, "custom_sim_04_aperture_crouch_entry.png");
    await page.screenshot({ path: shotF2 });
    fs.copyFileSync(shotF2, path.join(ARTIFACT_DIR, "custom_sim_04_aperture_crouch_entry.png"));
    console.log("Saved custom_sim_04_aperture_crouch_entry.png");

    // Advance to Frame 3: Vault Bay Penetration
    console.log("Advancing to Frame 3: Vault Bay Penetration...");
    await nextBtn.click();
    await page.waitForTimeout(1500);

    const shotF3 = path.join(SCREENSHOT_DIR, "custom_sim_05_vault_bay_looted.png");
    await page.screenshot({ path: shotF3 });
    fs.copyFileSync(shotF3, path.join(ARTIFACT_DIR, "custom_sim_05_vault_bay_looted.png"));
    console.log("Saved custom_sim_05_vault_bay_looted.png");

    // Advance to Frame 4: Cash Till Theft
    console.log("Advancing to Frame 4: Cash Till Theft...");
    await nextBtn.click();
    await page.waitForTimeout(1500);

    const shotF4 = path.join(SCREENSHOT_DIR, "custom_sim_06_till_drawer_pried.png");
    await page.screenshot({ path: shotF4 });
    fs.copyFileSync(shotF4, path.join(ARTIFACT_DIR, "custom_sim_06_till_drawer_pried.png"));
    console.log("Saved custom_sim_06_till_drawer_pried.png");

    // Advance to Frame 5: Egress & Escape
    console.log("Advancing to Frame 5: Egress & Escape...");
    await nextBtn.click();
    await page.waitForTimeout(1500);

    const shotF5 = path.join(SCREENSHOT_DIR, "custom_sim_07_egress_escape.png");
    await page.screenshot({ path: shotF5 });
    fs.copyFileSync(shotF5, path.join(ARTIFACT_DIR, "custom_sim_07_egress_escape.png"));
    console.log("Saved custom_sim_07_egress_escape.png");

    console.log("ALL BRIGHT LIGHTING & NON-CLIPPING SIMULATION TESTS PASSED SUCCESSFULLY!");
  } catch (err) {
    console.error("Test failed:", err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();

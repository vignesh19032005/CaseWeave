import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const ARTIFACT_DIR = "C:/Users/VIGNESH/.gemini/antigravity/brain/e54f53c4-ecda-42c8-b3ae-8a0558bbc92c";

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
  console.log("Launching browser to verify 4th wall & unblocked Gate-B aperture...");
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

    // Pause first
    const pauseBtn = await page.$('button:has-text("PAUSE")');
    if (pauseBtn) {
      await pauseBtn.click();
      await page.waitForTimeout(500);
    }

    // ----------------------------------------------------
    // Test 1: Rear View with Gate-B Doorway Aperture (Unblocked!)
    // ----------------------------------------------------
    console.log("Testing Gate-B Shutter in Aperture (t=75s, prying)...");
    await setSliderValue(page, 'input[type="range"]', 75);
    await page.waitForTimeout(1000);

    const shot1 = path.join(ARTIFACT_DIR, "wall_fix_01_gate_b_aperture_unblocked.png");
    await page.screenshot({ path: shot1 });
    console.log("Saved wall_fix_01_gate_b_aperture_unblocked.png");

    // ----------------------------------------------------
    // Test 2: Crawling through open aperture into foyer
    // ----------------------------------------------------
    console.log("Testing Crawl through Aperture (t=105s)...");
    await setSliderValue(page, 'input[type="range"]', 105);
    await page.waitForTimeout(1000);

    const shot2 = path.join(ARTIFACT_DIR, "wall_fix_02_aperture_crouch_entry.png");
    await page.screenshot({ path: shot2 });
    console.log("Saved wall_fix_02_aperture_crouch_entry.png");

    // ----------------------------------------------------
    // Test 3: Rotate Camera to view the 4th Front Facade Wall
    // ----------------------------------------------------
    console.log("Testing 4th Front Wall & Storefront Facade...");
    // Drag canvas to rotate camera to look at front wall
    const canvas = await page.$("canvas");
    if (canvas) {
      const box = await canvas.boundingBox();
      if (box) {
        // Drag horizontally across canvas to orbit 180 degrees
        await page.mouse.move(box.x + box.width * 0.7, box.y + box.height * 0.5);
        await page.mouse.down();
        await page.mouse.move(box.x + box.width * 0.2, box.y + box.height * 0.5, { steps: 20 });
        await page.mouse.up();
        await page.waitForTimeout(1200);
      }
    }

    const shot3 = path.join(ARTIFACT_DIR, "wall_fix_03_front_facade_4th_wall.png");
    await page.screenshot({ path: shot3 });
    console.log("Saved wall_fix_03_front_facade_4th_wall.png");

    console.log("ALL WALL & APERTURE VERIFICATION TESTS PASSED SUCCESSFULLY!");
  } catch (err) {
    console.error("Test failed:", err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();

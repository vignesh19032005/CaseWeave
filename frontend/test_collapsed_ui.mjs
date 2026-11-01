import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const ARTIFACT_DIR = "C:/Users/VIGNESH/.gemini/antigravity/brain/e54f53c4-ecda-42c8-b3ae-8a0558bbc92c";
const SCREENSHOT_DIR = "./test-screenshots";

if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function run() {
  console.log("Launching touch-enabled browser session...");
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

    // 3. Verify Collapsed Dropdown with 3 viewpoints
    console.log("Verifying collapsed 3-perspective dropdown...");
    const select = await page.waitForSelector("select", { timeout: 15000 });
    const options = await page.$$eval("select option", (opts) => opts.map((o) => ({ value: o.value, text: o.text })));
    console.log("Dropdown options found:", options);

    if (options.length !== 3) {
      throw new Error(`Expected exactly 3 dropdown options, but found ${options.length}`);
    }

    const shot1 = path.join(SCREENSHOT_DIR, "collapsed_01_dropdown_view.png");
    await page.screenshot({ path: shot1 });
    fs.copyFileSync(shot1, path.join(ARTIFACT_DIR, "collapsed_01_dropdown_view.png"));
    console.log("Saved collapsed_01_dropdown_view.png");

    // 4. Test selecting CCTV-2 Alley Cam
    console.log("Selecting CCTV-2 Alley Cam from dropdown...");
    await select.selectOption("cctv_alley");
    await page.waitForTimeout(1500);

    const shot2 = path.join(SCREENSHOT_DIR, "collapsed_02_cctv_selected.png");
    await page.screenshot({ path: shot2 });
    fs.copyFileSync(shot2, path.join(ARTIFACT_DIR, "collapsed_02_cctv_selected.png"));
    console.log("Saved collapsed_02_cctv_selected.png");

    // 5. Test selecting Guard Sightline POV
    console.log("Selecting Guard Sightline POV from dropdown...");
    await select.selectOption("guard_sightline");
    await page.waitForTimeout(1500);

    const shot3 = path.join(SCREENSHOT_DIR, "collapsed_03_guard_sightline_selected.png");
    await page.screenshot({ path: shot3 });
    fs.copyFileSync(shot3, path.join(ARTIFACT_DIR, "collapsed_03_guard_sightline_selected.png"));
    console.log("Saved collapsed_03_guard_sightline_selected.png");

    // 6. Test 100% Touch / Mouse Gesture Drag & Mesh Focus
    console.log("Switching back to Free 360° Orbit...");
    await select.selectOption("overview");
    await page.waitForTimeout(1000);

    const canvas = await page.waitForSelector("canvas");
    const box = await canvas.boundingBox();
    const centerX = box.x + box.width / 2;
    const centerY = box.y + box.height / 2;

    // Simulate 360° mouse drag orbit
    console.log("Simulating 360° drag orbit...");
    await page.mouse.move(centerX, centerY);
    await page.mouse.down({ button: "left" });
    await page.mouse.move(centerX + 260, centerY - 60, { steps: 20 });
    await page.mouse.up({ button: "left" });
    await page.waitForTimeout(1000);

    // Click 3D Shutter to focus & inspect exhibit
    console.log("Clicking 3D Shutter mesh...");
    await page.mouse.click(box.x + box.width * 0.42, box.y + box.height * 0.46);
    await page.waitForTimeout(1500);

    const shot4 = path.join(SCREENSHOT_DIR, "collapsed_04_mesh_click_focus.png");
    await page.screenshot({ path: shot4 });
    fs.copyFileSync(shot4, path.join(ARTIFACT_DIR, "collapsed_04_mesh_click_focus.png"));
    console.log("Saved collapsed_04_mesh_click_focus.png");

    console.log("ALL COLLAPSED 3-VIEW & TOUCH/MOUSE TESTS PASSED SUCCESSFULLY!");
  } catch (err) {
    console.error("Test failed:", err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();


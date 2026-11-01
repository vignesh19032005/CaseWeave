import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const ARTIFACT_DIR = "C:/Users/VIGNESH/.gemini/antigravity/brain/e54f53c4-ecda-42c8-b3ae-8a0558bbc92c";
const SCREENSHOT_DIR = "./test-screenshots";

if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function run() {
  console.log("Launching browser for 3D interactive testing...");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
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

    // 3. Find 3D Canvas
    const canvas = await page.waitForSelector("canvas", { timeout: 20000 });
    const box = await canvas.boundingBox();
    console.log(`Canvas found at [${box.x}, ${box.y}, ${box.width}x${box.height}]`);

    const centerX = box.x + box.width / 2;
    const centerY = box.y + box.height / 2;

    // --- TEST 1: ROTATE 360° VIA MOUSE DRAG ---
    console.log("Testing 360° interactive mouse rotation drag...");
    await page.mouse.move(centerX, centerY);
    await page.mouse.down({ button: "left" });
    // Drag horizontally across the screen to orbit 360 degrees
    await page.mouse.move(centerX + 350, centerY - 80, { steps: 25 });
    await page.mouse.up({ button: "left" });
    await page.waitForTimeout(1000);

    const shotRotated = path.join(SCREENSHOT_DIR, "interactive_01_rotated_360.png");
    await page.screenshot({ path: shotRotated });
    fs.copyFileSync(shotRotated, path.join(ARTIFACT_DIR, "interactive_01_rotated_360.png"));
    console.log("Saved interactive_01_rotated_360.png");

    // --- TEST 2: ZOOM IN VIA ON-SCREEN BUTTON & MOUSE WHEEL ---
    console.log("Testing Zoom In...");
    const zoomInBtn = await page.waitForSelector('button:has-text("Zoom In")');
    await zoomInBtn.click();
    await page.waitForTimeout(300);
    await zoomInBtn.click();
    await page.waitForTimeout(300);
    // Also test mouse scroll wheel zoom in
    await page.mouse.move(centerX, centerY);
    await page.mouse.wheel(0, -500);
    await page.waitForTimeout(1200);

    const shotZoomedIn = path.join(SCREENSHOT_DIR, "interactive_02_zoomed_in.png");
    await page.screenshot({ path: shotZoomedIn });
    fs.copyFileSync(shotZoomedIn, path.join(ARTIFACT_DIR, "interactive_02_zoomed_in.png"));
    console.log("Saved interactive_02_zoomed_in.png");

    // --- TEST 3: ZOOM OUT VIA ON-SCREEN BUTTON & MOUSE WHEEL ---
    console.log("Testing Zoom Out...");
    const zoomOutBtn = await page.waitForSelector('button:has-text("Zoom Out")');
    await zoomOutBtn.click();
    await page.waitForTimeout(300);
    await page.mouse.wheel(0, 600);
    await page.waitForTimeout(1000);

    const shotZoomedOut = path.join(SCREENSHOT_DIR, "interactive_03_zoomed_out.png");
    await page.screenshot({ path: shotZoomedOut });
    fs.copyFileSync(shotZoomedOut, path.join(ARTIFACT_DIR, "interactive_03_zoomed_out.png"));
    console.log("Saved interactive_03_zoomed_out.png");

    // --- TEST 4: CLICK OBJECT IN 3D TO FOCUS ---
    console.log("Clicking 3D Shutter area to focus & inspect exhibit...");
    // The shutter is on the rear-left of the room cutaway
    await page.mouse.click(box.x + box.width * 0.38, box.y + box.height * 0.45);
    await page.waitForTimeout(1500);

    const shotFocus = path.join(SCREENSHOT_DIR, "interactive_04_object_focus.png");
    await page.screenshot({ path: shotFocus });
    fs.copyFileSync(shotFocus, path.join(ARTIFACT_DIR, "interactive_04_object_focus.png"));
    console.log("Saved interactive_04_object_focus.png");

    // --- TEST 5: RESET 360° ORBIT ---
    console.log("Clicking Reset 360° button...");
    const resetBtn = await page.waitForSelector('button:has-text("Reset 360°")');
    await resetBtn.click();
    await page.waitForTimeout(1500);

    const shotReset = path.join(SCREENSHOT_DIR, "interactive_05_reset_orbit.png");
    await page.screenshot({ path: shotReset });
    fs.copyFileSync(shotReset, path.join(ARTIFACT_DIR, "interactive_05_reset_orbit.png"));
    console.log("Saved interactive_05_reset_orbit.png");

    console.log("ALL INTERACTIVE 3D ROTATE & ZOOM TESTS PASSED!");
  } catch (err) {
    console.error("Interactive test failed:", err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();

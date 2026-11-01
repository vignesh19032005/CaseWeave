import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const ARTIFACT_DIR = "C:/Users/VIGNESH/.gemini/antigravity/brain/e54f53c4-ecda-42c8-b3ae-8a0558bbc92c";
const SCREENSHOT_DIR = "./test-screenshots";

if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function run() {
  console.log("Launching headless browser...");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  try {
    // 1. Login
    console.log("Navigating to /login...");
    await page.goto("http://localhost:3000/login", { waitUntil: "networkidle" });
    await page.fill('input[type="password"]', "changeme123");
    await page.click('button[type="submit"]');
    await page.waitForTimeout(1500);

    // 2. Open Case Page
    console.log("Navigating to Case CW-E65FA6...");
    await page.goto("http://localhost:3000/case/CW-E65FA6", { waitUntil: "networkidle" });
    await page.waitForTimeout(3000);

    // 3. Verify Sandbox Engine title
    console.log("Waiting for Virtual Crime Scene Sandbox component...");
    await page.waitForSelector('text=Virtual Crime Scene Sandbox', { timeout: 20000 });
    console.log("Found Virtual Crime Scene Sandbox component!");
    await page.waitForTimeout(2000); // Allow 3D canvas and meshes to render

    // Capture Overview
    const shot1 = path.join(SCREENSHOT_DIR, "01_sandbox_overview.png");
    await page.screenshot({ path: shot1, fullPage: false });
    fs.copyFileSync(shot1, path.join(ARTIFACT_DIR, "01_sandbox_overview.png"));
    console.log("Saved 01_sandbox_overview.png");

    // 4. Test Camera Presets
    console.log("Testing Camera Angles: Shutter Breach View...");
    const shutterBtn = await page.waitForSelector('button:has-text("Shutter Breach View")');
    await shutterBtn.click();
    await page.waitForTimeout(1500);
    const shot2 = path.join(SCREENSHOT_DIR, "02_camera_shutter_close.png");
    await page.screenshot({ path: shot2, fullPage: false });
    fs.copyFileSync(shot2, path.join(ARTIFACT_DIR, "02_camera_shutter_close.png"));
    console.log("Saved 02_camera_shutter_close.png");

    console.log("Testing Guard Sightline Raycast...");
    const sightlineBtn = await page.waitForSelector('button:has-text("Guard Sightline POV")');
    await sightlineBtn.click();
    await page.waitForTimeout(1500);
    const shot3 = path.join(SCREENSHOT_DIR, "03_guard_sightline_blocked.png");
    await page.screenshot({ path: shot3, fullPage: false });
    fs.copyFileSync(shot3, path.join(ARTIFACT_DIR, "03_guard_sightline_blocked.png"));
    console.log("Saved 03_guard_sightline_blocked.png");

    // 5. Test Scenario 2 Switch
    console.log("Switching to Scenario 2 (Inside Collusion)...");
    const scen2Btn = await page.waitForSelector('button:has-text("Inside Collusion")');
    await scen2Btn.click();
    await page.waitForTimeout(1500);
    const shot4 = path.join(SCREENSHOT_DIR, "04_scenario_2_inside_collusion.png");
    await page.screenshot({ path: shot4, fullPage: false });
    fs.copyFileSync(shot4, path.join(ARTIFACT_DIR, "04_scenario_2_inside_collusion.png"));
    console.log("Saved 04_scenario_2_inside_collusion.png");

    // 6. Test Officer Custom Hypothesis Modal & Socratic Interview
    console.log("Opening Propose Custom Scenario modal...");
    const proposeBtn = await page.waitForSelector('button:has-text("Propose Custom Scenario")');
    await proposeBtn.click();
    await page.waitForTimeout(1000);

    const textarea = await page.waitForSelector('textarea[placeholder*="What if the intruder entered"]');
    await textarea.fill("What if an accomplice entered via the roof vent, waited until the guard shift, and unlocked the rear shutter from the inside?");
    
    console.log("Requesting Socratic Forensic Verification Questions...");
    const interviewBtn = await page.waitForSelector('button:has-text("Verify Hypothesis with AI Advisor")');
    await interviewBtn.click();

    // Wait for Socratic questions
    console.log("Waiting for Meta LLM Socratic questions...");
    await page.waitForSelector('text=Forensic Advisor Verification Questions', { timeout: 30000 });
    console.log("Socratic verification questions generated successfully!");

    // Capture modal screenshot with questions
    await page.waitForTimeout(1000);
    const shot5 = path.join(SCREENSHOT_DIR, "05_socratic_interview_modal.png");
    await page.screenshot({ path: shot5, fullPage: false });
    fs.copyFileSync(shot5, path.join(ARTIFACT_DIR, "05_socratic_interview_modal.png"));
    console.log("Saved 05_socratic_interview_modal.png");

    // Click suggested answers for verification
    const ansButtons = await page.$$('button:has-text("No"), button:has-text("Yes"), button:has-text("Confirmed"), button:has-text("Consistent"), button:has-text("None"), button:has-text("Exterior")');
    for (const btn of ansButtons.slice(0, 3)) {
      await btn.click().catch(() => {});
    }

    console.log("Synthesizing 3D Digital Twin...");
    const synthBtn = await page.waitForSelector('button:has-text("Construct Custom Digital Twin & Simulate")');
    await synthBtn.click();
    await page.waitForTimeout(5000);

    const shot6 = path.join(SCREENSHOT_DIR, "06_custom_scenario_synthesized.png");
    await page.screenshot({ path: shot6, fullPage: false });
    fs.copyFileSync(shot6, path.join(ARTIFACT_DIR, "06_custom_scenario_synthesized.png"));
    console.log("Saved 06_custom_scenario_synthesized.png");

    console.log("ALL E2E BROWSER UI TESTS PASSED SUCCESSFULLY!");
  } catch (err) {
    console.error("Test failed with error:", err);
    const errShot = path.join(SCREENSHOT_DIR, "error_state.png");
    await page.screenshot({ path: errShot, fullPage: true }).catch(() => {});
    fs.copyFileSync(errShot, path.join(ARTIFACT_DIR, "error_state.png"));
    process.exit(1);
  } finally {
    await browser.close();
  }
}

run();

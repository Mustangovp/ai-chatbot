const { test, expect } = require('@playwright/test');
const {
  startSimulatedWorkout,
  verifyCoreMount,
  assertSingleCoreElement,
  verifyRafContinuity
} = require('./helpers/workoutHelper');

test.describe('APEX V2 Coach Card Rendering Pipeline & Legacy Fallback', () => {
  let consoleErrors = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors = [];
    // Catch console errors and uncaught exceptions
    page.on('pageerror', (exception) => {
      consoleErrors.push(exception.message || exception.toString());
    });
    
    // Navigate to local App endpoint
    await page.goto('/app');
  });

  test('CC-001: Execute workout with Push-Ups (Coach Card) and Squats (Legacy)', async ({ page }) => {
    // 1. Prepare target exercises
    const workoutData = [
      { name: 'Push-ups', sets: 2, reps: 10 },
      { name: 'Squats', sets: 2, reps: 12 }
    ];

    // 2. Start the simulated workout bypass profile modal
    await startSimulatedWorkout(page, workoutData);

    // ── STEP 1 & 2: Push-Up Renders Coach Card & Core Mounts ──
    const overlay = page.locator('#workout-overlay');
    await expect(overlay).toHaveClass(/active/);
    await expect(overlay).toHaveClass(/cc-active/); // Coach Card layout active

    // Verify Coach Card elements exist
    await expect(page.locator('.cc-root')).toBeVisible();
    await expect(page.locator('.cc-tech-item')).toHaveCount(5); // 5 technique pointers

    // Verify Biological Core mounts in the Coach Card slot
    const coreSlotCc = await verifyCoreMount(page, '#cc-core-slot');
    expect(coreSlotCc).toBe(true);

    // Dynamic checks
    await assertSingleCoreElement(page);
    expect(await verifyRafContinuity(page)).toBe(true);

    // ── STEP 3: Click Done ──
    const doneBtn = page.locator('.wo-done-btn');
    await doneBtn.click();

    await expect(page.locator('.wo-feedback')).toBeVisible();
    
    // Organism must return to the background slot during feedback
    const coreSlotFb = await verifyCoreMount(page, '#wo-organism-slot');
    expect(coreSlotFb).toBe(true);

    // Trigger feedback selection: 'Moderate' (medium)
    const moderateBtn = page.locator('.wo-fb-btn.medium');
    await moderateBtn.click();

    // ── STEP 5 & 6: Rest screen appears & Core returns to background slot ──
    await expect(page.locator('.wo-rest')).toBeVisible();
    
    // Core must move back to the background slot during rest timer phase
    const coreSlotRest = await verifyCoreMount(page, '#wo-organism-slot');
    expect(coreSlotRest).toBe(true);

    // Skip the rest timer
    const skipBtn = page.locator('.wo-skip-btn');
    await skipBtn.click();

    // ── PUSH-UPS SET 2 ──
    await expect(page.locator('.cc-root')).toBeVisible();
    await page.locator('.wo-done-btn').click();
    await expect(page.locator('.wo-feedback')).toBeVisible();
    await page.locator('.wo-fb-btn.medium').click();
    await expect(page.locator('.wo-rest')).toBeVisible();
    await page.locator('.wo-skip-btn').click();

    // ── STEP 7: Squats (next exercise) Renders using Unified Renderer ──
    await expect(overlay).toHaveClass(/active/);
    await expect(overlay).toHaveClass(/cc-active/); // unified rendering pipeline

    // Verify simple legacy element layout
    await expect(page.locator('.cc-ex-name-en')).toHaveText('Squats');
    
    // Core must be mapped to #cc-core-slot
    const coreSlotLegacy = await verifyCoreMount(page, '#cc-core-slot');
    expect(coreSlotLegacy).toBe(true);

    // Complete Squats Set 1
    await page.locator('.wo-done-btn').click();
    await page.locator('.wo-fb-btn.medium').click();
    await page.locator('.wo-skip-btn').click();

    // Complete Squats Set 2 (Final set -> transitions directly to done screen)
    await page.locator('.wo-done-btn').click();
    await page.locator('.wo-fb-btn.medium').click();

    // ── STEP 8: Complete Workout Survey ──
    await expect(page.locator('.wo-complete-title')).toBeVisible();
    await page.locator('.wo-done-btn').click(); // Moves to recovery survey

    // Fill the recovery check-in forms
    await expect(page.locator('.wo-rec-title')).toBeVisible();
    await page.locator('.wo-rec-save').click(); // Saves and exits

    // ── STEP 9 & 10: Exit Workout & Core returns to Overview stage ──
    await expect(overlay).not.toHaveClass(/active/); // overlay hidden
    
    // Core must return to the primary stage
    const coreSlotStage = await verifyCoreMount(page, '#phys-core-stage');
    expect(coreSlotStage).toBe(true);

    // Dynamic checks
    await assertSingleCoreElement(page);
    expect(await verifyRafContinuity(page)).toBe(true);

    // ── CONSOLE ERRORS AUDIT ──
    expect(consoleErrors).toEqual([]); // Ensure zero uncaught JS exceptions
  });
});

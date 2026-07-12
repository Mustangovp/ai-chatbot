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

  test.skip('CC-001: Execute workout with Push-Ups (Coach Card) and Squats (Legacy)', async ({ page }) => {
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

test.describe('Nutrition pipe-table rendering', () => {
  async function render(page, text, viewport) {
    if (viewport) await page.setViewportSize(viewport);
    return page.evaluate((raw) => {
      const host = document.createElement('div');
      host.id = 'nutrition-render-test';
      host.style.width = '100%';
      document.body.append(host);
      host.innerHTML = renderMarkdown(raw);
      return {
        meals: [...host.querySelectorAll('.nutri-meal')].map((meal) => meal.textContent.trim()),
        rawPipes: host.textContent.includes('|'),
        nutritionCards: host.querySelectorAll('.nutri').length,
        workoutCards: host.querySelectorAll('.wo-intro').length,
        paragraph: host.querySelector('p')?.textContent || '',
        overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      };
    }, text);
  }

  test.beforeEach(async ({ page }) => {
    await page.goto('/app');
  });

  test('NUT-001: standard Markdown table renders all four meals without raw pipes', async ({ page }) => {
    const result = await render(page, [
      '| Meal | Quantity | Protein | Carbs | Fat | Kcal |',
      '| --- | --- | --- | --- | --- | --- |',
      '| Breakfast | Oats 80 g | 25 | 60 | 10 | 420 |',
      '| Lunch | Chicken 200 g | 45 | 70 | 18 | 620 |',
      '| Snack | Yogurt 250 g | 20 | 35 | 8 | 300 |',
      '| Dinner | Salmon 180 g | 40 | 55 | 22 | 560 |',
      '| Total | | 130 | 220 | 58 | 1900 |',
    ].join('\n'));
    expect(result.nutritionCards).toBe(1);
    expect(result.meals).toHaveLength(4);
    expect(result.rawPipes).toBe(false);
  });

  test('NUT-002: separator-less Bulgarian meal rows render consistently', async ({ page }) => {
    const result = await render(page, [
      'Закуска | Овес 80 г | 25 | 60 | 10 | 420',
      'Обяд | Пиле 200 г | 45 | 70 | 18 | 620',
      'Междинно | Кисело мляко 250 г | 20 | 35 | 8 | 300',
      'Вечеря | Сьомга 180 г | 40 | 55 | 22 | 560',
    ].join('\n'));
    expect(result.meals).toHaveLength(4);
    expect(result.rawPipes).toBe(false);
    expect(result.meals.join(' ')).toContain('Закуска');
    expect(result.meals.join(' ')).toContain('Вечеря');
  });

  test('NUT-003: mixed standard and separator-less nutrition sections have no raw pipes', async ({ page }) => {
    const result = await render(page, [
      '| Meal | Quantity | Protein | Carbs | Fat | Kcal |',
      '| --- | --- | --- | --- | --- |',
      '| Breakfast | Eggs 3 | 24 | 20 | 18 | 340 |',
      '',
      'Lunch | Rice and chicken | 45 | 75 | 15 | 620',
      'Snack | Greek yogurt | 20 | 30 | 8 | 280',
      'Dinner | Fish and potatoes | 38 | 65 | 20 | 540',
    ].join('\n'));
    expect(result.nutritionCards).toBe(2);
    expect(result.meals).toHaveLength(4);
    expect(result.rawPipes).toBe(false);
  });

  test('NUT-004: English separator-less header works, prose pipes stay plain, and workout cards remain unchanged', async ({ page }) => {
    const nutrition = await render(page, [
      'Meal | Quantity | Protein | Carbs | Fat | Kcal',
      'Breakfast | Toast and eggs | 24 | 38 | 16 | 410',
      'Lunch | Beef and rice | 42 | 72 | 20 | 640',
    ].join('\n'));
    expect(nutrition.meals).toHaveLength(2);
    expect(nutrition.rawPipes).toBe(false);

    const prose = await render(page, 'Use A | B when comparing two options.');
    expect(prose.nutritionCards).toBe(0);
    expect(prose.paragraph).toContain('A | B');

    const workout = await render(page, [
      '| Exercise | Sets | Reps | Rest | Note |',
      '| --- | --- | --- | --- | --- |',
      '| Squats | 3 | 10 | 60 | steady |',
    ].join('\n'));
    expect(workout.workoutCards).toBe(1);
  });

  test('NUT-005: nutrition cards fit a Chromium mobile viewport', async ({ page }) => {
    const result = await render(page, [
      'Breakfast | Oats 80 g | 25 | 60 | 10 | 420',
      'Lunch | Chicken 200 g | 45 | 70 | 18 | 620',
      'Snack | Yogurt 250 g | 20 | 35 | 8 | 300',
      'Dinner | Salmon 180 g | 40 | 55 | 22 | 560',
    ].join('\n'), { width: 360, height: 740 });
    expect(result.meals).toHaveLength(4);
    expect(result.overflow).toBe(false);
  });
});

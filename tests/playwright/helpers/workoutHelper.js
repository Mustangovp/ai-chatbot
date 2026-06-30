/**
 * Playwright helper functions for APEX Pulse Pro testing.
 */

/**
 * Bypasses the initial onboarding profile by starting a custom workout directly.
 * @param {import('@playwright/test').Page} page
 * @param {Array<object>} exercises
 */
async function startSimulatedWorkout(page, exercises) {
  // Start the workout with the bypass parameter (true)
  await page.evaluate((exs) => {
    window.startWorkout(exs, true);
  }, exercises);
}

/**
 * Verifies that the Biological Core is mounted to the correct DOM selector.
 * @param {import('@playwright/test').Page} page
 * @param {string} targetSelector
 */
async function verifyCoreMount(page, targetSelector) {
  const isAligned = await page.evaluate((sel) => {
    const core = document.getElementById('phys-core');
    let slot = document.querySelector(sel);
    if (!core || !slot) return false;
    
    // Map stage selector to the specific overview core slot inside it
    if (sel === '#phys-core-stage') {
      const overviewSlot = document.getElementById('overview-core-slot');
      if (overviewSlot) slot = overviewSlot;
    }
    
    // Check if the core is physically positioned near the slot (visual overlay)
    const coreRect = core.getBoundingClientRect();
    const slotRect = slot.getBoundingClientRect();
    
    // Allow small tolerance (e.g. 25px) for transition lag in tests
    const xDiff = Math.abs((coreRect.left + coreRect.width / 2) - (slotRect.left + slotRect.width / 2));
    const yDiff = Math.abs((coreRect.top + coreRect.height / 2) - (slotRect.top + slotRect.height / 2));
    
    return xDiff < 25 && yDiff < 25;
  }, targetSelector);
  return isAligned;
}

/**
 * Asserts that exactly one #phys-core element exists in the DOM.
 * @param {import('@playwright/test').Page} page
 */
async function assertSingleCoreElement(page) {
  const count = await page.locator('#phys-core').count();
  if (count !== 1) {
    throw new Error(`Expected exactly 1 #phys-core element, but found ${count}`);
  }
}

/**
 * Checks if requestAnimationFrame continues running on the page.
 * @param {import('@playwright/test').Page} page
 * @returns {Promise<boolean>}
 */
async function verifyRafContinuity(page) {
  return await page.evaluate(() => {
    return new Promise((resolve) => {
      let count = 0;
      function tick() {
        count++;
        if (count >= 5) {
          resolve(true);
        } else {
          requestAnimationFrame(tick);
        }
      }
      requestAnimationFrame(tick);
    });
  });
}

module.exports = {
  startSimulatedWorkout,
  verifyCoreMount,
  assertSingleCoreElement,
  verifyRafContinuity
};

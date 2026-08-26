const { test, expect } = require('@playwright/test');

const profile = {
  goal: 'fat_loss', age: '30', weight: '75', height: '178', gender: 'male',
  level: 'beginner', equipment: 'gym', sleepQuality: 'average',
  stressLevel: 'moderate', recoveryFeel: 'ok', activityLevel: 'moderate', frequency: '3',
};

test.describe('stable APEX mobile shell', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript((value) => {
      const owner = 'mobile-playwright';
      localStorage.setItem('apexAnonymousOwnerV1', owner);
      localStorage.setItem(`apexOwnedV1:anonymous:${owner}:apexProfile`, JSON.stringify(value));
    }, profile);
    await page.goto('/app?lang=en');
    await expect(page.locator('#core')).toBeVisible();
  });

  test('fits the viewport, keeps the Core visible, and has no page errors', async ({ page }) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    const menuBox = await page.locator('#menu-btn').boundingBox();
    expect(menuBox.width).toBeGreaterThanOrEqual(44);
    expect(menuBox.height).toBeGreaterThanOrEqual(44);
    expect(errors).toEqual([]);
  });

  test('drawer and profile sheet remain reachable and dismissible', async ({ page }) => {
    await page.locator('#menu-btn').click();
    await expect(page.locator('#drawer')).toHaveClass(/on/);
    const closeBox = await page.locator('.drawer-close').boundingBox();
    expect(closeBox.width).toBeGreaterThanOrEqual(44);
    expect(closeBox.height).toBeGreaterThanOrEqual(44);
    await page.locator('.drawer-close').click();
    await expect(page.locator('#drawer')).not.toHaveClass(/on/);
    await page.evaluate(() => openProfile(2));
    const sheet = page.locator('#profile-modal .sheet');
    await expect(sheet).toBeVisible();
    expect(await sheet.evaluate(el => el.scrollHeight >= el.clientHeight)).toBeTruthy();
    await page.locator('#profile-modal').click({ position: { x: 2, y: 2 } });
    await expect(page.locator('#profile-modal')).not.toHaveClass(/on/);
  });

  test('chat composer remains visible after a mobile viewport resize', async ({ page }) => {
    await page.evaluate(() => enterConsult());
    await expect(page.locator('#consult')).toHaveClass(/on/);
    await page.locator('#user-in').fill('A deliberately long message that must stay inside the mobile composer without making the app scroll sideways.');
    await page.setViewportSize({ width: 390, height: 560 });
    await expect(page.locator('.inputbar')).toBeVisible();
    const input = await page.locator('.inputbar').boundingBox();
    const send = await page.locator('.send-btn').boundingBox();
    expect(input.y + input.height).toBeLessThanOrEqual(560);
    expect(send.y + send.height).toBeLessThanOrEqual(560);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });

  test('keeps Position and the primary action ahead of supporting profile detail', async ({ page }) => {
    for (const viewport of [
      { width: 360, height: 800 },
      { width: 390, height: 844 },
      { width: 393, height: 873 },
      { width: 430, height: 932 },
    ]) {
      await page.setViewportSize(viewport);
      await page.reload();

      const position = await page.locator('.position-head').boundingBox();
      const action = await page.locator('.cta-row .cta').first().boundingBox();
      const facts = await page.locator('#calibration-facts').boundingBox();
      const signals = await page.locator('#position-signals').boundingBox();

      expect(position).not.toBeNull();
      expect(action).not.toBeNull();
      expect(action.y + action.height).toBeLessThanOrEqual(viewport.height);
      expect(facts.y).toBeGreaterThanOrEqual(viewport.height);
      expect(signals.y).toBeGreaterThanOrEqual(action.y + action.height);
      await page.locator('#calibration-facts').scrollIntoViewIfNeeded();
      await expect(page.locator('#calibration-facts')).toBeVisible();
      await expect(page.locator('#position-signals')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
      await expect(page.locator('#core')).toBeVisible();
    }
  });
});

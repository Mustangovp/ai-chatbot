const { test, expect } = require('@playwright/test');

test.describe('landing paid access pause', () => {
  for (const route of ['/', '/en']) {
    test(`${route} keeps FREE available and has no paid checkout action`, async ({ page }) => {
      if (route === '/') {
        await page.addInitScript(() => localStorage.setItem('apexLang', 'bg'));
      }
      await page.goto(route);

      await expect(page.locator('#pricing a[href^="/app?lang="]')).toHaveCount(1);
      await expect(page.locator('#pricing [data-paid-unavailable]')).toHaveCount(2);
      await expect(page.locator('#pricing [data-paid-unavailable]')).toHaveText(
        [route === '/' ? 'Очаквайте скоро' : 'Coming soon', route === '/' ? 'Очаквайте скоро' : 'Coming soon'],
      );

      const paidActions = await page.locator(
        '#pricing a[href*="plan="], #pricing [onclick*="goCheckout"]',
      ).count();
      expect(paidActions).toBe(0);
      await expect(page.locator('body')).not.toContainText(
        route === '/' ? 'НАЙ-ИЗБИРАН' : 'MOST POPULAR',
      );
    });
  }
});

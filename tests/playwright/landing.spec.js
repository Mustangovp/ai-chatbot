const { test, expect } = require('@playwright/test');

test.describe('landing paid access pause', () => {
  const cases = [
    { route: '/', locale: 'bg', unavailable: 'Очаквайте скоро' },
    { route: '/en', locale: 'en', unavailable: 'Coming soon' },
    { route: '/bg', locale: 'bg', unavailable: 'Очаквайте скоро' },
  ];

  for (const { route, locale, unavailable: unavailableText } of cases) {
    test(`${route} keeps FREE available and has no paid checkout action`, async ({ page }) => {
      if (route === '/') {
        await page.addInitScript(() => localStorage.setItem('apexLang', 'bg'));
      }
      await page.goto(route);

      if (route === '/') await expect(page).toHaveURL(/\/bg$/);
      await expect(page.locator('html')).toHaveAttribute('lang', locale);

      const pricing = page.locator('#plans.pricing');
      await expect(pricing).toHaveCount(1);
      const freeEntry = pricing.locator('.plans > article').filter({ hasText: locale === 'bg' ? 'БЕЗПЛАТНО' : 'FREE' }).locator('a');
      await expect(freeEntry).toHaveCount(1);
      await expect(freeEntry).toHaveAttribute('href', '/app');

      const unavailable = pricing.locator('.plans > article.unavailable');
      await expect(unavailable).toHaveCount(2);
      await expect(unavailable.locator('.comingSoon')).toHaveText([unavailableText, unavailableText]);

      const paidActions = await page.locator(
        '#plans a[href*="plan="], #plans [onclick*="goCheckout"]',
      ).count();
      expect(paidActions).toBe(0);
      await expect(page.locator('body')).not.toContainText(
        locale === 'bg' ? 'НАЙ-ИЗБИРАН' : 'MOST POPULAR',
      );
    });
  }
});

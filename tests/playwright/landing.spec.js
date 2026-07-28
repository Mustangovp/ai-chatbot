const { test, expect } = require('@playwright/test');

test.describe('landing checkout fallback URLs', () => {
  for (const route of ['/', '/en']) {
    test(`${route} never produces an empty plan query parameter`, async ({ page }) => {
      await page.goto(route);

      const urls = await page.evaluate(() => [
        checkoutFallbackUrl('bg', ''),
        checkoutFallbackUrl('bg', null),
        checkoutFallbackUrl('bg', undefined),
        checkoutFallbackUrl('bg', '   '),
        checkoutFallbackUrl('bg', 'core'),
      ]);

      expect(urls.slice(0, 4)).toEqual(['/app', '/app', '/app', '/app']);
      expect(urls[4]).toBe('/app?lang=bg&plan=core');
    });
  }
});

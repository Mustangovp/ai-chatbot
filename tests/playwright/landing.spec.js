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

test.describe('landing mobile hero hierarchy', () => {
  for (const route of ['/', '/en']) {
    test(`${route} keeps the goal action and directory badges contained on mobile`, async ({ page }) => {
      for (const viewport of [
        { width: 390, height: 844 },
        { width: 360, height: 800 },
      ]) {
        await page.setViewportSize(viewport);
        await page.goto(route);
        await page.waitForTimeout(1800);

        const layout = await page.evaluate(() => {
          const bounds = (selector) => {
            const rect = document.querySelector(selector).getBoundingClientRect();
            return { top: rect.top, bottom: rect.bottom, left: rect.left, right: rect.right };
          };
          const viewportWidth = document.documentElement.clientWidth;
          const cookieBar = document.querySelector('#cookiebar');

          return {
            viewportWidth,
            scrollWidth: document.documentElement.scrollWidth,
            logo: bounds('.logo'),
            action: bounds('.gl-btn'),
            reassurance: bounds('.micro'),
            cookie: cookieBar?.classList.contains('show') ? bounds('#cookiebar') : null,
            badgeStrip: bounds('header.hero .ph-badge'),
            badgeLinks: [...document.querySelectorAll('header.hero .ph-badge a')].map((link) => ({
              href: link.getAttribute('href'),
              target: link.getAttribute('target'),
            })),
          };
        });

        expect(layout.scrollWidth).toBeLessThanOrEqual(layout.viewportWidth);
        expect(layout.logo.right).toBeLessThanOrEqual(layout.viewportWidth);
        expect(layout.action.top).toBeGreaterThan(layout.logo.bottom);
        expect(layout.action.bottom).toBeLessThanOrEqual(viewport.height);
        expect(layout.reassurance.top).toBeGreaterThan(layout.action.bottom);
        if (layout.cookie) {
          expect(layout.action.bottom).toBeLessThanOrEqual(layout.cookie.top);
        }
        expect(layout.badgeStrip.right).toBeLessThanOrEqual(layout.viewportWidth);
        expect(layout.badgeLinks).toHaveLength(4);
        for (const link of layout.badgeLinks) {
          expect(link.href).toMatch(/^https:\/\//);
          expect(link.target).toBe('_blank');
        }
      }
    });
  }
});

const { test, expect } = require('@playwright/test');

test.describe('authoritative FREE activation analytics', () => {
  test('forwards only the minimal server confirmation after a delivered result', async ({ page }) => {
    const requests = [];
    await page.route('**/chat', async (route) => {
      requests.push(route.request().headers());
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: [
          'data: {"t":"Your structured training result."}\n\n',
          'data: {"activation":{"event":"apex_free_activation","activation_type":"training","authenticated":false,"locale":"en"}}\n\n',
          'data: {"done":true}\n\n',
        ].join(''),
      });
    });

    await page.goto('/app?lang=en');
    await page.evaluate(() => {
      localStorage.setItem('apexProfile', JSON.stringify({
        goal: 'strength', equipment: 'gym', level: 'intermediate',
        age: '30', height: '180', weight: '80', recoveryFeel: 'fresh',
      }));
      window.__freeActivationEvents = [];
      window.gtag = (...args) => window.__freeActivationEvents.push(args);
      if (typeof enterConsult === 'function') enterConsult('');
      document.getElementById('profile-modal')?.classList.remove('on');
    });
    expect(await page.evaluate(() => window.__freeActivationEvents)).toEqual([]);

    await page.locator('#user-in').fill('Build a workout');
    await page.locator('.send-btn').click();
    await expect.poll(() => page.evaluate(() => window.__freeActivationEvents)).toEqual([
      ['event', 'apex_free_activation', {
        activation_type: 'training', authenticated: false, locale: 'en',
      }],
    ]);

    expect(requests).toHaveLength(1);
    expect(requests[0]['x-apex-activation-confirmation']).toBe('1');
  });
});

const { test, expect } = require('@playwright/test');

test.describe('authoritative FREE activation analytics', () => {
  async function prepare(page) {
    await page.evaluate(() => {
      localStorage.setItem('apexProfile', JSON.stringify({
        goal: 'strength', equipment: 'gym', level: 'intermediate',
        age: '30', height: '180', weight: '80', recoveryFeel: 'fresh',
      }));
      window.__freeActivationEvents = [];
      window.gtag = (...args) => window.__freeActivationEvents.push(args);
      window.__apexAnalyticsReady = true;
      if (typeof enterConsult === 'function') enterConsult('');
      document.getElementById('profile-modal')?.classList.remove('on');
    });
  }

  test('confirms only a rendered candidate, then delivers once after consent', async ({ page }) => {
    const chatRequests = [];
    const confirmations = [];
    const deliveries = [];
    const acknowledgements = [];
    await page.route('**/gtag/js*', route => route.fulfill({ status: 200, body: '' }));
    await page.route('**/chat', async route => {
      chatRequests.push(route.request().headers());
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: [
          'data: {"t":"**Workout**\\n- **Goal:** strength\\n\\n- Use dumbbells: They match your equipment."}\n\n',
          'data: {"activation_candidate":{"token":"candidate-token-for-confirmation-1234567890","activation_type":"coaching","locale":"en"}}\n\n',
          'data: {"done":true}\n\n',
        ].join(''),
      });
    });
    await page.route('**/api/free-activation/confirm', async route => {
      confirmations.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });
    await page.route('**/api/free-activation/delivery', async route => {
      deliveries.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ delivery: { token: 'delivery-token-for-acknowledgement-123456', event: {
          event: 'apex_free_activation', activation_type: 'coaching', authenticated: false, locale: 'en',
        } } }),
      });
    });
    await page.route('**/api/free-activation/delivery/ack', async route => {
      acknowledgements.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await page.goto('/app?lang=en');
    await prepare(page);
    await page.locator('#user-in').fill('Build a workout');
    await page.locator('.send-btn').click();

    await expect.poll(() => confirmations.length).toBe(1);
    expect(deliveries).toHaveLength(0);
    expect(await page.evaluate(() => window.__freeActivationEvents)).toEqual([]);
    expect(chatRequests).toHaveLength(1);
    expect(chatRequests[0]['x-apex-activation-confirmation']).toBeUndefined();

    await page.evaluate(() => {
      localStorage.setItem('apexConsent', 'granted');
      window.apexAnalyticsConsentChanged();
    });
    await expect.poll(() => acknowledgements.length).toBe(1);
    expect(deliveries).toHaveLength(1);
    expect(confirmations[0]).toEqual({ candidate: 'candidate-token-for-confirmation-1234567890' });
    expect(acknowledgements[0]).toEqual({ token: 'delivery-token-for-acknowledgement-123456' });
    expect(await page.evaluate(() => window.__freeActivationEvents)).toEqual([
      ['event', 'apex_free_activation', {
        activation_type: 'coaching', authenticated: false, locale: 'en',
      }],
    ]);
  });

  test('does not confirm a training candidate when the exercise cards did not render', async ({ page }) => {
    let confirmations = 0;
    await page.route('**/gtag/js*', route => route.fulfill({ status: 200, body: '' }));
    await page.route('**/chat', async route => route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'data: {"t":"The delivery could not be rendered as a workout."}\n\n',
        'data: {"training_completion":{"sessions":[{"exercises":[{"prescription_id":"p1","exercise_id":"bodyweight.squat","exercise_version":"v1","display_name":"Bodyweight squat"}]}]}}\n\n',
        'data: {"activation_candidate":{"token":"candidate-token-for-training-render-123456789","activation_type":"training","locale":"en"}}\n\n',
        'data: {"done":true}\n\n',
      ].join(''),
    }));
    await page.route('**/api/free-activation/confirm', async route => {
      confirmations += 1;
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await page.goto('/app?lang=en');
    await prepare(page);
    await page.locator('#user-in').fill('Build a workout');
    await page.locator('.send-btn').click();
    await expect(page.locator('.msg.a').last()).toContainText('could not be rendered');
    await page.waitForTimeout(150);
    expect(confirmations).toBe(0);
  });

  test('confirms a training candidate only after matching exercise cards render', async ({ page }) => {
    const confirmations = [];
    await page.route('**/gtag/js*', route => route.fulfill({ status: 200, body: '' }));
    await page.route('**/chat', async route => route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'data: {"t":"| Exercise | Sets | Reps | Rest | Note |\\n| --- | --- | --- | --- | --- |\\n| Goblet Squat | 3 | 8-12 | 60 sec | Controlled tempo |"}\n\n',
        'data: {"training_completion":{"sessions":[{"exercises":[{"prescription_id":"p1","exercise_id":"dumbbell.goblet_squat","exercise_version":"v1","display_name":"Goblet Squat"}]}]}}\n\n',
        'data: {"activation_candidate":{"token":"candidate-token-for-training-success-123456789","activation_type":"training","locale":"en"}}\n\n',
        'data: {"done":true}\n\n',
      ].join(''),
    }));
    await page.route('**/api/free-activation/confirm', async route => {
      confirmations.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await page.goto('/app?lang=en');
    await prepare(page);
    await page.locator('#user-in').fill('Build a workout');
    await page.locator('.send-btn').click();
    await expect(page.locator('.workout-protocol .workout-exercise-card')).toHaveCount(1);
    await expect.poll(() => confirmations.length).toBe(1);
    expect(confirmations[0]).toEqual({ candidate: 'candidate-token-for-training-success-123456789' });
  });

  test('excludes owner sessions and strips private query values before analytics initialization', async ({ page }) => {
    const confirmations = [];
    await page.addInitScript(() => localStorage.setItem('apexOwner', 'true'));
    await page.route('**/gtag/js*', route => route.fulfill({ status: 200, body: '' }));
    await page.route('**/chat', async route => route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'data: {"t":"**Workout**\\n- **Goal:** strength\\n\\n- Use dumbbells: They match your equipment."}\n\n',
        'data: {"activation_candidate":{"token":"candidate-token-owner-exclusion-123456789","activation_type":"coaching","locale":"en"}}\n\n',
        'data: {"done":true}\n\n',
      ].join(''),
    }));
    await page.route('**/api/free-activation/confirm', async route => {
      confirmations.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await page.goto('/app?lang=en&token=private-token-value&q=private-query-value');
    const config = await page.evaluate(() => window.dataLayer.find(entry => entry[0] === 'config'));
    expect(JSON.stringify(config)).not.toContain('private-token-value');
    expect(JSON.stringify(config)).not.toContain('private-query-value');
    expect(config[2].page_location).toMatch(/\/app$/);

    await prepare(page);
    await page.locator('#user-in').fill('Build a workout');
    await page.locator('.send-btn').click();
    await page.waitForTimeout(150);
    expect(confirmations).toHaveLength(0);
  });

  test('keeps startup usable when local storage rejects initialization reads', async ({ page }) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      const fail = () => { throw new Error('storage unavailable'); };
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        value: { getItem: fail, setItem: fail, removeItem: fail },
      });
    });
    await page.route('**/gtag/js*', route => route.fulfill({ status: 200, body: '' }));

    await page.goto('/app?lang=en');
    await expect(page.locator('#stage')).toBeVisible();
    expect(errors).toEqual([]);
  });
});

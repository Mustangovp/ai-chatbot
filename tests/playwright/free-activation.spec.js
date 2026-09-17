const { test, expect } = require('@playwright/test');

test.describe('authoritative FREE activation analytics', () => {
  async function prepare(page) {
    await page.evaluate(() => {
      localStorage.setItem('apexProfile', JSON.stringify({
        goal: 'strength', equipment: 'gym', level: 'intermediate',
        age: '30', height: '180', weight: '80', recoveryFeel: 'fresh',
      }));
      window.__freeActivationEvents = [];
      window.gtag = (...args) => {
        window.__freeActivationEvents.push(args);
        if (args[0] === 'event' && typeof args[2]?.event_callback === 'function') {
          queueMicrotask(() => args[2].event_callback());
        }
      };
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
    expect(await page.evaluate(() => window.__freeActivationEvents
      .filter(args => args[0] === 'event')
      .map(args => ({
        name: args[1],
        payload: {
          activation_type: args[2].activation_type,
          authenticated: args[2].authenticated,
          locale: args[2].locale,
          callback: typeof args[2].event_callback,
        },
      })))).toEqual([{
      name: 'apex_free_activation',
      payload: {
        activation_type: 'coaching', authenticated: false, locale: 'en', callback: 'function',
      },
    }]);
    const events = await page.evaluate(() => window.__freeActivationEvents);
    const grantedConsent = events.findIndex(args =>
      args[0] === 'consent' && args[1] === 'update' && args[2].analytics_storage === 'granted');
    const activationEvent = events.findIndex(args => args[0] === 'event');
    expect(grantedConsent).toBeGreaterThanOrEqual(0);
    expect(grantedConsent).toBeLessThan(activationEvent);
  });

  test('rechecks revoked consent after delivery lease and emits no activation event', async ({ page }) => {
    const releases = [];
    await page.route('**/gtag/js*', route => route.fulfill({ status: 200, body: '' }));
    await page.route('**/api/free-activation/delivery', async route => {
      await page.evaluate(() => {
        localStorage.setItem('apexConsent', 'denied');
        window.apexAnalyticsConsentChanged();
      });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ delivery: { token: 'delivery-token-revoked-before-emit-123456', event: {
          event: 'apex_free_activation', activation_type: 'training', authenticated: false, locale: 'en',
        } } }),
      });
    });
    await page.route('**/api/free-activation/delivery/release', async route => {
      releases.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await page.goto('/app?lang=en');
    await prepare(page);
    await page.evaluate(() => {
      localStorage.setItem('apexConsent', 'granted');
      window.apexAnalyticsConsentChanged();
    });

    await expect.poll(() => releases.length).toBe(1);
    expect(releases[0]).toEqual({ token: 'delivery-token-revoked-before-emit-123456' });
    expect(await page.evaluate(() => window.__freeActivationEvents
      .filter(args => args[0] === 'event'))).toEqual([]);
  });

  test('gtag exceptions and missing callbacks release delivery without breaking the app', async ({ page }) => {
    const releases = [];
    const deliveries = [];
    await page.route('**/gtag/js*', route => route.fulfill({ status: 200, body: '' }));
    await page.route('**/api/free-activation/delivery', async route => {
      deliveries.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ delivery: { token: 'delivery-token-gtag-throws-123456789', event: {
          event: 'apex_free_activation', activation_type: 'training', authenticated: false, locale: 'en',
        } } }),
      });
    });
    await page.route('**/api/free-activation/delivery/release', async route => {
      releases.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await page.goto('/app?lang=en');
    await prepare(page);
    await page.evaluate(() => {
      window.gtag = (...args) => {
        window.__freeActivationEvents.push(args);
        if (args[0] === 'event') throw new Error('gtag unavailable');
      };
      localStorage.setItem('apexConsent', 'granted');
      window.apexAnalyticsConsentChanged();
    });

    await expect.poll(() => releases.length).toBe(1);
    expect(deliveries).toHaveLength(1);
    expect(await page.locator('#stage')).toBeVisible();
  });

  test('callback timeout and acknowledgement failure use the recoverable release path', async ({ page }) => {
    const releases = [];
    const acknowledgements = [];
    let deliveryCount = 0;
    await page.route('**/gtag/js*', route => route.fulfill({ status: 200, body: '' }));
    await page.route('**/api/free-activation/delivery', async route => {
      deliveryCount += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ delivery: { token: `delivery-token-timeout-${deliveryCount}-123456789`, event: {
          event: 'apex_free_activation', activation_type: 'training', authenticated: false, locale: 'en',
        } } }),
      });
    });
    await page.route('**/api/free-activation/delivery/ack', async route => {
      acknowledgements.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":false}' });
    });
    await page.route('**/api/free-activation/delivery/release', async route => {
      releases.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
    });

    await page.goto('/app?lang=en');
    await prepare(page);
    await page.evaluate(() => {
      // The first event never calls the callback, modelling a page that stays
      // open while the provider callback is unavailable.
      window.gtag = (...args) => window.__freeActivationEvents.push(args);
      localStorage.setItem('apexConsent', 'granted');
      window.apexAnalyticsConsentChanged();
    });
    await expect.poll(() => releases.length, { timeout: 6000 }).toBe(1);
    expect(acknowledgements).toHaveLength(0);

    await page.evaluate(() => {
      window.gtag = (...args) => {
        window.__freeActivationEvents.push(args);
        if (args[0] === 'event') queueMicrotask(() => args[2].event_callback());
      };
      void window.maybeDeliverFreeActivationAnalytics();
    });
    await expect.poll(() => acknowledgements.length).toBe(1);
    await expect.poll(() => releases.length).toBe(2);
    expect(deliveryCount).toBe(2);
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

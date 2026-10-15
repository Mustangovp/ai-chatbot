const { test, expect } = require('@playwright/test');
const path = require('path');

const profile = { age: '33', weight: '76', height: '178', gender: 'male', goal: 'strength',
  level: 'intermediate', equipment: 'home', frequency: '3', sleepQuality: 'average',
  stressLevel: 'moderate', recoveryFeel: 'ok', activityLevel: 'moderate' };
const deferred = () => { let release; const promise = new Promise(resolve => { release = resolve; }); return { promise, release }; };
const billing = (plan = 'free', purchases = [], status = plan === 'free' ? 'free' : 'active') => ({
  entitlement: { plan, status, access_until: plan === 'free' ? null : '2035-05-20T12:00:00Z' },
  purchases, paid_sales_enabled: false,
});
const purchase = overrides => ({ reference: 'cs_test_owned', plan: 'core', state: 'paid',
  recorded_at: '2035-04-20T12:00:00Z', paid_at: null, amount_cents: 1234, currency: 'eur',
  access_until: '2035-05-20T12:00:00Z', refund_status: null, can_request_refund: true, ...overrides });

async function setup(page, { language = 'en', data = billing(), anonymous = false } = {}) {
  const state = { current: anonymous ? null : 'a', data, status: 200, reads: 0, withdrawals: [],
    result: { ok: true, refunded: true, access_revoked: true }, withdrawStatus: 200 };
  await page.addInitScript(({ language, profile }) => {
    localStorage.setItem('apexLang', language);
    localStorage.setItem('apexAnonymousOwnerV1', 'billing-anon');
    localStorage.setItem('apexOwnedV1:anonymous:billing-anon:apexProfile', JSON.stringify(profile));
  }, { language, profile });
  await page.route('**/auth/me', route => route.fulfill({ json: {
    authenticated: !!state.current, email: state.current ? `account-${state.current}@example.test` : null,
    plan: state.data.entitlement.plan, status: state.data.entitlement.status,
    current_period_end: state.data.entitlement.access_until,
  } }));
  await page.route('**/api/profile', route => route.fulfill({ json: { profile: { ...profile, language },
    training_constraint_records: [], training_constraint_load_state: 'ready' } }));
  await page.route('**/api/history', route => route.fulfill({ json: { workouts: [] } }));
  await page.route('**/api/conversations?*', route => route.fulfill({ json: { messages: [] } }));
  await page.route('**/auth/logout', route => { state.current = null; return route.fulfill({ json: { ok: true } }); });
  await page.route('**/api/billing', async route => {
    state.reads++;
    const snapshot = structuredClone(state.data), status = state.status, hold = state.readHold;
    if (hold) await hold.promise;
    await route.fulfill({ status, json: status === 200 ? snapshot : { error: 'billing_unavailable' } });
  });
  await page.route('**/withdraw', async route => {
    state.withdrawals.push(route.request().postDataJSON());
    if (state.hold) await state.hold.promise;
    if (state.networkFailure) return route.abort('failed');
    if (state.after) state.data = state.after;
    await route.fulfill({ status: state.withdrawStatus, json: state.result });
  });
  page.on('dialog', dialog => dialog.accept());
  await page.goto('/app?lang=' + language);
  await expect.poll(() => page.evaluate(() => DATA_OWNER.kind)).toBe(anonymous ? 'anonymous' : 'account');
  if (!anonymous) await expect.poll(() => page.evaluate(() => pfLoad().age)).toBe('33');
  await page.locator('#menu-btn').click();
  await page.locator('[onclick="menuAction(\'subscription\')"]').click();
  await expect(page.locator('#billing-surface')).toBeVisible();
  if (!anonymous) await expect(page.locator('[data-billing-access]')).toBeVisible();
  return state;
}

for (const language of ['bg', 'en']) {
  test(`${language}: truthful FREE and tier comparison, no checkout or unsupported benefits`, async ({ page }) => {
    const state = await setup(page, { language });
    await expect(page.locator('[data-billing-empty]')).toBeVisible();
    await expect(page.locator('#billing-surface')).not.toContainText(/card on file|следващо плащане|next billing|PDF|priority support|6×/i);
    await expect(page.locator('[data-billing-tier="free"]')).toContainText('GPT-6 Luna');
    await expect(page.locator('[data-billing-tier="free"]')).toContainText(language === 'bg' ? '10 съобщения за подвижен период от 24 часа' : '10 messages per rolling 24 hours');
    await expect(page.locator('[data-billing-tier="core"]')).toContainText('€9.99');
    await expect(page.locator('[data-billing-tier="pro"]')).toContainText('€14.99');
    await expect(page.locator('[data-billing-tier="pro"]')).toContainText('GPT-6.1 Sol');
    await expect(page.locator('#billing-surface')).toContainText(language === 'bg' ? /без автоматично подновяване/i : 'No automatic renewal');
    await expect(page.locator('[data-billing-request]')).toHaveCount(0);
    expect(state.withdrawals).toEqual([]);
  });

  for (const plan of ['core', 'pro']) {
    test(`${language}: legacy ${plan} expiry is shown without fabricated payment records`, async ({ page }) => {
      await setup(page, { language, data: billing(plan) });
      await expect(page.locator('[data-billing-access]')).toHaveText(plan.toUpperCase());
      await expect(page.locator('[data-billing-empty]')).toBeVisible();
      await expect(page.locator('[data-billing-purchase]')).toHaveCount(0);
      await expect(page.locator('#billing-surface')).toContainText('2035');
      await expect(page.locator('#billing-surface')).not.toContainText(/card on file|visa|mastercard|next billing/i);
    });
  }

  test(`${language}: recorded amount/date and refund statuses are not inferred`, async ({ page }) => {
    const state = await setup(page, { language, data: billing('core', [purchase()]) });
    await expect(page.locator('[data-billing-amount]')).toContainText(/12[,.]34/);
    await expect(page.locator('[data-billing-purchase]')).toContainText(language === 'bg' ? 'Дата на записа' : 'Record date');
    await expect(page.locator('[data-billing-purchase]')).not.toContainText(language === 'bg' ? 'Потвърдена дата на плащане' : 'Confirmed payment date');
    for (const outcome of ['pending', 'failed', 'unconfirmed', 'succeeded']) {
      state.data = billing('free', [purchase({ state: 'refund_pending', refund_status: outcome, can_request_refund: false })], 'revoked');
      await page.evaluate(() => showSubscription());
      await expect(page.locator('[data-billing-refund]')).toHaveText(await page.evaluate(outcome => tr().sub.refundStates[outcome], outcome));
      await expect(page.locator('[data-billing-request]')).toHaveCount(0);
    }
    for (const status of ['expired', 'revoked', 'grace']) {
      state.data = billing(status === 'grace' ? 'core' : 'free', [], status);
      await page.evaluate(() => showSubscription());
      await expect(page.locator('#billing-surface')).toContainText(await page.evaluate(status => tr().sub.statuses[status], status));
    }
  });
}

test('missing currency/amount stay unknown and a 5xx never manufactures FREE billing facts', async ({ page }) => {
  const state = await setup(page, { data: billing('pro', [purchase({ amount_cents: null, currency: null })]) });
  await expect(page.locator('[data-billing-amount]')).toHaveText('Not available');
  state.status = 503; await page.evaluate(() => showSubscription());
  await expect(page.locator('#billing-surface [role="alert"]')).toBeVisible();
  await expect(page.locator('[data-billing-access]')).toHaveCount(0);
  await expect(page.locator('[data-billing-empty]')).toHaveCount(0);
  state.status = 200; await page.locator('#billing-retry').click();
  await expect(page.locator('[data-billing-access]')).toHaveText('PRO');
});

test('anonymous access comparison does not read account billing', async ({ page }) => {
  const state = await setup(page, { anonymous: true });
  expect(state.reads).toBe(0);
  await expect(page.locator('#billing-surface')).toContainText('Sign in to view');
  await expect(page.locator('[data-billing-access]')).toHaveCount(0);
});

test('refund waits for positive ACK, schedules once and survives same-owner panel reopen', async ({ page }) => {
  const state = await setup(page, { data: billing('core', [purchase()]) });
  state.hold = deferred(); state.after = billing('free', [purchase({ state: 'refunded', can_request_refund: false })], 'revoked');
  await page.locator('[data-billing-request]').click();
  await expect.poll(() => state.withdrawals.length).toBe(1);
  expect(state.withdrawals[0]).toEqual({ session_id: 'cs_test_owned', lang: 'en' });
  await expect(page.locator('[data-billing-request]')).toBeDisabled();
  await expect(page.locator('#billing-status')).toHaveText('Checking your request…');
  await expect(page.locator('#billing-status')).not.toContainText('Refund confirmed');
  await page.evaluate(() => showSubscription());
  await expect(page.locator('[data-billing-request]')).toBeDisabled();
  state.hold.release();
  await expect(page.locator('#billing-status')).toHaveText('Refund confirmed. Access from this purchase has ended.');
  await expect(page.locator('[data-billing-access]')).toHaveText('FREE');
  await expect(page.locator('[data-billing-request]')).toHaveCount(0);
  expect(state.withdrawals).toHaveLength(1);
});

for (const failure of ['503', 'false-ack', 'network', 'invalid-json']) {
  test(`refund ${failure} never displays success and remains retryable`, async ({ page }) => {
    const state = await setup(page, { data: billing('core', [purchase()]) });
    if (failure === '503') state.withdrawStatus = 503;
    if (failure === 'false-ack') state.result = { ok: false };
    if (failure === 'network') state.networkFailure = true;
    if (failure === 'invalid-json') state.result = 'not an acknowledgement';
    await page.locator('[data-billing-request]').click();
    await expect(page.locator('#billing-status')).toContainText('could not be confirmed');
    await expect(page.locator('[data-billing-request]')).toBeEnabled();
    await expect(page.locator('#billing-status')).not.toContainText('Refund confirmed');
    state.withdrawStatus = 200; state.result = { ok: true, refunded: false, access_revoked: false, waiver_applied: true }; state.networkFailure = false;
    await page.locator('[data-billing-request]').click();
    await expect(page.locator('#billing-status')).toContainText('Access continues until its recorded expiry');
    expect(state.withdrawals).toHaveLength(2);
  });
}

test('revocation ACK without refund confirmation stays explicitly unconfirmed', async ({ page }) => {
  const state = await setup(page, { data: billing('core', [purchase()]) });
  state.result = { ok: true, refunded: false, access_revoked: true };
  state.after = billing('free', [purchase({ state: 'refund_pending', refund_status: 'pending', can_request_refund: false })], 'revoked');
  await page.locator('[data-billing-request]').click();
  await expect(page.locator('#billing-status')).toContainText('refund is not yet confirmed');
  await expect(page.locator('[data-billing-refund]')).toHaveText('Awaiting confirmation');
});

test('BG refund copy distinguishes failed, pending and confirmed acknowledgements', async ({ page }) => {
  const state = await setup(page, { language: 'bg', data: billing('core', [purchase()]) });
  state.withdrawStatus = 503;
  await page.locator('[data-billing-request]').click();
  await expect(page.locator('#billing-status')).toContainText('не можа да бъде потвърден');
  state.withdrawStatus = 200; state.result = { ok: true, refunded: false, access_revoked: true };
  await page.locator('[data-billing-request]').click();
  await expect(page.locator('#billing-status')).toContainText('още не е потвърдено');
  state.result = { ok: true, refunded: true, access_revoked: true };
  state.after = billing('free', [purchase({ state: 'refunded', can_request_refund: false })], 'revoked');
  await page.locator('[data-billing-request]').click();
  await expect(page.locator('#billing-status')).toContainText('Възстановяването е потвърдено.');
});

test('late account A billing and refund responses cannot reach account B', async ({ page }) => {
  const state = await setup(page, { data: billing('core', [purchase({ amount_cents: 9876 })]) });
  state.hold = deferred();
  await page.locator('[data-billing-request]').click();
  await expect.poll(() => state.withdrawals.length).toBe(1);
  state.readHold = deferred();
  await page.evaluate(() => { window.oldBillingRead = showSubscription(); });
  await expect.poll(() => state.reads).toBe(2);
  await page.evaluate(() => logout());
  state.current = 'b'; state.data = billing(); const oldRead = state.readHold; state.readHold = null;
  await page.evaluate(() => loadSession(null));
  await page.evaluate(() => showSubscription());
  state.hold.release(); oldRead.release(); await page.evaluate(() => window.oldBillingRead);
  await expect(page.locator('[data-billing-access]')).toHaveText('FREE');
  await expect(page.locator('[data-billing-purchase]')).toHaveCount(0);
  await expect(page.locator('#billing-status')).toBeEmpty();
});

for (const language of ['bg', 'en']) for (const width of [1440, 390, 360]) {
  test(`${language} billing ${width}px: wrapping, touch targets and keyboard dialog`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 1440 ? 900 : width === 390 ? 844 : 800 });
    await setup(page, { language, data: billing('core', [purchase({ state: 'refund_pending', refund_status: 'unconfirmed', can_request_refund: false })], 'grace') });
    const summary = page.locator('.billing-tiers summary'); await summary.click();
    expect(await page.locator('#billing-surface').evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(await summary.evaluate(el => el.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    await page.locator('#panel-modal .sheet').evaluate(el => { el.scrollTop = 0; });
    await page.screenshot({ path: path.join(__dirname, '../../test-results', `billing-${language}-${width}.png`), fullPage: true });
    await page.keyboard.press('Escape'); await expect(page.locator('#panel-modal')).not.toHaveClass(/\bon\b/);
    await page.keyboard.press('Tab');
    expect(await page.evaluate(() => document.activeElement !== document.body)).toBe(true);
  });
}

for (const url of ['/', '/en']) {
  test(`${url} pricing describes existing tiers without unsupported benefits`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(url); const pricing = page.locator('#pricing');
    await page.locator('.cb-decline').click();
    await expect(pricing).toContainText('€9.99'); await expect(pricing).toContainText('€14.99');
    await expect(pricing).not.toContainText(/PDF|6×|priority support|неограничен достъп|unlimited access/);
    await expect(pricing.locator('[data-paid-unavailable]')).toHaveCount(2);
    for (const width of [1440, 390, 360]) {
      await page.setViewportSize({ width, height: width === 1440 ? 900 : 844 });
      await pricing.scrollIntoViewIfNeeded();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: path.join(__dirname, '../../test-results', `pricing-${url === '/' ? 'bg' : 'en'}-${width}.png`) });
    }
  });
}

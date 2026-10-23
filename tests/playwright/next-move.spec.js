const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test.use({ baseURL: process.env.NEXT_MOVE_BASE_URL || 'http://127.0.0.1:5005' });
const shots = process.env.NEXT_MOVE_SCREENSHOTS || 'C:/tmp/apex-next-move';
function recommendation(language, extra = {}) {
  const bg = language === 'bg';
  return { decision_id: 'synthetic-evidence-fingerprint', kind: 'checkin',
    title: bg ? 'Как се чувстваш възстановен днес?' : 'How recovered do you feel today?',
    why: bg ? 'Запазеният профил не е нова оценка на възстановяването ти днес.' : 'Your saved profile is not a fresh recovery check-in.',
    action_label: bg ? 'Отговори за днес' : "Answer today's check-in",
    known: { goal: 'strength', level: 'intermediate', equipment: 'home' },
    completed_at: null, constraints: ['vertical_push'], ...extra };
}
async function mount(page, language = 'en', configure = () => {}) {
  const state = { reads: 0, approvals: 0, chats: 0, saves: 0, failure: false, stale: false,
    current: recommendation(language), workflow: { workflow: 'checkin' } };
  configure(state);
  await page.route('**/api/next-move?*', async route => {
    state.reads++;
    if (state.hold) await state.hold;
    await route.fulfill({ status: state.failure ? 503 : 200,
      json: state.failure ? { error: 'next_move_unavailable' } : { recommendation: state.current } });
  });
  await page.route('**/api/next-move/approve?*', route => {
    state.approvals++;
    return route.fulfill({ status: state.stale ? 409 : 200, json: state.stale ?
      { error: 'next_move_changed', recommendation: recommendation(language, { title: 'UPDATED SAFE NEXT STEP' }) } : state.workflow });
  });
  await page.route('**/api/next-move/check-in?*', route => {
    state.saves++; state.savedBody = route.request().postDataJSON();
    return route.fulfill({ status: state.saveFailure ? 503 : 200,
      json: state.saveFailure ? { error: 'next_move_unavailable' } : { recommendation: recommendation(language,
        { kind: 'recovery', title: language === 'bg' ? 'Постави възстановяването пред още натоварване.' : 'Put recovery before more training.',
          action_label: language === 'bg' ? 'Обсъди възстановяването' : 'Discuss recovery' }) } });
  });
  page.on('request', request => { if (new URL(request.url()).pathname === '/chat') state.chats++; });
  await page.goto('/app?lang=' + language);
  await expect.poll(() => page.evaluate(() => DATA_OWNER.kind)).toBe('account');
  await expect(page.locator('#read-state')).toHaveText(state.current.title);
  return state;
}

for (const language of ['bg', 'en']) {
  for (const width of [390, 1440]) {
    test(`${language} ${width}: page-open next step, facts, approval and unclipped Core`, async ({ page }) => {
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      const state = await mount(page, language);
      await expect(page.locator('#brief-context')).toContainText(language === 'bg' ? 'Избягвай преси над глава' : 'Avoid overhead pressing');
      await expect(page.locator('#read-sub')).toHaveText(state.current.why);
      expect(state.chats).toBe(0); expect(state.approvals).toBe(0);
      await expect(page.locator('.cta:not(.ghost)')).toBeInViewport();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await expect.poll(() => page.evaluate(() => {
        const canvas = document.getElementById('core');
        return canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data.some(value => value > 0);
      })).toBe(true);
      await page.evaluate(() => document.fonts.ready);
      fs.mkdirSync(shots, { recursive: true });
      await page.screenshot({ path: path.join(shots, `${language}-${width}-overview.png`) });
      await page.locator('.cta:not(.ghost)').focus(); await page.keyboard.press('Enter');
      await expect(page.locator('#next-move-checkin')).toBeVisible();
      expect(state.approvals).toBe(1); expect(state.saves).toBe(0); expect(state.chats).toBe(0);
      await expect(page.locator('label[for="next-move-recovery"]')).toBeVisible();
      await page.locator('#next-move-recovery').selectOption('tired');
      await page.screenshot({ path: path.join(shots, `${language}-${width}-checkin.png`) });
      await page.locator('#next-move-checkin button').click();
      await expect(page.locator('#next-move-checkin')).not.toBeVisible();
      await expect(page.locator('#read-state')).toHaveText(language === 'bg' ? 'Постави възстановяването пред още натоварване.' : 'Put recovery before more training.');
      expect(state.savedBody).toEqual({ recovery: 'tired' }); expect(state.saves).toBe(1);
      expect(state.chats).toBe(0); expect(errors).toEqual([]);
    });
  }
}

test('check-in cancellation and failed ACK cannot claim a saved update', async ({ page }) => {
  const state = await mount(page);
  await page.locator('.cta:not(.ghost)').click();
  await page.locator('#next-move-recovery').selectOption('tired');
  await page.evaluate(() => closePanel()); expect(state.saves).toBe(0);
  await page.locator('.cta:not(.ghost)').click(); state.saveFailure = true;
  await page.locator('#next-move-recovery').selectOption('tired');
  await page.locator('#next-move-checkin button').click();
  await expect(page.locator('#next-move-status')).toContainText('not confirmed');
  await expect(page.locator('#read-state')).toHaveText(state.current.title);
  expect(state.saves).toBe(1); expect(state.chats).toBe(0);
});

test('stale recommendation requires another approval; unavailable context cannot execute', async ({ page }) => {
  const state = await mount(page); state.stale = true;
  await page.locator('.cta:not(.ghost)').click();
  await expect(page.locator('#read-state')).toHaveText('UPDATED SAFE NEXT STEP');
  expect(state.chats).toBe(0); await expect(page.locator('#next-move-checkin')).not.toBeVisible();
  state.failure = true; await page.evaluate(() => ApexNextMove.refresh());
  await expect(page.locator('#read-state')).toContainText("can't verify");
  await page.locator('.cta:not(.ghost)').click();
  await expect.poll(() => state.reads).toBe(3); expect(state.approvals).toBe(1);
  await page.locator('.cta.ghost').click(); await expect(page.locator('#user-in')).toBeVisible();
});

test('approved workflow alone can enter chat; recording completion refreshes evidence', async ({ page }) => {
  const state = await mount(page, 'en', value => { value.workflow = { workflow: 'chat', message: 'Discuss recovery using my saved constraints.' }; });
  await page.locator('.cta:not(.ghost)').click();
  await expect.poll(() => state.chats).toBe(1);
  await expect(page.locator('#feed')).toContainText('DEMO');
  await page.route('**/api/workout', route => route.fulfill({ json: { ok: true, id: 'synthetic-completion' } }));
  const before = state.reads;
  state.current = recommendation('en', { kind: 'post_workout', title: 'Check in after your recorded workout.', completed_at: '2026-10-23T08:00:00Z' });
  await page.evaluate(() => accountLogWorkout({ completion: 100 }));
  await expect.poll(() => state.reads).toBe(before + 1);
  await expect(page.locator('#read-state')).toHaveText(state.current.title);
});

test('late account response is discarded after logout', async ({ page }) => {
  const state = await mount(page); let release;
  state.hold = new Promise(resolve => { release = resolve; });
  state.current = recommendation('en', { title: 'ACCOUNT_A_PRIVATE_NEXT_MOVE' });
  const before = state.reads;
  await page.evaluate(() => { window.pendingMove = ApexNextMove.refresh(); });
  await expect.poll(() => state.reads).toBe(before + 1);
  await page.route('**/auth/logout', route => route.fulfill({ json: { ok: true } }));
  await page.evaluate(() => logout()); release();
  await page.evaluate(() => window.pendingMove);
  expect(await page.evaluate(() => SESSION.authenticated)).toBe(false);
  await expect(page.locator('#read-state')).not.toContainText('ACCOUNT_A_PRIVATE');
  expect(state.chats).toBe(0);
});

test('normal account language switch refreshes the localized recommendation', async ({ page }) => {
  const state = await mount(page);
  state.current = recommendation('bg');
  await page.evaluate(() => selectAppLanguage('bg'));
  await expect(page.locator('#read-state')).toHaveText(state.current.title);
  await page.reload(); await expect(page.locator('#read-state')).toHaveText(state.current.title);
  expect(state.chats).toBe(0);
});

test('language save failure cannot strand the next step in another language', async ({ page }) => {
  const state = await mount(page);
  state.current = recommendation('bg');
  await page.route('**/api/profile', route => route.request().method() === 'PUT' ?
    route.fulfill({ status: 503, json: { error: 'profile_save_unavailable' } }) : route.continue());
  await page.evaluate(() => selectAppLanguage('bg'));
  await expect(page.locator('#read-state')).toHaveText(state.current.title);
  await expect(page.locator('.cta:not(.ghost)')).toBeEnabled();
  expect(state.chats).toBe(0);
});

test('anonymous app retains onboarding and never requests account recommendations', async ({ page }) => {
  let reads = 0;
  await page.route('**/auth/me', route => route.fulfill({ json: { authenticated: false, plan: 'free' } }));
  page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/next-move')) reads++; });
  await page.goto('/app?lang=en');
  await page.evaluate(() => loadSession());
  expect(await page.evaluate(() => SESSION.authenticated)).toBe(false);
  expect(reads).toBe(0);
  await expect(page.locator('#read-state')).not.toContainText('How recovered');
});

test('real local endpoint: explicit check-in persists and recalculates without chat', async ({ page }) => {
  let chats = 0;
  page.on('request', request => { if (new URL(request.url()).pathname === '/chat') chats++; });
  await page.goto('/app?lang=en');
  const read = await page.request.get('/api/next-move?lang=en');
  expect(read.status()).toBe(200);
  const current = (await read.json()).recommendation;
  await expect(page.locator('#read-state')).toHaveText(current.title);
  const approved = await page.request.post('/api/next-move/approve?lang=en', { data: { decision_id: current.decision_id } });
  expect(approved.status()).toBe(200);
  const saved = await page.request.post('/api/next-move/check-in?lang=en', { data: { recovery: 'tired' } });
  expect(saved.status()).toBe(200);
  await page.evaluate(() => ApexNextMove.refresh());
  await expect(page.locator('#read-state')).toHaveText('Put recovery before more training.');
  await page.reload();
  await expect(page.locator('#read-state')).toHaveText('Put recovery before more training.');
  await expect(page.locator('#brief-context')).toContainText('Avoid overhead pressing');
  expect(chats).toBe(0);
});

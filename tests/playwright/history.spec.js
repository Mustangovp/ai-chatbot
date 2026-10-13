const { test, expect } = require('@playwright/test');

const profile = { goal: 'strength', level: 'beginner', equip: 'home', age: '30', height: '178', weight: '75', gender: 'male' };
const ids = ['dumbbell.goblet_squat', 'dumbbell.floor_press', 'bodyweight.table_row', 'bodyweight.glute_bridge', 'bodyweight.plank', 'bodyweight.march_in_place'];
const session = (state = 'completed') => ({
  id: 'saved-session', occurred_at: '2026-10-11T10:00:00Z', type: 'Lower body', execution_state: state,
  completion_evidence: { workout_id: 'observed-workout' },
  exercises: ids.map((id, index) => ({ exercise_id: id, exercise_version: '1.0.0', name: 'Original exercise name',
    completed_sets: 2, actual_repetitions: index === 4 ? null : 10, execution_state: state,
    ...(index === 4 ? { prescription_type: 'duration', actual_duration_seconds: 30 } : {}),
    completed_load: index < 2 ? 8 : null, completed_rpe: 7, completed_rir: 2, completed_effort: 'productive',
    sets: 99, reps: '99-100', weight: 999 }))
});
const local = row => ({ ...row, ts: Date.parse(row.occurred_at), execution_schema: 'workout-execution-v1',
  workout_id: row.completion_evidence.workout_id, serverId: undefined });

async function setup(page, { language = 'en', authenticated = true, rows = [] } = {}) {
  const calls = { chat: 0, reads: 0 };
  let history = rows;
  page.on('request', request => { if (new URL(request.url()).pathname === '/chat') calls.chat++; });
  await page.route('**/auth/me', route => route.fulfill({ json: { authenticated,
    ...(authenticated ? { email: 'local-history@example.com' } : {}), plan: 'free', status: 'free' } }));
  await page.route('**/api/profile', route => route.fulfill({ json: { profile: { ...profile, language }, training_constraint_records: [] } }));
  await page.route('**/api/history', route => { calls.reads++; return route.fulfill({ json: { workouts: history, nutrition: [], timeline: [] } }); });
  await page.route('**/api/conversations?*', route => route.fulfill({ json: { messages: [] } }));
  await page.route('**/api/athlete-model', route => route.fulfill({ json: {} }));
  await page.route('**/api/my-training', route => route.fulfill({ json: { latest_workout: null, last_completed: null, active_constraints: [] } }));
  await page.goto('/app?lang=' + language);
  await expect.poll(() => page.evaluate(() => SESSION.authenticated)).toBe(authenticated);
  if (authenticated) await expect.poll(() => page.evaluate(() => DATA_OWNER.kind)).toBe('account');
  if (authenticated) await expect.poll(() => page.evaluate(() => historyCache().length)).toBe(rows.length);
  return { calls, setRows: value => { history = value; } };
}
async function openHistory(page, language = 'en') {
  await page.locator('#menu-btn').click();
  await page.locator('#drawer').getByText(language === 'bg' ? 'История' : 'History', { exact: true }).click();
  await expect(page.locator('#training-history')).toHaveAttribute('aria-busy', 'false');
}

for (const language of ['bg', 'en']) {
  test(`History renders observed 12 sets and typed work, not the prescription, in ${language}`, async ({ page }) => {
    const { calls } = await setup(page, { language, rows: [session()] });
    await openHistory(page, language);
    const root = page.locator('#training-history');
    await expect(root.locator('summary')).toContainText(language === 'bg' ? 'Записани серии: 12' : 'Recorded sets: 12');
    await expect(root).not.toContainText(/99-100|999|0 sets|0 серии/);
    await expect(root.locator('[data-history-save]')).toHaveText(language === 'bg' ? 'Запазено в акаунта' : 'Saved to account');
    await root.locator('summary').click();
    await expect(root.locator('h4').first()).toHaveText(language === 'bg' ? 'Гоблет клек' : 'Goblet Squat');
    const facts = root.locator('[data-history-execution]');
    await expect(facts.nth(0)).toContainText('10 ' + (language === 'bg' ? 'повт.' : 'reps'));
    await expect(facts.nth(0)).toContainText('8 ' + (language === 'bg' ? 'кг' : 'kg'));
    await expect(facts.nth(4)).toContainText('30 ' + (language === 'bg' ? 'сек' : 'sec'));
    await expect(facts.nth(4)).not.toContainText(/reps|повт\./);
    await expect(facts.nth(4)).not.toContainText(/0 kg|0 кг/);
    await expect(root.locator('[data-history-feedback]').first()).toContainText(language === 'bg' ? 'Твоя самооценка' : 'Your self-reported feedback');
    await expect(root).not.toContainText(/next time|при следващо изпълнение|score|readiness|\d+%/i);
    await root.locator('#history-training').click();
    await expect(page.locator('#my-training')).toBeVisible();
    expect(calls.chat).toBe(0);
  });

  test(`History uses existing execution states in ${language}`, async ({ page }) => {
    const states = ['completed', 'partial', 'abandoned', 'skipped', 'unknown'];
    await setup(page, { language, rows: states.map((state, index) => ({ ...session(state), id: 'saved-' + index,
      completion_evidence: { workout_id: 'observed-' + index } })) });
    await openHistory(page, language);
    for (const state of states) {
      await expect(page.locator(`[data-history-state="${state}"] .hist-state`)).toHaveText({
        bg: { completed: 'Завършена', partial: 'Частично завършена', abandoned: 'Прекъсната', skipped: 'Пропусната', unknown: 'Статусът не е потвърден' },
        en: { completed: 'Completed', partial: 'Partially completed', abandoned: 'Interrupted', skipped: 'Skipped', unknown: 'Status not confirmed' }
      }[language][state]);
    }
  });

  test(`legacy prescribed values never replace missing execution in ${language}`, async ({ page }) => {
    await setup(page, { language, rows: [{ id: 'legacy', occurred_at: '2026-10-01T10:00:00Z', type: 'Original legacy title',
      completion: 100, exercises: [{ name: 'Original legacy movement', sets: 12, reps: '20-30', weight: 50, completed_repetitions: 30 }] }] });
    await openHistory(page, language);
    const row = page.locator('[data-history-state="unknown"]');
    await row.locator('summary').click();
    await expect(row).toContainText('Original legacy title');
    await expect(row).toContainText('Original legacy movement');
    await expect(row).toContainText(language === 'bg' ? 'Повторенията или времето не са записани.' : 'Repetitions or time were not recorded.');
    await expect(row).not.toContainText(/20-30|50 kg|50 кг|Recorded sets: 12|Записани серии: 12/);
  });
}

test('fresh account History wins over stale cache and retains visibly unconfirmed local work', async ({ page }) => {
  const api = await setup(page);
  await page.evaluate(row => ownedStorageSet('apexWorkoutLog', JSON.stringify([
    { ...row, serverId: 'saved-session', exercises: row.exercises.map(ex => ({ ...ex, completed_sets: 15 })) },
    { ...row, workout_id: 'pending-workout', execution_state: 'partial' }
  ])), local(session()));
  api.setRows([session()]);
  const before = api.calls.reads;
  await openHistory(page);
  expect(api.calls.reads).toBe(before + 1);
  await expect(page.locator('[data-history-authority="account"] summary')).toContainText('Recorded sets: 12');
  await expect(page.locator('[data-history-authority="local"]')).toContainText('Local record · Not yet confirmed');
  expect(api.calls.chat).toBe(0);
  await page.keyboard.press('Escape');
  api.setRows([{ ...session(), exercises: session().exercises.map(ex => ({ ...ex, completed_sets: 1 })) }]);
  await openHistory(page);
  await expect(page.locator('[data-history-authority="account"] summary')).toContainText('Recorded sets: 6');
});

test('anonymous History is explicitly browser-local and never reads the account', async ({ page }) => {
  const api = await setup(page, { authenticated: false });
  await page.evaluate(row => ownedStorageSet('apexWorkoutLog', JSON.stringify([row])), local(session()));
  await openHistory(page);
  await expect(page.locator('[data-history-save]')).toHaveText('Local record · Only in this browser');
  expect(api.calls.reads).toBe(0);
});

for (const success of [true, false]) {
  test(`account acknowledgement ${success ? 'confirms' : 'does not confirm'} the local save`, async ({ page }) => {
    const api = await setup(page);
    let release;
    const wait = new Promise(resolve => { release = resolve; });
    await page.route('**/api/workout', async route => { await wait; await route.fulfill({ status: success ? 200 : 503,
      json: success ? { ok: true, id: 'saved-session' } : { error: 'unavailable' } }); });
    await page.evaluate(row => logWorkout(row), local(session()));
    await openHistory(page);
    await expect(page.locator('[data-history-save]')).toHaveText('Local record · Not yet confirmed');
    release();
    if (success) {
      await expect.poll(() => page.evaluate(() => historyCache()[0].serverId)).toBe('saved-session');
      api.setRows([session()]);
    }
    await page.keyboard.press('Escape');
    await openHistory(page);
    await expect(page.locator('.hist-item')).toHaveCount(1);
    await expect(page.locator('[data-history-save]')).toHaveText(success ? 'Saved to account' : 'Local record · Not yet confirmed');
  });
}

test('History read errors preserve an explicitly cached fallback rather than claiming empty account evidence', async ({ page }) => {
  await setup(page, { rows: [session()] });
  await page.route('**/api/history', route => route.fulfill({ status: 503, json: { error: 'unavailable' } }));
  await openHistory(page);
  await expect(page.locator('#training-history [role="status"]')).toHaveText('Account history is unavailable at the moment.');
  await expect(page.locator('[data-history-save]')).toHaveText('Saved to account · Cached record');
});

test('an account History response arriving after owner change is discarded', async ({ page }) => {
  await setup(page);
  let release;
  const wait = new Promise(resolve => { release = resolve; });
  await page.route('**/api/history', async route => { await wait; await route.fulfill({ json: { workouts: [session()] } }); });
  await page.locator('#menu-btn').click(); await page.locator('#drawer').getByText('History', { exact: true }).click();
  await expect(page.locator('#training-history')).toHaveAttribute('aria-busy', 'true');
  await page.evaluate(() => { SESSION.authenticated = false; rotateAnonymousOwner(); showHistory(); });
  release();
  await expect(page.locator('#training-history')).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('#training-history')).not.toContainText('Saved to account');
  await expect.poll(() => page.evaluate(() => historyCache().length)).toBe(0);
});

test('a late save acknowledgement cannot mark the next owner cache', async ({ page }) => {
  await setup(page);
  let release;
  const wait = new Promise(resolve => { release = resolve; });
  await page.route('**/api/workout', async route => { await wait; await route.fulfill({ json: { ok: true, id: 'previous-owner-record' } }); });
  await page.evaluate(row => {
    window.historyTestAcknowledged = false;
    const original = accountLogWorkout;
    accountLogWorkout = (...args) => { window.historyTestReceipt = original(...args); return window.historyTestReceipt; };
    logWorkout(row, null, () => { window.historyTestAcknowledged = true; });
  }, local(session()));
  await expect.poll(() => page.evaluate(() => historyCache().length)).toBe(1);
  await page.evaluate(() => { SESSION.authenticated = false; rotateAnonymousOwner(); });
  release();
  expect(await page.evaluate(() => window.historyTestReceipt)).toBe(false);
  expect(await page.evaluate(() => window.historyTestAcknowledged)).toBe(false);
  expect(await page.evaluate(() => historyCache())).toEqual([]);
});

test('shared dialog has initial focus, Tab containment, Escape and focus restoration', async ({ page }) => {
  await setup(page, { rows: [session()] }); await openHistory(page);
  const dialog = page.locator('#panel-modal');
  await expect(dialog).toHaveAttribute('role', 'dialog'); await expect(dialog).toHaveAttribute('aria-modal', 'true');
  await expect(dialog).toHaveAttribute('aria-labelledby', 'panel-title'); await expect(page.locator('#panel-title')).toBeFocused();
  await page.keyboard.press('Shift+Tab'); await expect(page.locator('#panel-close')).toBeFocused();
  await page.keyboard.press('Tab'); await expect(page.locator('.hist-item>summary')).toBeFocused();
  for (let index = 0; index < 8; index++) {
    await page.keyboard.press('Tab');
    expect(await page.evaluate(() => !!document.activeElement.closest('#panel-modal'))).toBe(true);
  }
  await page.keyboard.press('Escape'); await expect(dialog).not.toHaveClass(/\bon\b/);
  await expect(page.locator('#menu-btn')).toBeFocused();
  await page.evaluate(() => {
    const trigger = document.getElementById('status-pill'); trigger.focus(); showPanel('Test', '<p>Read-only fixture</p>');
  });
  await page.locator('#panel-close').click(); await expect(page.locator('#status-pill')).toBeFocused();
});

for (const language of ['bg', 'en']) for (const width of [1440, 390, 360]) {
  test(`History geometry and existing actions at ${width}px in ${language}`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 1440 ? 900 : width === 390 ? 844 : 800 });
    const row = session(); row.exercises[2] = { ...row.exercises[2], exercise_id: undefined,
      name: 'A very long original historical exercise name that must remain completely readable' };
    await setup(page, { language, rows: [row] }); await openHistory(page, language);
    await page.locator('.hist-item>summary').click();
    const sheet = page.locator('#panel-modal .sheet');
    expect(await sheet.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const item of await page.locator('.hist-exercises li').all())
      expect(await item.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    if (process.env.APEX_CONTINUITY_SCREENSHOTS) await page.screenshot({ path: require('path').join(process.env.APEX_CONTINUITY_SCREENSHOTS, `history-${language}-${width}.png`), animations: 'disabled' });
    await page.locator('#history-training').scrollIntoViewIfNeeded(); await expect(page.locator('#history-training')).toBeInViewport();
    await page.locator('#panel-close').scrollIntoViewIfNeeded(); await page.locator('#panel-close').click();
    await expect(page.locator('#panel-modal')).not.toHaveClass(/\bon\b/);
  });
}

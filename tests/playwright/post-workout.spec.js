const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const path = require('node:path');

const fixtures = JSON.parse(execFileSync(process.env.APEX_TEST_PYTHON || 'python',
  [path.join(__dirname, '../canonical_workout_fixture.py')], { encoding: 'utf8' }));
const ids = ['dumbbell.goblet_squat', 'dumbbell.floor_press', 'bodyweight.table_row',
  'bodyweight.glute_bridge', 'bodyweight.plank', 'bodyweight.march_in_place'];
const profile = { goal: 'strength', level: 'beginner', equip: 'home', age: '30',
  weight: '75', height: '178', gender: 'male' };
const adjustment = { exercise_id: ids[0], exercise_version: '1.0.0', decision_type: 'maintain',
  reason_code: 'effort_productive' };

async function mount(page, { language = 'en', authenticated = true, fail = false,
  deferred = false, decisions = [] } = {}) {
  const calls = { writes: [], chats: 0, reads: 0 };
  let release;
  page.on('request', request => { if (new URL(request.url()).pathname === '/chat') calls.chats++; });
  await page.route('**/auth/me', route => route.fulfill({ json: authenticated
    ? { authenticated: true, email: 'synthetic-receipt@example.invalid', plan: 'free', status: 'free' }
    : { authenticated: false, plan: 'free' } }));
  await page.route('**/api/profile', route => route.fulfill({ json: {
    profile: { ...profile, language }, training_constraint_records: [] } }));
  await page.route('**/api/history', route => route.fulfill({ json: { workouts: [] } }));
  await page.route('**/api/conversations?*', route => route.fulfill({ json: { messages: [] } }));
  await page.route('**/api/athlete-model', route => route.fulfill({ json: {} }));
  await page.route('**/api/my-training', route => {
    calls.reads++; return route.fulfill({ json: {
      latest_workout: null, last_completed: null, active_constraints: [] } });
  });
  await page.route('**/api/workout', async route => {
    const body = route.request().postDataJSON(); calls.writes.push(body);
    if (deferred) await new Promise(resolve => { release = resolve; });
    await route.fulfill({ status: fail ? 503 : 200, json: fail ? {} : {
      ok: true, adaptation: { workout_id: body.workout_completion.workout_id, decisions } } });
  });
  await page.goto('/app?lang=' + language);
  await expect.poll(() => page.evaluate(() => SESSION.authenticated)).toBe(authenticated);
  if (authenticated) await expect.poll(() => page.evaluate(() => DATA_OWNER.kind)).toBe('account');
  const items = ids.map((id, index) => ({
    ...fixtures.find(item => item.id === id).languages[language].metadata.sessions[0].exercises[0],
    prescription_id: 'receipt-' + index
  }));
  await page.evaluate(({ items, profile, language }) => {
    lang = language; ownedStorageSet('apexProfile', JSON.stringify(profile)); enterConsult('');
    document.getElementById('profile-modal').classList.remove('on');
    const session = { session_id: 'receipt-session', session_index: 1, exercises: items };
    pendingTrainingCompletion = { plan_id: 'receipt-plan', plan_version: 'training-plan-blueprint-v3', sessions: [session] };
    pendingCompletionSessions = [session];
    appendCoach().innerHTML = renderMarkdown(['| Exercise | Sets | Reps | Rest |', '| --- | --- | --- |',
      ...items.map(item => `| ${item.display_name} | ${item.prescribed_sets} | ${item.prescription_type === 'duration'
        ? item.duration_min_seconds + '-' + item.duration_max_seconds + ' sec' : item.rep_min + '-' + item.rep_max} | ${item.rest_seconds} |`)].join('\n'));
    startWorkout('receipt-session');
  }, { items, profile, language });
  return { calls, items, release: () => release(), source: await page.evaluate(() => JSON.stringify(pendingTrainingCompletion)) };
}

async function complete(page, feedback = true) {
  for (let exercise = 0; exercise < 6; exercise++) {
    for (let set = 0; set < 2; set++) {
      await page.locator('#wo-reps-in').fill(exercise === 4 ? '30' : exercise === 0 && set === 1 ? '9' : '10');
      if (exercise === 0) await page.locator('#wo-weight-in').fill('12');
      if (feedback) {
        await page.locator('#wo-effort-in').selectOption('productive');
        if (exercise === 0 && set === 0) {
          await page.locator('.wo-effort details > summary').click();
          await page.locator('#wo-rpe-in').selectOption('7'); await page.locator('#wo-rir-in').selectOption('3');
        }
      }
      await page.locator('button[onclick="completeSet()"]').click();
      if (exercise !== 5 || set !== 1) await page.locator('button[onclick="endRest()"]').click();
    }
  }
  await expect(page.locator('[data-workout-result="completed"]')).toBeVisible();
}

async function screenshot(page, testInfo, name) {
  await page.screenshot({ path: testInfo.outputPath(name + '.png'), animations: 'disabled' });
}

for (const language of ['bg', 'en']) {
  test(`pending, success and deterministic future decision are truthful in ${language}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const state = await mount(page, { language, deferred: true, decisions: [adjustment] });
    await complete(page);
    await expect.poll(() => state.calls.writes.length).toBe(1);
    const save = page.locator('[data-completion-save-status]');
    await expect(save).toContainText(language === 'bg' ? 'Записано локално. Запазване' : 'Recorded locally. Saving');
    await expect(save).toBeInViewport({ ratio: 1 });
    await expect(save).not.toContainText(language === 'bg' ? 'Запазено в профила' : 'Saved to your account');
    await expect(page.locator('.completion-adjustments')).toHaveCount(0);
    await screenshot(page, testInfo, 'save-pending-' + language);
    const summary = page.locator('.wo-receipt > summary');
    await summary.focus(); await page.keyboard.press('Enter');
    await expect(page.locator('.wo-receipt')).toHaveAttribute('open', '');
    await page.evaluate(() => {
      window.receiptLiveSave = document.querySelector('[data-completion-save-status]');
      window.receiptLiveAdjustment = document.querySelector('[data-completion-adjustment-status]');
      window.receiptAnnouncements = [];
      new MutationObserver(() => receiptAnnouncements.push(receiptLiveSave.textContent))
        .observe(receiptLiveSave, { childList: true, characterData: true, subtree: true });
    });
    state.release();
    await expect(save).toHaveText(language === 'bg' ? 'Запазено в профила ти.' : 'Saved to your account.');
    await expect(save).toHaveAttribute('role', 'status'); await expect(save).toHaveAttribute('aria-live', 'polite');
    await expect(page.locator('[data-completion-adjustment-status]')).toHaveAttribute('aria-atomic', 'true');
    expect(await page.evaluate(() => receiptLiveSave === document.querySelector('[data-completion-save-status]') &&
      receiptLiveAdjustment === document.querySelector('[data-completion-adjustment-status]'))).toBe(true);
    await expect.poll(() => page.evaluate(() => receiptAnnouncements.length)).toBeGreaterThan(0);
    await expect(summary).toBeFocused(); await expect(page.locator('.wo-receipt')).toHaveAttribute('open', '');
    const first = page.locator('.wo-recorded-list li').first();
    await expect(first.locator('[data-receipt-facts="observed"]')).toContainText('12 ' + (language === 'bg' ? 'кг' : 'kg'));
    await expect(first.locator('[data-receipt-facts="observed"]')).not.toContainText(/RPE|RIR/);
    await expect(first.locator('[data-receipt-facts="reported"]')).toContainText('RPE 7');
    await expect(first.locator('[data-receipt-facts="reported"]')).toContainText('RIR 3');
    await expect(page.locator('.wo-recorded-list li').nth(4).locator('[data-receipt-facts="observed"]')).toContainText('30 ' + (language === 'bg' ? 'сек' : 'sec'));
    const next = page.locator('[data-completion-section="adjustment"]');
    await expect(next).toContainText(language === 'bg' ? 'не AI импровизация' : 'not AI improvisation');
    await expect(next.locator('[data-adjustment-reason]')).toHaveText(language === 'bg'
      ? 'Записаното усещане е „точно както трябва“.' : 'Recorded effort was about right.');
    await expect(next).toContainText(language === 'bg' ? 'бъдеща съвместима тренировка' : 'future compatible workout');
    await expect(next).toContainText(language === 'bg' ? 'Завършената тренировка не се променя' : 'The completed workout is unchanged');
    await screenshot(page, testInfo, 'receipt-expanded-' + language);
    await summary.press('Enter');
    await screenshot(page, testInfo, 'save-success-adjustment-' + language);
    expect(state.calls.writes).toHaveLength(1); expect(state.calls.chats).toBe(0);
    expect(state.calls.writes[0].session).toMatchObject({ execution_state: 'completed', completion: 100 });
    expect(state.calls.writes[0].workout_completion.exercises[0]).toMatchObject({
      completed_sets: 2, completed_repetitions: 9, completed_load: 12, completed_rpe: 7, completed_rir: 3 });
    expect(await page.evaluate(() => JSON.stringify(pendingTrainingCompletion))).toBe(state.source);
  });

  test(`save failure and missing optional feedback remain usable in ${language}`, async ({ page }) => {
    const state = await mount(page, { language, fail: true }); await complete(page, false);
    const save = page.locator('[data-completion-save-status]');
    await expect(save).toContainText(language === 'bg' ? 'Записът в профила не е потвърден' : 'Account save has not been confirmed');
    await expect(save).not.toContainText(language === 'bg' ? 'Запазено в профила' : 'Saved to your account');
    await expect(page.locator('.wo-feedback-missing')).toContainText(language === 'bg' ? 'не е задължителна' : 'not required');
    await page.locator('.wo-receipt > summary').click();
    await expect(page.locator('[data-receipt-facts="reported"]').first()).toContainText(language === 'bg'
      ? 'Не е записана допълнителна самооценка' : 'No optional feedback was recorded');
    await expect(page.locator('.wo-recorded-list')).not.toContainText(/RPE 0|RIR 0|0 kg|0 кг/);
    await expect(page.locator('.completion-adjustments')).toHaveCount(0);
    const evidence = state.calls.writes[0].workout_completion.exercises;
    expect(evidence.every(item => item.completed_effort === null && item.completed_rpe === null && item.completed_rir === null)).toBe(true);
    await page.getByRole('button', { name: language === 'bg' ? 'Към треньора' : 'Back to coach', exact: true }).click();
    await expect(page.locator('#user-in')).toBeFocused(); expect(state.calls.chats).toBe(0);
  });

  for (const width of [1440, 390, 360]) {
    test(`six-exercise receipt is compact and accessible in ${language} at ${width}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width === 1440 ? 900 : width === 390 ? 844 : 800 });
      const state = await mount(page, { language }); await complete(page);
      await expect(page.locator('[data-completion-save-status]')).toHaveText(language === 'bg' ? 'Запазено в профила ти.' : 'Saved to your account.');
      await expect(page.locator('.wo-summary h2')).toBeInViewport({ ratio: 1 });
      await expect(page.locator('[data-completion-save-status]')).toBeInViewport({ ratio: 1 });
      const primary = page.getByRole('button', { name: language === 'bg' ? 'Към Моите тренировки' : 'Go to My Training', exact: true });
      await expect(primary).toHaveClass(/primary/); await expect(primary).toBeInViewport({ ratio: 1 });
      const summary = page.locator('.wo-receipt > summary');
      await expect(page.locator('.wo-receipt')).not.toHaveAttribute('open', '');
      await expect(page.locator('.wo-recorded-list')).toBeHidden();
      await expect(page.locator('.wo-summary')).not.toContainText(/APEX recorded|APEX отчете/);
      await expect(page.locator('[data-completion-section="adjustment"]')).toContainText(language === 'bg'
        ? 'Няма потвърдена тренировъчна корекция' : 'No training adjustment has been confirmed');
      for (const element of [summary, primary]) expect((await element.boundingBox()).height).toBeGreaterThanOrEqual(48);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth &&
        document.getElementById('wo-stage').scrollWidth <= document.getElementById('wo-stage').clientWidth)).toBe(true);
      await screenshot(page, testInfo, `completion-${language}-${width}`);
      await summary.focus(); await summary.press('Space');
      await expect(page.locator('.wo-recorded-list li')).toHaveCount(6);
      await expect(page.locator('.wo-recorded-list')).toBeVisible();
      await expect(page.locator('[data-completion-section="recorded"]')).toContainText(language === 'bg' ? 'минимумът' : 'minimum');
      await expect(page.locator('[data-receipt-facts="observed"]')).toHaveCount(6);
      await expect(page.locator('[data-receipt-facts="reported"]')).toHaveCount(6);
      await summary.press('Space'); await expect(page.locator('.wo-recorded-list')).toBeHidden();
      await primary.click(); await expect(page.locator('#my-training')).toBeVisible();
      expect(state.calls.reads).toBe(1); expect(state.calls.chats).toBe(0); expect(state.calls.writes).toHaveLength(1);
    });
  }
}

test('anonymous receipt claims browser storage only and unknown reason cannot become an explanation', async ({ page }) => {
  const state = await mount(page, { authenticated: false }); await complete(page, false);
  await expect(page.locator('[data-completion-save-status]')).toHaveText('Recorded in this browser only, not to an account.');
  await expect(page.locator('.completion-adjustments')).toHaveCount(0); expect(state.calls.writes).toHaveLength(0);
  const before = await page.evaluate(() => JSON.stringify(lastWorkoutSummary));
  await page.evaluate(decision => renderWorkoutResult(lastWorkoutSummary, 12, 'saved', [decision]),
    { ...adjustment, reason_code: 'PRIVATE_REASON', reason: 'private policy text' });
  await expect(page.locator('[data-adjustment-reason]')).toHaveCount(0);
  await expect(page.locator('.wo-summary')).not.toContainText(/PRIVATE|private policy text|effort_productive/);
  expect(await page.evaluate(() => JSON.stringify(lastWorkoutSummary))).toBe(before);
  expect(state.calls.chats).toBe(0);
});

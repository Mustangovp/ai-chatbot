const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const path = require('node:path');

const fixtures = JSON.parse(execFileSync(process.env.APEX_TEST_PYTHON || 'python',
  [path.join(__dirname, '../canonical_workout_fixture.py')], { encoding: 'utf8' }));
const ids = ['dumbbell.goblet_squat', 'dumbbell.floor_press', 'bodyweight.table_row',
  'bodyweight.glute_bridge', 'bodyweight.plank', 'bodyweight.march_in_place'];
const profile = { goal: 'strength', level: 'beginner', equip: 'home', age: '30',
  weight: '75', height: '178', gender: 'male' };

async function mount(page, language = 'en', deferSave = false) {
  const writes = [];
  let releaseSave;
  await page.route('**/auth/me', route => route.fulfill({ json: {
    authenticated: true, email: 'synthetic-session@example.invalid', plan: 'free', status: 'free' } }));
  await page.route('**/api/profile', route => route.fulfill({ json: {
    profile: { ...profile, language }, training_constraint_records: [] } }));
  await page.route('**/api/history', route => route.fulfill({ json: { workouts: [] } }));
  await page.route('**/api/conversations?*', route => route.fulfill({ json: { messages: [] } }));
  await page.route('**/api/athlete-model', route => route.fulfill({ json: {} }));
  await page.route('**/api/workout', async route => {
    const body = route.request().postDataJSON(); writes.push(body);
    if (deferSave) await new Promise(resolve => { releaseSave = resolve; });
    await route.fulfill({ json: { ok: true, adaptation: {
      workout_id: body.workout_completion.workout_id, decisions: [] } } });
  });
  await page.goto('/app?lang=' + language);
  await expect.poll(() => page.evaluate(() => SESSION.authenticated && DATA_OWNER.kind === 'account')).toBe(true);
  const items = ids.map((id, index) => ({
    ...fixtures.find(item => item.id === id).languages[language].metadata.sessions[0].exercises[0],
    prescription_id: 'active-' + index
  }));
  await page.evaluate(({ items, language, profile }) => {
    lang = language; ownedStorageSet('apexProfile', JSON.stringify(profile));
    enterConsult(''); document.getElementById('profile-modal').classList.remove('on');
    const session = { session_id: 'active-session', session_index: 1, exercises: items };
    pendingTrainingCompletion = { plan_id: 'active-plan', plan_version: 'training-plan-blueprint-v3', sessions: [session] };
    pendingCompletionSessions = [session];
    const rows = items.map(item => `| ${item.display_name} | ${item.prescribed_sets} | ${item.prescription_type === 'duration'
      ? item.duration_min_seconds + '-' + item.duration_max_seconds + ' sec' : item.rep_min + '-' + item.rep_max} | ${item.rest_seconds} | RPE 6, RIR 4; tempo 2-1-2-0 |`);
    appendCoach().innerHTML = renderMarkdown(['| Exercise | Sets | Reps | Rest | Note |', '| --- | --- | --- | --- |', ...rows].join('\n'));
    hardScroll();
  }, { items, language, profile });
  const source = await page.evaluate(() => JSON.stringify(pendingTrainingCompletion));
  await page.locator('.start-wo').click();
  await expect(page.locator('#wo-current-step')).toBeFocused();
  const names = await page.evaluate(() => WO.ex.map(item => item.name));
  return { items, names, source, writes, release: () => releaseSave() };
}

async function snapshot(page, testInfo, name) {
  const image = page.locator('#workout .exercise-visual img');
  if (await image.count()) await expect.poll(() => image.evaluate(item => item.complete && item.naturalWidth > 0)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath(name + '.png'), animations: 'disabled' });
}

async function complete(page, onWork = async () => {}, onRest = async () => {}) {
  for (let exercise = 0; exercise < 6; exercise++) {
    for (let set = 0; set < 2; set++) {
      await onWork(exercise, set);
      const duration = await page.evaluate(() => WO.ex[WO.i].completion.prescription_type === 'duration');
      await page.locator('#wo-reps-in').fill(duration ? '30' : exercise === 0 && set === 1 ? '9' : '10');
      if (exercise === 0) await page.locator('#wo-weight-in').fill('12');
      await page.locator('#wo-effort-in').selectOption('productive');
      await page.locator('button[onclick="completeSet()"]').click();
      await expect(page.locator('#wo-current-step')).toBeFocused();
      if (exercise !== 5 || set !== 1) {
        await onRest(exercise, set);
        await page.getByRole('button', { name: /Skip rest|Пропусни почивката/ }).click();
      }
    }
  }
}

for (const language of ['bg', 'en']) {
  for (const width of [1440, 390, 360]) {
    test(`six exercises and twelve sets stay explicit in ${language} at ${width}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width === 1440 ? 900 : width === 390 ? 844 : 800 });
      const state = await mount(page, language);
      await expect(page.getByRole('dialog')).toHaveAttribute('aria-modal', 'true');
      await expect(page.getByRole('button', { name: /Skip exercise|Пропусни упражнението/ })).toBeVisible();
      await expect(page.getByRole('spinbutton', { name: /Actual reps|Реални повторения/ })).toHaveValue('');
      await expect(page.getByRole('spinbutton', { name: /Actual load|Реална тежест/ })).toHaveValue('');
      await expect(page.getByRole('combobox', { name: /Exercise effort|Усещане за упражнението/ })).toHaveValue('');
      await expect(page.locator('#wo-actual-note')).toContainText(language === 'bg' ? 'неизвестно' : 'unknown');
      await expect(page.locator('#wo-effort-scope')).toContainText(language === 'bg' ? 'между сериите' : 'across sets');
      await expect(page.locator('.wo-ex-target')).toContainText(language === 'bg' ? 'Предписано:' : 'Prescribed:');
      await expect(page.locator('button[onclick="completeSet()"]')).toBeInViewport();
      await snapshot(page, testInfo, `active-${language}-${width}`);
      await page.locator('.wo-technique > summary').click();
      await page.locator('.wo-technique .workout-deep-guidance > summary').click();
      await page.locator('.wo-effort details > summary').click();
      await page.locator('#wo-rpe-in').selectOption('7');
      await page.locator('#wo-rir-in').selectOption('3');
      await complete(page, async (exercise, set) => {
        await expect(page.locator('#wo-reps-in')).toHaveValue('');
        await expect(page.locator('#workout .exercise-visual')).toHaveAttribute('data-exercise-visual-id', ids[exercise]);
        if (exercise === 0 && set === 1) {
          await expect(page.locator('.wo-technique')).toHaveAttribute('open', '');
          await expect(page.locator('.wo-technique .workout-deep-guidance')).toHaveAttribute('open', '');
          await expect(page.locator('.wo-effort details')).toHaveAttribute('open', '');
          await expect(page.locator('#wo-rpe-in')).toHaveValue('7');
          await expect(page.locator('#wo-rir-in')).toHaveValue('3');
        }
        if (exercise === 4) await expect(page.getByRole('spinbutton', { name: /Actual time|Реално време/ })).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth &&
          document.getElementById('wo-stage').scrollWidth <= document.getElementById('wo-stage').clientWidth)).toBe(true);
      }, async (exercise, set) => {
        const rest = page.locator('.wo-rest-context');
        await expect(rest.first()).toContainText((set + 1) + '/2');
        await expect(rest.first()).toContainText(state.names[exercise]);
        await expect(rest.nth(1)).toContainText(language === 'bg'
          ? set === 0 ? 'Следваща серия:' : 'Следващо упражнение:' : set === 0 ? 'Next set:' : 'Next exercise:');
        await expect(rest.nth(1)).toContainText(state.names[set === 0 ? exercise : exercise + 1]);
        await expect(page.getByRole('timer', { name: /Remaining rest|Оставаща почивка/ })).toBeVisible();
        if (exercise === 0 && set === 0) await snapshot(page, testInfo, `rest-${language}-${width}`);
      });
      await expect(page.locator('[data-workout-result="completed"]')).toBeVisible();
      await expect(page.locator('[data-completion-section="adjustment"]')).toContainText(language === 'bg'
        ? 'Няма потвърдена тренировъчна корекция' : 'No training adjustment');
      await expect(page.locator('.wo-summary h2')).toBeInViewport({ ratio: 1 });
      const geometry = await page.locator('.wo-summary h2').evaluate(item => ({
        top: item.getBoundingClientRect().top, stageTop: item.closest('.wo-stage').getBoundingClientRect().top }));
      expect(geometry.top).toBeGreaterThanOrEqual(geometry.stageTop);
      await expect(page.locator('[data-completion-section="recorded"]')).toContainText(language === 'bg'
        ? 'минимумът' : 'minimum across confirmed sets');
      expect(state.writes).toHaveLength(1);
      expect(state.writes[0].session).toMatchObject({ execution_state: 'completed', completion: 100 });
      const evidence = state.writes[0].workout_completion.exercises;
      expect(evidence).toHaveLength(6);
      expect(evidence[0]).toMatchObject({ completed_sets: 2, completed_repetitions: 9,
        completed_load: 12, completed_rpe: 7, completed_rir: 3 });
      expect(evidence[4]).toMatchObject({ prescription_type: 'duration', completed_sets: 2,
        completed_repetitions: null, completed_duration_seconds: 30 });
      expect(await page.evaluate(() => JSON.stringify(pendingTrainingCompletion))).toBe(state.source);
      await snapshot(page, testInfo, `completion-${language}-${width}`);
      await page.getByRole('button', { name: /Back to coach|Към треньора/ }).click();
      await expect(page.locator('#user-in')).toBeFocused();
    });
  }
}

test('keyboard is contained in work, rest and completion and returns to start on exit', async ({ page }) => {
  await mount(page);
  const last = page.locator('.wo-technique > summary');
  await last.focus(); await page.keyboard.press('Tab');
  await expect(page.locator('#wo-quit-btn')).toBeFocused();
  await page.keyboard.press('Shift+Tab'); await expect(last).toBeFocused();
  await page.evaluate(() => document.getElementById('user-in').focus());
  await expect(page.locator('#wo-current-step')).toBeFocused();
  await page.keyboard.press('Escape'); await expect(page.locator('#workout')).toHaveClass(/on/);
  await page.locator('#wo-reps-in').fill('10');
  await page.locator('button[onclick="completeSet()"]').press('Enter');
  await expect(page.locator('#wo-current-step')).toBeFocused();
  await page.getByRole('button', { name: /Skip rest/ }).focus(); await page.keyboard.press('Tab');
  await expect(page.locator('#wo-quit-btn')).toBeFocused();
  await page.keyboard.press('Shift+Tab'); await expect(page.getByRole('button', { name: /Skip rest/ })).toBeFocused();
  await page.locator('#wo-quit-btn').click(); await expect(page.locator('.start-wo')).toBeFocused();
});

test('skip behavior is unchanged and blank completed-set data remains unknown, not zero', async ({ page }) => {
  const state = await mount(page);
  await page.getByRole('button', { name: /Skip exercise/ }).click();
  expect(await page.evaluate(() => ({ index: WO.i, phase: WO.phase, skipped: WO.ex[0].skipped,
    sets: WO.ex[0].completedSets }))).toEqual({ index: 1, phase: 'work', skipped: true, sets: 0 });
  await page.locator('#wo-quit-btn').click(); await page.locator('.start-wo').click();
  for (let i = 0; i < 12; i++) {
    await page.locator('button[onclick="completeSet()"]').click();
    if (i < 11) await page.getByRole('button', { name: /Skip rest/ }).click();
  }
  await expect(page.locator('[data-workout-result="unknown"]')).toBeVisible();
  await expect.poll(() => state.writes.length).toBe(2);
  const evidence = state.writes[1].workout_completion.exercises;
  expect(state.writes[1].session).toMatchObject({ completion: null, execution_state: 'unknown' });
  expect(evidence.every(item => item.completed_repetitions === null)).toBe(true);
  expect(evidence[4].completed_duration_seconds).toBeNull();
});

test('rest countdown advances normally and focuses the next set', async ({ page }) => {
  await mount(page);
  await page.clock.install();
  await page.locator('#wo-reps-in').fill('10'); await page.locator('button[onclick="completeSet()"]').click();
  // Exercise the existing timer callback without simulating a minute of Core animation.
  // The canonical prescription remains 60 seconds; only this test timer is shortened.
  await page.evaluate(() => runRest(2));
  await page.clock.runFor(1000); await expect(page.locator('#rt-n')).toHaveText('1');
  await page.clock.runFor(1000); await expect(page.locator('.wo-step')).toContainText('Set 2/2');
  await expect(page.locator('#wo-current-step')).toBeFocused();
});

test('receipt rerender preserves completion focus and scroll', async ({ page }) => {
  const state = await mount(page, 'en', true);
  await complete(page);
  await expect.poll(() => state.writes.length).toBe(1);
  const action = page.getByRole('button', { name: /Back to coach/ });
  await action.focus();
  const scroll = await page.locator('#wo-stage').evaluate(item => item.scrollTop);
  state.release();
  await expect(page.locator('[data-completion-section="adjustment"]')).toContainText('No training adjustment');
  await expect(action).toBeFocused();
  expect(await page.locator('#wo-stage').evaluate(item => item.scrollTop)).toBe(scroll);
  await page.keyboard.press('Tab'); await expect(page.locator('#wo-quit-btn')).toBeFocused();
});

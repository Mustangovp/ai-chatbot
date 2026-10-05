const { test, expect } = require('@playwright/test');

const profile = { goal: 'strength', level: 'intermediate', equip: 'home', age: '30', weight: '75', height: '178', gender: 'male' };
const identity = id => ({ exercise_id: id, exercise_version: '1.0.0', display_name: id });
const empty = { record: { completed_sessions: 0, recent_sessions: [] }, exercise_trajectories: [], recent_adjustments: [] };
const populated = () => ({
  record: { completed_sessions: 7, recent_sessions: [5, 4, 3, 2, 1].map(day => ({
    completed_at: `2026-10-0${day}T10:00:00Z`, exercises: [identity('dumbbell.front_squat'), identity('bodyweight.hollow_hold')]
  })) },
  exercise_trajectories: [
    { ...identity('dumbbell.front_squat'), state: 'progressing' },
    { ...identity('bodyweight.hollow_hold'), state: 'stable' },
    { ...identity('bodyweight.wall_push_up'), display_name: 'Wall Push-Up', state: 'insufficient_evidence' }
  ],
  recent_adjustments: [
    { decision_type: 'increase_repetitions', repetition_delta: 1 },
    { decision_type: 'increase_load', load_delta_kg: '1.25' },
    { decision_type: 'increase_sets', set_delta: 1 }, { decision_type: 'maintain' }, { decision_type: 'deload' }
  ].map((item, index) => ({ ...identity('dumbbell.front_squat'), ...item, occurred_at: `2026-10-0${5 - index}T10:00:00Z` }))
});

async function setup(page, { language = 'en', authenticated = true, data = populated(), status = 200 } = {}) {
  const calls = { chat: 0, reads: 0, writes: 0 };
  page.on('request', request => { if (new URL(request.url()).pathname === '/chat') calls.chat++; });
  await page.route('**/auth/me', route => route.fulfill({ json: authenticated ? {
    authenticated: true, email: 'local-progress@example.com', plan: 'free', status: 'free'
  } : { authenticated: false, plan: 'free', status: 'free' } }));
  await page.route('**/api/profile', route => route.fulfill({ json: { profile: { ...profile, language }, training_constraint_records: [] } }));
  await page.route('**/api/history', route => route.fulfill({ json: { workouts: [] } }));
  await page.route('**/api/conversations?*', route => route.fulfill({ json: { messages: [] } }));
  await page.route('**/api/athlete-model', route => route.fulfill({ json: {} }));
  await page.route('**/api/progress', route => {
    calls.reads++;
    if (route.request().method() !== 'GET') calls.writes++;
    return route.fulfill({ status, json: data });
  });
  await page.goto('/app?lang=' + language);
  await expect.poll(() => page.evaluate(() => SESSION.authenticated)).toBe(authenticated);
  if (authenticated) await expect.poll(() => page.evaluate(() => DATA_OWNER.kind)).toBe('account');
  await page.evaluate(profile => {
    ownedStorageSet('apexProfile', JSON.stringify(profile));
    document.getElementById('profile-modal').classList.remove('on');
  }, profile);
  return calls;
}

async function openProgress(page, language = 'en') {
  await page.locator('#menu-btn').click();
  await page.locator('#drawer').getByText(language === 'bg' ? 'Прогрес' : 'Progress', { exact: true }).click();
  await expect(page.locator('#training-progress')).toBeVisible();
  await expect(page.locator('#training-progress')).toHaveAttribute('aria-busy', 'false');
}

for (const language of ['en', 'bg']) {
  test(`Progress is three factual sections, not Consultation, in ${language}`, async ({ page }) => {
    const calls = await setup(page, { language });
    await openProgress(page, language);
    const root = page.locator('#training-progress');
    await expect(root.locator('[data-progress-block]')).toHaveCount(3);
    await expect(root.locator('h3')).toHaveText(language === 'bg' ?
      ['Тренировъчен запис', 'Посока по упражнения', 'Последни корекции'] : ['Training record', 'Exercise direction', 'Recent adjustments']);
    await expect(root.locator('button, canvas, svg, .ex-glyph, .wo-ex-glyph, .card, .gauge, .chart')).toHaveCount(0);
    await expect(page.locator('#consult')).not.toHaveClass(/\bon\b/);
    await expect(page.locator('#user-in')).toHaveValue('');
    expect(calls).toEqual({ chat: 0, reads: 1, writes: 0 });
    await expect(root).not.toContainText(/score|plateau|regressing|stalled|readiness|adherence|%|Latest generated workout|Последно създадена тренировка/i);
    const record = root.locator('[data-progress-block="record"]');
    await expect(record).toContainText(language === 'bg' ? '7 завършени тренировки са записани в APEX.' : '7 completed workouts are recorded in APEX.');
    await expect(record.locator('li')).toHaveCount(5);
    expect(await record.locator('time').evaluateAll(items => items.map(item => item.dateTime)))
      .toEqual([5, 4, 3, 2, 1].map(day => `2026-10-0${day}T10:00:00Z`));
  });

  test(`approved trajectory mappings and insufficient evidence in ${language}`, async ({ page }) => {
    await setup(page, { language });
    await openProgress(page, language);
    const labels = language === 'bg' ? ['Напредва', 'Стабилно', 'Нужни са още сравними сесии'] : ['Progressing', 'Stable', 'More comparable sessions needed'];
    await expect(page.locator('.training-progress-state')).toHaveText(labels);
    await expect(page.locator('[data-progress-exercise-id="dumbbell.front_squat"]')).toContainText(language === 'bg' ?
      'APEX има достатъчно сравними сесии и е регистрирал прогресиращи корекции.' : 'APEX has enough comparable sessions and has recorded forward training adjustments.');
    await expect(page.locator('[data-progress-exercise-id="bodyweight.hollow_hold"]')).toContainText(language === 'bg' ?
      'Сравнимите сесии поддържат текущата тренировъчна схема.' : 'Comparable sessions support keeping the current training prescription.');
    await expect(page.locator('[data-progress-exercise-id="bodyweight.wall_push_up"]')).not.toContainText(/failed|failure|no progress|plateau|застой|регрес/i);
  });

  test(`Task05 adjustment text is reused exactly in ${language}`, async ({ page }) => {
    const data = populated();
    data.recent_adjustments[4] = { ...identity('dumbbell.front_squat'), occurred_at: '2026-10-01T10:00:00Z',
      decision_type: 'replace_exercise', replacement: identity('bodyweight.push_up'), reason: 'PRIVATE_REASON', policy_version: 'PRIVATE_POLICY' };
    await setup(page, { language, data });
    await openProgress(page, language);
    const expected = await page.evaluate(items => items.map(item => adjustmentText(item)), data.recent_adjustments);
    await expect(page.locator('[data-progress-block="adjustments"] li p')).toHaveText(expected);
    await expect(page.locator('#training-progress')).not.toContainText(/PRIVATE|increase_repetitions|replace_exercise|policy_version/);
  });

  test(`truthful empty and singular record copy in ${language}`, async ({ page }) => {
    await setup(page, { language, data: empty });
    await openProgress(page, language);
    const texts = language === 'bg' ? ['Още няма достатъчно завършени тренировки за прогрес отчет.',
      'Още няма достатъчно сравними тренировъчни данни.', 'Още няма потвърдени тренировъчни корекции.'] :
      ['There are not enough completed workouts for a progress record yet.', 'There is not enough comparable training data yet.', 'No training adjustments have been confirmed yet.'];
    for (const text of texts) await expect(page.locator('#training-progress')).toContainText(text);
    const singular = await page.evaluate(() => progressRecordText(1, false));
    expect(singular).toBe(language === 'bg' ? '1 завършена тренировка е записана в APEX.' : '1 completed workout is recorded in APEX.');
  });
}

test('canonical thumbnail localization and neutral fallback are reused', async ({ page }) => {
  await setup(page);
  await openProgress(page);
  for (const id of ['dumbbell.front_squat', 'bodyweight.hollow_hold']) {
    const row = page.locator(`[data-progress-exercise-id="${id}"]`), image = row.locator('img');
    const visual = await page.evaluate(id => ApexExerciseVisuals.resolve(id), id);
    await expect(image).toHaveAttribute('src', visual.thumb);
    await expect(image).toHaveAttribute('alt', visual.alt.en);
    await image.scrollIntoViewIfNeeded();
    await expect.poll(() => image.evaluate(element => element.complete && element.naturalWidth > 0)).toBe(true);
  }
  const fallback = page.locator('[data-progress-exercise-id="bodyweight.wall_push_up"] .exercise-visual');
  await expect(fallback).toHaveClass('exercise-visual is-fallback');
  await expect(fallback).toHaveAttribute('aria-hidden', 'true');
  await expect(fallback.locator('img, svg')).toHaveCount(0);
});

for (const language of ['en', 'bg']) {
  test(`anonymous Progress uses only truthful current-browser completed work in ${language}`, async ({ page }) => {
    const calls = await setup(page, { authenticated: false, language });
    await page.evaluate(() => ownedStorageSet('apexWorkoutLog', JSON.stringify([
      { execution_schema: 'workout-execution-v1', execution_state: 'completed', ts: Date.parse('2026-10-04T10:00:00Z'),
        exercises: [{ execution_state: 'completed', completed_sets: 2, actual_repetitions: 10 }] },
      { execution_schema: 'workout-execution-v1', execution_state: 'partial', ts: Date.parse('2026-10-05T10:00:00Z'),
        exercises: [{ execution_state: 'completed', completed_sets: 2, actual_repetitions: 10 }] },
      { completion: 100, ts: Date.now(), exercises: [{ sets: 2, reps: '8-12' }] },
      { execution_schema: 'workout-execution-v1', execution_state: 'completed', ts: Date.now(),
        exercises: [{ execution_state: 'unknown', completed_sets: 0, actual_repetitions: null }] }
    ])));
    await openProgress(page, language);
    await expect(page.locator('[data-progress-block="record"]')).toContainText(language === 'bg' ?
      '1 завършена тренировка е записана в този браузър.' : '1 completed workout is recorded in this browser.');
    await expect(page.locator('[data-progress-block="record"] time')).toHaveCount(1);
    await expect(page.locator('[data-progress-block="direction"]')).toContainText(language === 'bg' ?
      'Влез в профила си, за да виждаш потвърдена тренировъчна тенденция между сесиите.' : 'Sign in to see verified training direction across sessions.');
    await expect(page.locator('.training-progress-direction')).toHaveCount(0);
    expect(calls).toEqual({ chat: 0, reads: 0, writes: 0 });
    await page.evaluate(() => { closePanel(); rotateAnonymousOwner(); });
    await openProgress(page, language);
    await expect(page.locator('[data-progress-block="record"] time')).toHaveCount(0);
  });
}

test('unavailable account data is not represented as empty evidence', async ({ page }) => {
  await setup(page, { status: 503, data: { error: 'training_data_unavailable' } });
  await openProgress(page);
  await expect(page.locator('#training-progress')).toContainText('Training data is unavailable at the moment.');
  await expect(page.locator('#training-progress')).not.toContainText('There are not enough completed workouts');
});

test('a response arriving after owner change is discarded', async ({ page }) => {
  await setup(page);
  let release;
  const wait = new Promise(resolve => { release = resolve; });
  await page.route('**/api/progress', async route => { await wait; await route.fulfill({ json: populated() }); });
  await page.locator('#menu-btn').click();
  await page.locator('#drawer').getByText('Progress', { exact: true }).click();
  await expect(page.locator('#training-progress')).toHaveAttribute('aria-busy', 'true');
  await page.evaluate(() => { SESSION.authenticated = false; rotateAnonymousOwner(); showProgress(); });
  release();
  await expect(page.locator('#training-progress')).toContainText('Sign in to see verified training direction');
  await expect(page.locator('#training-progress')).not.toContainText('7 completed workouts');
});

for (const width of [1440, 390, 360]) {
  test(`Progress geometry at ${width}px preserves Core and supports scrolling`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 1440 ? 900 : width === 390 ? 844 : 800 });
    await setup(page, { language: 'bg' });
    const before = await page.locator('#core').boundingBox();
    await openProgress(page, 'bg');
    const sheet = page.locator('#panel-modal .sheet');
    expect(await sheet.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const row of await page.locator('#training-progress li').all()) {
      expect(await row.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    }
    if (process.env.APEX_PROGRESS_SCREENSHOTS) {
      await page.screenshot({ path: require('path').join(process.env.APEX_PROGRESS_SCREENSHOTS, `progress-${width}.png`) });
      await page.locator('[data-progress-block="direction"]').scrollIntoViewIfNeeded();
      await page.screenshot({ path: require('path').join(process.env.APEX_PROGRESS_SCREENSHOTS, `progress-direction-${width}.png`) });
    }
    await page.locator('#panel-close').scrollIntoViewIfNeeded();
    await page.locator('#panel-close').click();
    expect(await page.locator('#core').boundingBox()).toEqual(before);
    await expect(page.locator('#core')).toBeVisible();
  });
}

const { test, expect } = require('@playwright/test');

const exercise = (id, duration = false) => ({
  exercise_id: id, exercise_version: '1.0.0', display_name: id,
  sets: 2, prescription_type: duration ? 'duration' : 'repetitions',
  rep_min: duration ? null : 8, rep_max: duration ? null : 12,
  duration_min_seconds: duration ? 20 : null, duration_max_seconds: duration ? 40 : null,
  rest_seconds: 60, rpe: 7, rir: 3, tempo: '2-0-2', difficulty: 'intermediate'
});
const populated = () => ({
  latest_workout: {
    delivered_at: '2026-10-04T10:00:00Z', estimated_duration_minutes: 25,
    exercises: [exercise('dumbbell.front_squat'), exercise('bodyweight.hollow_hold', true), { ...exercise('bodyweight.wall_push_up'), display_name: 'Wall Push-Up' }]
  },
  last_completed: {
    completed_at: '2026-10-03T10:00:00Z', completion_percent: 100,
    exercises: [
      { exercise_id: 'bodyweight.push_up', exercise_version: '1.0.0', prescription_type: 'repetitions', completed_sets: 2, completed_repetitions: 10, completed_load: null },
      { exercise_id: 'bodyweight.hollow_hold', exercise_version: '1.0.0', prescription_type: 'duration', completed_sets: 2, completed_repetitions: null, completed_duration_seconds: 30, completed_load: 5 }
    ]
  },
  active_constraints: [{ id: 'constraint-one', pattern: 'vertical_push' }]
});
const empty = { latest_workout: null, last_completed: null, active_constraints: [] };
const profile = { goal: 'strength', level: 'intermediate', equip: 'home', age: '30', weight: '75', height: '178', gender: 'male' };

async function setup(page, { language = 'en', authenticated = true, data = populated(), status = 200 } = {}) {
  const calls = { chat: 0, read: 0 };
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/chat') calls.chat++;
  });
  await page.route('**/auth/me', route => route.fulfill({ json: authenticated ? { authenticated: true, email: 'local-training@example.com', plan: 'free', status: 'free' } : { authenticated: false, plan: 'free', status: 'free' } }));
  await page.route('**/api/profile', route => route.fulfill({ json: { profile: { ...profile, language }, training_constraint_records: [] } }));
  await page.route('**/api/history', route => route.fulfill({ json: { workouts: [] } }));
  await page.route('**/api/conversations?*', route => route.fulfill({ json: { messages: [] } }));
  await page.route('**/api/my-training', route => { calls.read++; return route.fulfill({ status, json: data }); });
  await page.goto('/app?lang=' + language);
  await expect.poll(() => page.evaluate(() => SESSION.authenticated)).toBe(authenticated);
  if (authenticated) await expect.poll(() => page.evaluate(() => DATA_OWNER.kind)).toBe('account');
  await page.evaluate(profile => {
    ownedStorageSet('apexProfile', JSON.stringify(profile));
    document.getElementById('profile-modal').classList.remove('on');
  }, profile);
  return calls;
}

async function openTraining(page, language = 'en') {
  await page.locator('#menu-btn').click();
  await page.locator('#drawer').getByText(language === 'bg' ? 'Моите тренировки' : 'My Training', { exact: true }).click();
  await expect(page.locator('#my-training')).toBeVisible();
  await expect(page.locator('#my-training')).toHaveAttribute('aria-busy', 'false');
}

for (const language of ['en', 'bg']) {
  test(`My Training is factual, localized and does not enter chat in ${language}`, async ({ page }) => {
    const calls = await setup(page, { language });
    await openTraining(page, language);
    const root = page.locator('#my-training');
    await expect(root.locator('[data-my-training-block]')).toHaveCount(3);
    await expect(root.locator('.save')).toHaveCount(1);
    await expect(page.locator('#consult')).not.toHaveClass(/\bon\b/);
    await expect(page.locator('#user-in')).toHaveValue('');
    expect(calls.chat).toBe(0);
    expect(calls.read).toBe(1);
    await expect(root).toContainText(language === 'bg' ? 'Последно създадена тренировка' : 'Latest generated workout');
    await expect(root).toContainText(language === 'bg' ? 'Последно завършена' : 'Last completed');
    await expect(root).toContainText(language === 'bg' ? 'APEX помни' : 'APEX remembers');
    await expect(root).toContainText(language === 'bg' ? 'Избягвай преси над глава' : 'Avoid overhead pressing');
    await expect(root).not.toContainText('vertical_push');
    await expect(root).not.toContainText(/Next Workout|Upcoming|Current Plan|Active Plan|ready|score/i);
    await expect(root.locator('details, .ex-glyph, .wo-ex-glyph')).toHaveCount(0);
  });

  test(`typed doses and observed completion stay distinct in ${language}`, async ({ page }) => {
    await setup(page, { language });
    await openTraining(page, language);
    const latest = page.locator('[data-my-training-block="latest"]');
    await expect(latest.locator('.my-training-exercise')).toHaveCount(3);
    await expect(latest.locator('[data-training-exercise-id="dumbbell.front_squat"]')).toContainText('8–12');
    const duration = latest.locator('[data-training-exercise-id="bodyweight.hollow_hold"]');
    await expect(duration).toContainText('20–40');
    await expect(duration).toContainText(language === 'bg' ? 'сек продължителност' : 'sec duration');
    await expect(duration).not.toContainText(language === 'bg' ? 'повторения' : 'repetitions');
    const completed = page.locator('[data-my-training-block="completed"]');
    await expect(completed).toContainText('10 ' + (language === 'bg' ? 'повторения' : 'repetitions'));
    await expect(completed).toContainText('30 ' + (language === 'bg' ? 'сек продължителност' : 'sec duration'));
    await expect(completed).toContainText('5 ' + (language === 'bg' ? 'кг' : 'kg'));
    await expect(completed).not.toContainText('0 ' + (language === 'bg' ? 'кг' : 'kg'));
    await expect(completed).not.toContainText('8–12');
  });

  test(`truthful empty states remain usable in ${language}`, async ({ page }) => {
    await setup(page, { language, data: empty });
    await openTraining(page, language);
    const copy = language === 'bg' ? ['Още няма създадена тренировка.', 'Още няма завършена тренировка.', 'Няма запазени активни тренировъчни ограничения.'] : ['No workout has been generated yet.', 'No workout has been completed yet.', 'No active training constraints are saved.'];
    for (const text of copy) await expect(page.locator('#my-training')).toContainText(text);
    await expect(page.locator('#my-training-create')).toBeEnabled();
  });
}

test('approved canonical thumbs and neutral fallback reuse the visual resolver', async ({ page }) => {
  await setup(page);
  await openTraining(page);
  const latest = page.locator('[data-my-training-block="latest"]');
  for (const id of ['dumbbell.front_squat', 'bodyweight.hollow_hold']) {
    const row = latest.locator(`[data-training-exercise-id="${id}"]`);
    const image = row.locator('img');
    const expected = await page.evaluate(id => ApexExerciseVisuals.resolve(id), id);
    await expect(image).toHaveAttribute('src', expected.thumb);
    await expect(image).toHaveAttribute('alt', expected.alt.en);
    await image.scrollIntoViewIfNeeded();
    await expect.poll(() => image.evaluate(element => element.complete && element.naturalWidth > 0)).toBe(true);
  }
  const fallback = latest.locator('[data-training-exercise-id="bodyweight.wall_push_up"] .exercise-visual');
  await expect(fallback).toHaveClass('exercise-visual is-fallback');
  await expect(fallback).toHaveAttribute('aria-hidden', 'true');
  await expect(fallback.locator('img, svg')).toHaveCount(0);
});

test('later-session payload fields are never rendered and retired constraints stay hidden', async ({ page }) => {
  const data = populated();
  data.latest_workout.sessions = [{ exercises: [{ display_name: 'LATER SESSION SECRET' }] }];
  data.next_session = { name: 'LATER SESSION SECRET' };
  data.active_constraints.push({ pattern: 'squat', state: 'retired' });
  await setup(page, { data });
  await openTraining(page);
  await expect(page.locator('#my-training')).not.toContainText('LATER SESSION SECRET');
  await expect(page.locator('[data-my-training-block="constraints"]')).not.toContainText('Avoid squats');
});

test('anonymous opening makes no authenticated read and CTA alone enters the existing flow', async ({ page }) => {
  const calls = await setup(page, { authenticated: false });
  await page.route('**/chat', route => route.fulfill({ contentType: 'text/event-stream', body: 'data: {"t":"Local test reply"}\n\ndata: {"done":true}\n\n' }));
  await openTraining(page);
  expect(calls.read).toBe(0);
  expect(calls.chat).toBe(0);
  await expect(page.locator('#my-training')).toContainText('No workout has been generated yet.');
  await page.locator('#my-training-create').click();
  await expect(page.locator('#consult')).toHaveClass(/\bon\b/);
  await expect.poll(() => calls.chat).toBe(1);
  await expect(page.locator('#panel-modal')).not.toHaveClass(/\bon\b/);
});

test('anonymous local completion uses only observed, owner-scoped work', async ({ page }) => {
  await setup(page, { authenticated: false });
  await page.evaluate(() => ownedStorageSet('apexWorkoutLog', JSON.stringify([
    { execution_schema: 'workout-execution-v1', execution_state: 'completed', ts: Date.parse('2026-10-03T10:00:00Z'), exercises: [{ name: 'Push-Up', exercise_id: 'bodyweight.push_up', exercise_version: '1.0.0', execution_state: 'completed', completed_sets: 2, actual_repetitions: 9, completed_load: null }] },
    { execution_schema: 'workout-execution-v1', execution_state: 'unknown', ts: Date.now(), exercises: [{ name: 'Fake completion', sets: 4, reps: '12' }] }
  ])));
  await openTraining(page);
  await expect(page.locator('[data-my-training-block="completed"]')).toContainText('9 repetitions');
  await expect(page.locator('#my-training')).not.toContainText('Fake completion');
  await page.evaluate(() => { closePanel(); rotateAnonymousOwner(); });
  await openTraining(page);
  await expect(page.locator('[data-my-training-block="completed"]')).toContainText('No workout has been completed yet.');
});

test('anonymous latest summary requires first-session metadata attached to a rendered protocol', async ({ page }) => {
  await setup(page, { authenticated: false });
  const metadata = { ...exercise('dumbbell.front_squat'), display_name: 'Dumbbell Front Squat', prescribed_sets: 2, prescription_id: 'browser-prescription' };
  const session = { session_id: 'browser-first', exercises: [metadata] };
  const events = [
    { t: '| Exercise | Sets | Reps | Rest |\n| --- | --- | --- | --- |\n| Dumbbell Front Squat | 2 | 8-12 | 60 |' },
    { training_completion: { plan_id: 'browser-plan', plan_version: 'training-plan-blueprint-v3', sessions: [session, { session_id: 'hidden-later', exercises: [] }] } },
    { done: true }
  ];
  await page.route('**/chat', route => route.fulfill({ contentType: 'text/event-stream', body: events.map(event => 'data: ' + JSON.stringify(event) + '\n\n').join('') }));
  await page.evaluate(() => enterConsult('Build me a workout for today'));
  await expect(page.locator('.workout-protocol')).toBeVisible();
  await page.evaluate(() => exitConsult());
  await openTraining(page);
  await expect(page.locator('[data-my-training-block="latest"] .my-training-exercise')).toHaveCount(1);
  await expect(page.locator('#my-training')).not.toContainText('hidden-later');
  await page.evaluate(() => { closePanel(); rotateAnonymousOwner(); });
  await openTraining(page);
  await expect(page.locator('[data-my-training-block="latest"]')).toContainText('No workout has been generated yet.');
});

test('unavailable authenticated store is not represented as empty or all clear', async ({ page }) => {
  await setup(page, { status: 503, data: { error: 'training_data_unavailable' } });
  await openTraining(page);
  await expect(page.locator('#my-training')).toContainText('Training data is unavailable at the moment.');
  await expect(page.locator('#my-training')).not.toContainText('No active training constraints are saved.');
});

for (const width of [1440, 390, 360]) {
  test(`readable My Training geometry at ${width}px without changing Core`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 1440 ? 900 : width === 390 ? 844 : 800 });
    await setup(page);
    const before = await page.locator('#core').boundingBox();
    await openTraining(page);
    const sheet = page.locator('#panel-modal .sheet');
    expect(await sheet.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    const actionBox = await page.locator('#my-training-create').boundingBox();
    const sheetBox = await sheet.boundingBox();
    expect(actionBox.y + actionBox.height).toBeLessThanOrEqual(sheetBox.y + sheetBox.height + 1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const row of await page.locator('#my-training .my-training-exercise').all()) {
      expect(await row.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    }
    if (process.env.APEX_MY_TRAINING_SCREENSHOTS) {
      await page.screenshot({ path: require('path').join(process.env.APEX_MY_TRAINING_SCREENSHOTS, `my-training-${width}.png`) });
    }
    await page.locator('#panel-close').scrollIntoViewIfNeeded();
    await page.locator('#panel-close').click();
    const after = await page.locator('#core').boundingBox();
    expect(after).toEqual(before);
    await expect(page.locator('#core')).toBeVisible();
  });
}

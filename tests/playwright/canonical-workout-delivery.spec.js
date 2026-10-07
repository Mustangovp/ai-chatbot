const { test, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const fixtures = JSON.parse(execFileSync(process.env.APEX_TEST_PYTHON || 'python', [path.join(__dirname, '../canonical_workout_fixture.py')], { encoding: 'utf8' }));

async function mount(page, fixture, language = 'bg', mutate = null) {
  await page.goto('/app?lang=' + language);
  const payload = structuredClone(fixture.languages[language]);
  if (mutate) mutate(payload);
  await page.evaluate(({ payload, language }) => {
    lang = language;
    ownedStorageSet('apexProfile', JSON.stringify({goal:'strength',age:'30',weight:'75',height:'178',gender:'male',level:'beginner',equip:'home'}));
    enterConsult('');
    document.getElementById('profile-modal').classList.remove('on');
    pendingTrainingCompletion = payload.metadata;
    pendingCompletionSessions = payload.metadata.sessions.slice();
    appendCoach().innerHTML = renderMarkdown(payload.text);
  }, { payload, language });
}

for (const language of ['bg', 'en']) {
  test(`all 40 real canonical prescriptions render in ${language}`, async ({ page }) => {
    await page.goto('/app?lang=' + language);
    const results = await page.evaluate(({ fixtures, language }) => {
      lang = language;
      return fixtures.map(fixture => {
        const payload = fixture.languages[language];
        pendingTrainingCompletion = payload.metadata;
        pendingCompletionSessions = payload.metadata.sessions.slice();
        const html = renderMarkdown(payload.text);
        const element = document.createElement('div');
        element.innerHTML = html;
        const card = element.querySelector('.workout-exercise-card');
        return { id: fixture.id, count: element.querySelectorAll('.workout-exercise-card').length,
          identity: card && card.dataset.exerciseId, text: element.textContent,
          completion: card && renderedWorkoutExercises[payload.metadata.sessions[0].session_id][0].completion };
      });
    }, { fixtures, language });
    for (const [index, result] of results.entries()) {
      expect(result.count, result.id).toBe(1);
      expect(result.identity, result.id).toBe(result.id);
      expect(result.completion).toEqual(fixtures[index].languages[language].metadata.sessions[0].exercises[0]);
      expect(result.text).not.toContain(language === 'bg' ? 'не можа да бъде потвърдена' : 'could not be safely verified');
    }
  });
}

test('canonical identity ignores translated table/display-name changes', async ({ page }) => {
  await mount(page, fixtures.find(item => item.id === 'band.row'), 'bg', payload => {
    payload.text = payload.text.replace(payload.metadata.sessions[0].exercises[0].display_name, 'Translated presentation label');
    payload.metadata.sessions[0].exercises[0].display_name = 'Another presentation label';
  });
  await expect(page.locator('.workout-exercise-card')).toHaveAttribute('data-exercise-id', 'band.row');
});

test('observed BG request finalizes real renderer output after SSE done', async ({ page }) => {
  const payload = fixtures.find(item => item.id === 'dumbbell.row').languages.bg;
  await mount(page, fixtures.find(item => item.id === 'bodyweight.squat'));
  await page.route('**/chat', route => route.fulfill({
    status: 200, contentType: 'text/event-stream',
    body: [{ t: payload.text }, { training_completion: payload.metadata }, { done: true }]
      .map(event => 'data: ' + JSON.stringify(event) + '\n\n').join('')
  }));
  await page.evaluate(async () => {
    document.getElementById('feed').innerHTML = '';
    document.getElementById('user-in').value = 'Направи ми тренировка за днес';
    await send();
  });
  await expect(page.locator('.workout-exercise-card')).toHaveAttribute('data-exercise-id', 'dumbbell.row');
  await expect(page.locator('[data-workout-rejected]')).toHaveCount(0);
  expect(await page.evaluate(() => ChatLifecycle.current.state)).toBe('COMPLETED');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.locator('.workout-exercise-card').scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'test-results/canonical-workout-desktop.png' });
});

const tampers = {
  'unknown namespace': item => { item.exercise_id = 'unknown.plank'; },
  'malformed sets': item => { item.prescribed_sets = '2'; },
  'zero sets': item => { item.prescribed_sets = 0; },
  'invalid type': item => { item.prescription_type = 'seconds'; },
  'duration with repetitions': item => { item.rep_min = 8; item.rep_max = 12; },
  'invalid duration': item => { item.duration_max_seconds = 0; },
  'missing identity': item => { item.prescription_id = ''; },
  'duplicate identity': (item, payload) => {
    payload.metadata.sessions[0].exercises.push({ ...item });
    payload.text += '\n' + payload.text.split('\n').find(line => line.includes(item.display_name) && line.startsWith('|'));
  },
};
for (const [name, tamper] of Object.entries(tampers)) {
  test(`tamper fails closed: ${name}`, async ({ page }) => {
    await mount(page, fixtures.find(item => item.id === 'bodyweight.plank'), 'bg', payload => {
      tamper(payload.metadata.sessions[0].exercises[0], payload);
      payload.text += '\n\nSUCCESS_EXPLANATION_SENTINEL';
    });
    await expect(page.locator('.workout-exercise-card')).toHaveCount(0);
    await expect(page.locator('.start-wo')).toHaveCount(0);
    await expect(page.locator('#feed')).toContainText('Тренировката не можа да бъде потвърдена безопасно');
    await expect(page.locator('#feed')).not.toContainText('SUCCESS_EXPLANATION_SENTINEL');
  });
}

test('completion queue identity cannot contradict the authoritative metadata', async ({ page }) => {
  await mount(page, fixtures.find(item => item.id === 'bodyweight.plank'));
  await page.evaluate(payload => {
    pendingTrainingCompletion = payload.metadata;
    pendingCompletionSessions = structuredClone(payload.metadata.sessions);
    pendingCompletionSessions[0].exercises[0].exercise_id = 'bodyweight.squat';
    appendCoach().innerHTML = renderMarkdown(payload.text + '\n\nSUCCESS_EXPLANATION_SENTINEL');
  }, fixtures.find(item => item.id === 'bodyweight.plank').languages.bg);
  const response = page.locator('#feed .msg.a').last();
  await expect(response.locator('.workout-exercise-card')).toHaveCount(0);
  await expect(response).toContainText('Тренировката не можа да бъде потвърдена безопасно');
  await expect(response).not.toContainText('SUCCESS_EXPLANATION_SENTINEL');
});

test('malformed SSE completion event cannot fall back to display-name identity', async ({ page }) => {
  await page.goto('/app?lang=bg');
  const results = await page.evaluate(payload => [null, {}, { sessions: [] }].map(metadata => {
    ChatLifecycle.metadata({}, { training_completion: metadata });
    return renderMarkdown(payload.text + '\n\nSUCCESS_EXPLANATION_SENTINEL');
  }), fixtures.find(item => item.id === 'bodyweight.plank').languages.bg);
  for (const markup of results) {
    expect(markup).toContain('data-workout-rejected');
    expect(markup).not.toContain('workout-exercise-card');
    expect(markup).not.toContain('SUCCESS_EXPLANATION_SENTINEL');
  }
});

for (const width of [390, 360]) {
  test(`beginner six, duration and Start remain usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 800 });
    const ids = ['bodyweight.squat', 'bodyweight.wall_push_up', 'bodyweight.table_row', 'bodyweight.glute_bridge', 'bodyweight.plank', 'bodyweight.march_in_place'];
    const payload = structuredClone(fixtures.find(item => item.id === ids[0]).languages.bg);
    const items = ids.map(id => structuredClone(fixtures.find(item => item.id === id).languages.bg.metadata.sessions[0].exercises[0]));
    payload.metadata.sessions[0].exercises = items;
    const rows = ids.map(id => fixtures.find(item => item.id === id).languages.bg.text.split('\n').find(line => line.startsWith('| ') && !line.includes('Упражнение') && !line.includes('---')));
    const first = payload.text.split('\n');
    payload.text = [...first.slice(0, first.findIndex(line => line.startsWith('| ---')) + 1), ...rows].join('\n');
    await mount(page, { languages: { bg: payload } });
    await expect(page.locator('.workout-exercise-card')).toHaveCount(6);
    const plank = page.locator('[data-exercise-id="bodyweight.plank"]');
    await expect(plank).toContainText('Продължителност');
    await expect(plank).not.toContainText('Повторения');
    await page.locator('.workout-exercise-card').first().scrollIntoViewIfNeeded();
    await page.screenshot({ path: `test-results/canonical-beginner-${width}.png` });
    await page.locator('.start-wo').click();
    await expect(page.locator('#wo-stage')).toBeVisible();
    expect(await page.evaluate(() => WO.ex.map(item => item.completion.exercise_id))).toEqual(ids);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.evaluate(() => quitWorkout());
  });
}

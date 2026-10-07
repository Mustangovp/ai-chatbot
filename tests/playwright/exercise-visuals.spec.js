const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

const exerciseIds = [
  'dumbbell.front_squat',
  'bodyweight.push_up',
  'dumbbell.bent_over_row',
  'dumbbell.romanian_deadlift',
  'bodyweight.hollow_hold'
];
const beginnerExerciseIds = [
  'bodyweight.squat',
  'bodyweight.wall_push_up',
  'bodyweight.table_row',
  'bodyweight.glute_bridge',
  'bodyweight.plank'
];
const assetPath = (id, variant) => `/static/exercise/visuals/v1/${id}--${variant}.webp`;

async function mountWorkout(page, language = 'en', ids = exerciseIds) {
  await page.goto('/app?lang=' + language);
  await page.evaluate(({ language, ids }) => {
    lang = language;
    ownedStorageSet('apexProfile', JSON.stringify({
      goal: 'muscle_gain', age: '30', weight: '75', height: '178',
      gender: 'male', level: 'intermediate', equip: 'home'
    }));
    enterConsult('');
    document.getElementById('profile-modal').classList.remove('on');
    const items = ids.map((id, index) => {
      const duration = id === 'bodyweight.hollow_hold' || id === 'bodyweight.plank';
      return {
        prescription_id: 'visual-prescription-' + index,
        exercise_id: id, exercise_version: '1.0.0',
        display_name: ApexExerciseInstructions.display(ApexExerciseInstructions.findByExerciseId(id), language),
        prescribed_sets: 2, rep_min: duration ? null : 8, rep_max: duration ? null : 12,
        rest_seconds: 60, difficulty: id === 'bodyweight.push_up' ? 'beginner' : 'intermediate',
        prescription_type: duration ? 'duration' : 'repetitions',
        duration_min_seconds: duration ? 20 : null, duration_max_seconds: duration ? 40 : null
      };
    });
    const session = { session_id: 'visual-session', session_index: 1, exercises: items };
    pendingTrainingCompletion = { plan_id: 'visual-plan', plan_version: 'training-plan-blueprint-v3', sessions: [session] };
    pendingCompletionSessions = [session];
    appendCoach().innerHTML = renderMarkdown([
      '| Exercise | Sets | Reps | Rest | Note |', '| --- | --- | --- | --- | --- |',
      ...items.map(item => `| ${item.display_name} | 2 | ${item.prescription_type === 'duration' ? '20-40 sec' : '8-12'} | 60 | Tempo 2-0-2; RPE 7; RIR 3 |`)
    ].join('\n'));
  }, { language, ids });
}

async function expectLoaded(image) {
  await image.scrollIntoViewIfNeeded();
  await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate(element => element.complete && element.naturalWidth > 0)).toBe(true);
}

test.describe('canonical exercise visuals', () => {
  for (const language of ['bg', 'en']) {
    test(`five approved thumbs use canonical IDs and localized alt text in ${language}`, async ({ page }) => {
      await mountWorkout(page, language);
      const cards = page.locator('.workout-exercise-card');
      await expect(cards).toHaveCount(5);
      await expect(cards.locator('.ex-glyph')).toHaveCount(0);
      for (const [index, id] of exerciseIds.entries()) {
        const image = cards.nth(index).locator('.exercise-visual img');
        await expect(image).toHaveAttribute('src', assetPath(id, 'thumb'));
        await expect(image).toHaveAttribute('loading', 'lazy');
        const expectedAlt = await page.evaluate(({ id, language }) => ApexExerciseVisuals.resolve(id).alt[language], { id, language });
        await expect(image).toHaveAttribute('alt', expectedAlt);
        expect(expectedAlt).not.toBe('');
        await expectLoaded(image);
        await expect(cards.nth(index).locator('.ex-diff')).toHaveText(index === 1 ? (language === 'bg' ? 'Лесно' : 'Easy') : (language === 'bg' ? 'Средно' : 'Medium'));
        const stats = cards.nth(index).locator('.workout-card-stats');
        await expect(stats).toContainText(index === 4 ? '20–40' : '8-12');
        await expect(stats).toContainText(index === 4 ? (language === 'bg' ? 'Продължителност' : 'Duration') : (language === 'bg' ? 'Повторения' : 'Repetitions'));
        await expect(stats).toContainText('2-0-2');
      }
    });
  }

  test('all five active exercises use the corresponding protocol visual', async ({ page }) => {
    await mountWorkout(page);
    const before = await page.evaluate(() => JSON.stringify(renderedWorkoutExercises['visual-session'].map(exercise => exercise.completion)));
    await page.locator('.start-wo').click();
    for (const [index, id] of exerciseIds.entries()) {
      await page.evaluate(index => { WO.i = index; WO.set = 0; renderWO(); }, index);
      const visual = page.locator('#wo-stage > .exercise-visual-protocol');
      await expect(visual).toHaveAttribute('data-exercise-visual-id', id);
      await expect(visual.locator('img')).toHaveAttribute('src', assetPath(id, 'protocol'));
      await expect(visual.locator('img')).toHaveAttribute('loading', 'eager');
      await expectLoaded(visual.locator('img'));
      await expect(page.locator('#wo-stage > .wo-ex-glyph')).toHaveCount(0);
      await expect(page.locator('#wo-reps-in')).toHaveAttribute('placeholder', index === 4 ? 'seconds' : 'reps');
      await expect(page.locator('button[onclick="completeSet()"]')).toBeEnabled();
    }
    expect(await page.evaluate(() => JSON.stringify(WO.ex.map(exercise => exercise.completion)))).toBe(before);
    await page.evaluate(() => quitWorkout());
  });

  test('resolver never infers visuals from display name, instruction ID or position', async ({ page }) => {
    await mountWorkout(page, 'en', ['bodyweight.push_up']);
    const result = await page.evaluate(() => {
      const source = renderedWorkoutExercises['visual-session'][0];
      const labels = { easy: 'Easy', med: 'Medium', hard: 'Hard' };
      const cases = [
        { ...source, completion: undefined },
        { ...source, completion: { ...source.completion, exercise_id: 'push_up' } },
        { ...source, completion: { ...source.completion, exercise_id: 'bodyweight.unmapped' } },
        { ...source, name: 'Hollow Body Hold', canonical_id: 'bodyweight.hollow_hold' }
      ];
      return cases.map(exercise => renderWorkoutExerciseCard(exercise, labels));
    });
    for (const markup of result.slice(0, 3)) {
      expect(markup).toContain('exercise-visual is-fallback');
      expect(markup).not.toContain('<img');
      expect(markup).toContain('aria-hidden="true"');
    }
    expect(result[3]).toContain(assetPath('bodyweight.push_up', 'thumb'));
    expect(result[3]).not.toContain(assetPath('bodyweight.hollow_hold', 'thumb'));
    expect(await page.evaluate(() => [ApexExerciseVisuals.resolve('__proto__'), ApexExerciseVisuals.resolve(null), ApexExerciseVisuals.resolve('Push-Up')])).toEqual([null, null, null]);
  });

  test('legacy content uses decorative graphite fallback in card and protocol', async ({ page }) => {
    await mountWorkout(page);
    await page.evaluate(() => {
      pendingTrainingCompletion = null; pendingCompletionSessions = [];
      document.getElementById('feed').innerHTML = '';
      appendCoach().innerHTML = renderMarkdown('| Exercise | Sets | Reps | Rest |\n| --- | --- | --- | --- |\n| Push-up | 2 | 8-12 | 60 |');
    });
    const fallback = page.locator('.workout-exercise-card .exercise-visual');
    await expect(fallback).toHaveClass('exercise-visual is-fallback');
    await expect(fallback).toHaveAttribute('aria-hidden', 'true');
    await expect(fallback).toHaveText('');
    await expect(fallback.locator('img, svg')).toHaveCount(0);
    await page.locator('.start-wo').click();
    await expect(page.locator('#wo-stage .exercise-visual-protocol')).toHaveClass('exercise-visual exercise-visual-protocol is-fallback');
    await expect(page.locator('#wo-stage .exercise-visual-protocol')).toHaveText('');
    await page.evaluate(() => quitWorkout());
  });

  test('failed approved assets preserve geometry, controls and typed completion', async ({ page }) => {
    await page.route('**/static/exercise/visuals/v1/*.webp', route => route.abort());
    await mountWorkout(page, 'en', ['bodyweight.hollow_hold']);
    const cardVisual = page.locator('.workout-exercise-card .exercise-visual');
    await cardVisual.scrollIntoViewIfNeeded();
    await expect(cardVisual).toHaveClass('exercise-visual is-fallback');
    await expect(cardVisual.locator('img')).toBeHidden();
    const cardSize = await cardVisual.boundingBox();
    expect(cardSize.width).toBe(80); expect(cardSize.height).toBe(60);
    let posted;
    await page.route('**/api/workout', async route => {
      posted = route.request().postDataJSON();
      await route.fulfill({ status: 200, json: {} });
    });
    await page.evaluate(() => { SESSION.authenticated = true; });
    await page.locator('.start-wo').click();
    const activeVisual = page.locator('#wo-stage .exercise-visual-protocol');
    await expect(activeVisual).toHaveClass('exercise-visual exercise-visual-protocol is-fallback');
    await expect(activeVisual.locator('img')).toBeHidden();
    const activeSize = await activeVisual.boundingBox();
    expect(activeSize.width).toBe(160); expect(activeSize.height).toBe(120);
    for (let set = 0; set < 2; set++) {
      await page.locator('#wo-reps-in').fill('30');
      await page.locator('button[onclick="completeSet()"]').click();
      if (set === 0) await page.locator('button[onclick="endRest()"]').click();
    }
    await expect.poll(() => posted).toBeTruthy();
    expect(posted.session.execution_state).toBe('completed');
    expect(posted.workout_completion.exercises[0]).toMatchObject({ exercise_id: 'bodyweight.hollow_hold', prescription_type: 'duration', actual_duration_seconds: 30, actual_repetitions: null });
    await expect(page.locator('.wo-summary')).toBeVisible();
  });

  test('missing manifest does not prevent workout controls or neutral fallback', async ({ page }) => {
    await page.route('**/static/exercise/visuals/v1/manifest.js*', route => route.abort());
    await mountWorkout(page, 'en', ['bodyweight.push_up']);
    await expect(page.locator('.workout-exercise-card .exercise-visual.is-fallback')).toHaveCount(1);
    await page.locator('.start-wo').click();
    await expect(page.locator('#wo-stage .exercise-visual-protocol.is-fallback')).toHaveCount(1);
    await expect(page.locator('button[onclick="completeSet()"]')).toBeEnabled();
    await page.evaluate(() => quitWorkout());
  });

  test('pending image transport cannot delay SSE done, cards or workout controls', async ({ page }) => {
    let releaseImages, imageRequested;
    const blocked = new Promise(resolve => { releaseImages = resolve; });
    const requested = new Promise(resolve => { imageRequested = resolve; });
    await page.route('**/static/exercise/visuals/v1/*.webp', async route => {
      imageRequested();
      await blocked;
      await route.abort();
    });
    try {
      await mountWorkout(page, 'en', ['bodyweight.hollow_hold']);
      await requested;
      const result = await page.evaluate(async () => {
        const completion = pendingTrainingCompletion;
        const name = completion.sessions[0].exercises[0].display_name;
        const text = '| Exercise | Sets | Reps | Rest |\n| --- | --- | --- | --- |\n| ' + name + ' | 2 | 20-40 sec | 60 |';
        document.getElementById('feed').innerHTML = '';
        ChatLifecycle.current = null;
        const originalFetch = window.fetch;
        window.fetch = (url, options) => url === '/chat'
          ? Promise.resolve(new Response([
            { training_completion: completion }, { t: text }, { done: true }
          ].map(event => 'data: ' + JSON.stringify(event) + '\n\n').join(''), {
            headers: { 'content-type': 'text/event-stream' }
          })) : originalFetch(url, options);
        try {
          document.getElementById('user-in').value = 'Build my workout';
          await send();
          return { state: ChatLifecycle.current.state, completion: pendingTrainingCompletion };
        } finally {
          window.fetch = originalFetch;
        }
      });
      expect(result.state).toBe('COMPLETED');
      expect(result.completion.sessions[0].exercises[0].exercise_id).toBe('bodyweight.hollow_hold');
      await expect(page.locator('.workout-exercise-card')).toHaveCount(1);
      await expect(page.locator('.typing')).toHaveCount(0);
      await page.locator('.start-wo').click();
      await expect(page.locator('button[onclick="completeSet()"]')).toBeEnabled();
      expect(await page.locator('#wo-stage .exercise-visual img').evaluate(image => image.complete)).toBe(false);
      await page.evaluate(() => quitWorkout());
    } finally {
      releaseImages();
    }
  });

  test('visuals request local assets only and never request camera or microphone', async ({ page }) => {
    const imageRequests = [], errors = [];
    page.on('request', request => { if (request.resourceType() === 'image') imageRequests.push(request.url()); });
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      window.mediaCalls = 0;
      if (navigator.mediaDevices) navigator.mediaDevices.getUserMedia = () => {
        window.mediaCalls++;
        return Promise.reject(new Error('media access is forbidden'));
      };
    });
    await mountWorkout(page);
    for (const image of await page.locator('.exercise-visual img').all()) await expectLoaded(image);
    await page.locator('.start-wo').click();
    await expectLoaded(page.locator('#wo-stage .exercise-visual img'));
    expect(imageRequests.filter(url => new URL(url).origin !== new URL(page.url()).origin)).toEqual([]);
    expect(imageRequests.some(url => url.includes('pushup-holo'))).toBe(false);
    expect(await page.evaluate(() => window.mediaCalls)).toBe(0);
    expect(errors).toEqual([]);
    await expect(page.locator('#core')).toHaveCount(1);
    await page.evaluate(() => quitWorkout());
  });

  for (const language of ['bg', 'en']) {
    for (const width of [390, 360]) {
      test(`${language} cards and active protocol fit ${width}px without overflow`, async ({ page }) => {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 800 });
        await mountWorkout(page, language);
        for (const image of await page.locator('.exercise-visual img').all()) await expectLoaded(image);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        const boxes = await page.locator('.workout-card-hero').evaluateAll(heroes => heroes.map(hero => {
          const bounds = hero.getBoundingClientRect();
          return [...hero.querySelectorAll('.exercise-visual, .ex-name, .ex-diff')].every(element => {
            const rect = element.getBoundingClientRect();
            return rect.left >= bounds.left && rect.right <= bounds.right + 1;
          });
        }));
        expect(boxes).toEqual([true, true, true, true, true]);
        await page.locator('.start-wo').click();
        await expectLoaded(page.locator('#wo-stage .exercise-visual img'));
        await expect(page.locator('button[onclick="completeSet()"]')).toBeInViewport();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.evaluate(() => quitWorkout());
      });
    }
  }
});

test.describe('beginner Movement Studies pack', () => {
  test('canonical manifest entries resolve to local WebP files with exact dimensions', async ({ page, request }) => {
    await page.goto('/app');
    const entries = await page.evaluate(ids => ids.map(id => ApexExerciseVisuals.resolve(id)), beginnerExerciseIds);
    for (const [index, id] of beginnerExerciseIds.entries()) {
      const entry = entries[index];
      expect(entry.exercise_id).toBe(id);
      expect(entry.alt.bg).not.toBe('');
      expect(entry.alt.en).not.toBe('');
      expect(entry.alt.bg).not.toBe(entry.alt.en);
      for (const [variant, dimensions] of [['thumb', [320, 240]], ['protocol', [960, 720]]]) {
        const src = assetPath(id, variant);
        expect(entry[variant]).toBe(src);
        const bytes = fs.readFileSync(path.join(__dirname, '../..', src));
        expect(bytes.subarray(0, 4).toString()).toBe('RIFF');
        expect(bytes.subarray(8, 12).toString()).toBe('WEBP');
        const response = await request.get(src);
        expect(response.status()).toBe(200);
        expect(Buffer.compare(await response.body(), bytes)).toBe(0);
        expect(await page.evaluate(async src => {
          const image = new Image();
          image.src = src;
          await image.decode();
          return [image.naturalWidth, image.naturalHeight];
        }, src)).toEqual(dimensions);
      }
    }
    expect(await page.evaluate(ids => ids.flatMap(id => [
      ApexExerciseVisuals.resolve(id.split('.')[1]),
      ApexExerciseVisuals.resolve(id.toUpperCase()),
      ApexExerciseVisuals.resolve({ exercise_id: id })
    ]), beginnerExerciseIds)).toEqual(Array(15).fill(null));
    expect(await page.evaluate(() => ApexExerciseVisuals.version)).toBe('1');
  });

  for (const language of ['bg', 'en']) {
    test(`all five beginner cards and protocol visuals render without fallback in ${language}`, async ({ page }) => {
      await mountWorkout(page, language, beginnerExerciseIds);
      const cards = page.locator('.workout-exercise-card');
      await expect(cards).toHaveCount(5);
      for (const [index, id] of beginnerExerciseIds.entries()) {
        const visual = cards.nth(index).locator('.exercise-visual');
        await expect(visual).not.toHaveClass(/is-fallback/);
        await expect(visual).toHaveAttribute('data-exercise-visual-id', id);
        const image = visual.locator('img');
        await expect(image).toHaveAttribute('src', assetPath(id, 'thumb'));
        await expect(image).toHaveAttribute('loading', 'lazy');
        await expect(image).toHaveAttribute('alt', await page.evaluate(({ id, language }) => ApexExerciseVisuals.resolve(id).alt[language], { id, language }));
        await expectLoaded(image);
        expect(await image.evaluate(image => [image.naturalWidth, image.naturalHeight])).toEqual([320, 240]);
      }
      const completionBefore = await page.evaluate(() => JSON.stringify(renderedWorkoutExercises['visual-session'].map(exercise => exercise.completion)));
      await page.locator('.start-wo').click();
      for (const [index, id] of beginnerExerciseIds.entries()) {
        await page.evaluate(index => { WO.i = index; WO.set = 0; renderWO(); }, index);
        const visual = page.locator('#wo-stage > .exercise-visual-protocol');
        await expect(visual).not.toHaveClass(/is-fallback/);
        await expect(visual).toHaveAttribute('data-exercise-visual-id', id);
        await expect(visual.locator('img')).toHaveAttribute('src', assetPath(id, 'protocol'));
        await expect(visual.locator('img')).toHaveAttribute('loading', 'eager');
        await expectLoaded(visual.locator('img'));
        expect(await visual.locator('img').evaluate(image => [image.naturalWidth, image.naturalHeight])).toEqual([960, 720]);
        await expect(page.locator('button[onclick="completeSet()"]')).toBeEnabled();
      }
      expect(await page.evaluate(() => JSON.stringify(WO.ex.map(exercise => exercise.completion)))).toBe(completionBefore);
      await page.evaluate(() => quitWorkout());
    });

    for (const width of [390, 360]) {
      test(`${language} beginner pack fits ${width}px in cards and protocol`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 800 });
        await mountWorkout(page, language, beginnerExerciseIds);
        const heroes = page.locator('.workout-card-hero');
        for (let index = 0; index < beginnerExerciseIds.length; index++) {
          const hero = heroes.nth(index);
          await expectLoaded(hero.locator('img'));
          expect(await hero.evaluate(hero => {
            const bounds = hero.getBoundingClientRect();
            return [...hero.querySelectorAll('.exercise-visual, .ex-name, .ex-diff')].every(element => {
              const rect = element.getBoundingClientRect();
              return rect.left >= bounds.left && rect.right <= bounds.right + 1
                && element.scrollWidth <= element.clientWidth + 1;
            });
          })).toBe(true);
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await heroes.first().scrollIntoViewIfNeeded();
        await page.screenshot({ path: testInfo.outputPath(`beginner-${language}-${width}-cards.png`) });
        await page.locator('.start-wo').click();
        for (let index = 0; index < beginnerExerciseIds.length; index++) {
          await page.evaluate(index => { WO.i = index; WO.set = 0; renderWO(); }, index);
          const image = page.locator('#wo-stage > .exercise-visual-protocol img');
          await expectLoaded(image);
          await expect(image).toBeInViewport();
          await expect(page.locator('button[onclick="completeSet()"]')).toBeInViewport();
          expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        }
        await page.screenshot({ path: testInfo.outputPath(`beginner-${language}-${width}-protocol.png`) });
        await page.evaluate(() => quitWorkout());
      });
    }
  }

  test('beginner display names without completion identity and unknown IDs remain fallback', async ({ page }) => {
    await mountWorkout(page, 'en', beginnerExerciseIds);
    const markup = await page.evaluate(() => {
      const labels = { easy: 'Easy', med: 'Medium', hard: 'Hard' };
      const exercises = renderedWorkoutExercises['visual-session'];
      return exercises.flatMap(exercise => [
        renderWorkoutExerciseCard({ ...exercise, completion: undefined }, labels),
        renderWorkoutExerciseCard({ ...exercise, completion: { ...exercise.completion, exercise_id: 'bodyweight.unmapped' } }, labels)
      ]);
    });
    for (const card of markup) {
      expect(card).toContain('exercise-visual is-fallback');
      expect(card).toContain('aria-hidden="true"');
      expect(card).not.toContain('<img');
    }
  });
});

const { test, expect } = require('@playwright/test');

/**
 * Regression coverage for the CURRENT approved APEX app shell.
 *
 * The previous spec asserted a removed "V2 Coach Card" interface
 * (#workout-overlay / cc-active / Biological Core legacy fallback). Those
 * elements no longer exist in the approved shell, so this file replaces that
 * obsolete check with coverage of the interface that ships today:
 *   - the workout renderer (exercise cards),
 *   - the nutrition parser (separator-less plans, no raw pipes),
 *   - nutrition readability (full macro words + units),
 *   - the voice UI (mic button, state-machine markup, voice selector),
 *   - mobile: no horizontal overflow.
 *
 * Content is injected through the app's own render pipeline (renderMarkdown),
 * exactly as a real AI reply would arrive — no production UI is modified.
 */
test.describe('APEX approved app shell — UX regression', () => {
  let consoleErrors = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors = [];
    page.on('pageerror', (e) => consoleErrors.push(e.message || String(e)));
    // ?lang=bg pins the app to Bulgarian (applyIntent reads it), so the bilingual
    // renderers emit the approved BG labels the assertions below check.
    await page.goto('/app?lang=bg');
    // Enter the consultation view and dismiss onboarding so the chat log + composer exist.
    await page.evaluate(() => {
      try {
        ownedStorageSet('apexProfile', JSON.stringify({
          goal: 'fat_loss', age: '30', weight: '75', height: '178',
          gender: 'male', level: 'beginner', equip: 'full_gym'
        }));
      } catch (e) {}
      try { if (typeof enterConsult === 'function') enterConsult(''); } catch (e) {}
      const m = document.getElementById('profile-modal');
      if (m) m.classList.remove('on');
    });
  });

  test('WO-1: workout cards render with exercise name, sets and reps', async ({ page }) => {
    await page.evaluate(() => {
      const md = [
        '| Упражнение | Серии | Повторения | Почивка |',
        '| --- | --- | --- | --- |',
        '| Лицеви опори | 3 | 12 | 60 |',
        '| Клекове | 3 | 15 | 60 |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });

    // 1. cards render
    const cards = page.locator('.ex-card');
    await expect(cards).toHaveCount(2);

    // 2. exercise name is visible
    const firstName = page.locator('.ex-card').first().locator('.ex-name');
    await expect(firstName).toBeVisible();
    await expect(firstName).toHaveText('\u041b\u0438\u0446\u0435\u0432\u0430 \u043e\u043f\u043e\u0440\u0430');

    // 3. sets AND reps are visible on the card
    const firstStats = page.locator('.ex-card').first().locator('.workout-card-stats');
    await expect(firstStats).toContainText('3');            // sets value
    await expect(firstStats).toContainText(/серии|sets/i);
    await expect(firstStats).toContainText('12');           // reps value
    await expect(firstStats).toContainText(/повт|reps/);

    // approved workout entry point is present
    await expect(page.locator('.start-wo')).toBeVisible();
  });

  test('WO-1B: classic muscle-group glyphs contain no exercise SVG and never request camera access', async ({ page }) => {
    await page.evaluate(() => {
      window.__cameraCalls = 0;
      if (navigator.mediaDevices) {
        navigator.mediaDevices.getUserMedia = () => {
          window.__cameraCalls += 1;
          return Promise.reject(new Error('camera must not be requested'));
        };
      }
      const md = [
        '| Exercise | Sets | Reps | Rest |',
        '| --- | --- | --- | --- |',
        '| Pull-up | 3 | 8 | 60 |',
        '| \u041d\u0430\u0431\u0438\u0440\u0430\u043d\u0438\u044f | 3 | 8 | 60 |',
        '| Overhead Press | 3 | 8 | 60 |',
        '| \u0420\u0430\u043c\u0435\u043d\u043d\u0430 \u043f\u0440\u0435\u0441\u0430 | 3 | 8 | 60 |',
        '| Goblet Squat | 3 | 8 | 60 |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });

    const cards = page.locator('.ex-card');
    await expect(cards).toHaveCount(5);
    await expect(cards.locator('svg')).toHaveCount(0);
    await expect(cards.locator('[data-exercise-figure]')).toHaveCount(0);
    await expect(cards.nth(0).locator('.ex-glyph')).toHaveCount(1);
    await expect(cards.nth(2).locator('.ex-glyph')).toHaveCount(1);
    await expect(cards.nth(4).locator('.ex-glyph')).toHaveCount(1);
    await expect(page.locator('[data-camera-hr], [aria-label*="pulse" i], [aria-label*="heart" i]')).toHaveCount(0);

    await page.locator('.start-wo').click();
    await expect(page.locator('#wo-stage > .wo-ex-glyph')).toHaveCount(1);
    await expect(page.locator('#wo-stage > .wo-ex-glyph svg')).toHaveCount(0);
    await page.evaluate(() => { WO.i = 2; WO.set = 0; renderWO(); });
    await expect(page.locator('#wo-stage > .wo-ex-glyph')).toHaveCount(1);
    await expect(page.locator('#wo-stage > .wo-ex-glyph svg')).toHaveCount(0);
    expect(await page.evaluate(() => window.__cameraCalls)).toBe(0);
    await page.evaluate(() => quitWorkout());
  });

  test('WO-1C: initial workout renders one polished instruction card per exercise', async ({ page }) => {
    const networkCalls = await page.evaluate(async () => {
      const originalFetch = window.fetch;
      let calls = 0;
      window.fetch = (...args) => { calls += 1; return originalFetch(...args); };
      const md = [
        '| Exercise | Sets | Reps | Rest |',
        '| --- | --- | --- | --- |',
        '| Goblet Squat | 3 | 8–12 | 60 sec |',
        '| Push-up | 3 | 8–12 | 60 sec |',
        '| Inverted Row Under Table | 3 | 8–12 | 60 sec |',
        '| Dumbbell Romanian Deadlift | 3 | 8–12 | 60 sec |',
        '| Front Plank | 2 | 8–12 | 45 sec |'
      ].join('\n');
      const workout = appendCoach();
      workout.innerHTML = renderMarkdown(md);
      return calls;
    });

    await expect(page.locator('.start-wo')).toHaveCount(1);
    await expect(page.locator('.workout-protocol')).toHaveCount(1);
    const cards = page.locator('.workout-protocol .workout-exercise-card');
    await expect(cards).toHaveCount(5);
    await expect(cards.nth(0)).toContainText('\u0413\u043e\u0431\u043b\u0435\u0442 \u043a\u043b\u0435\u043a');
    await expect(cards.nth(1)).toContainText('\u041b\u0438\u0446\u0435\u0432\u0430 \u043e\u043f\u043e\u0440\u0430');
    await expect(cards.nth(2)).toContainText('\u0413\u0440\u0435\u0431\u0430\u043d\u0435 \u043f\u043e\u0434 \u0441\u0442\u0430\u0431\u0438\u043b\u043d\u0430 \u043c\u0430\u0441\u0430');
    await expect(cards.nth(3)).toContainText('\u0420\u0443\u043c\u044a\u043d\u0441\u043a\u0430 \u0442\u044f\u0433\u0430 \u0441 \u0434\u044a\u043c\u0431\u0435\u043b\u0438');
    await expect(cards.nth(4)).toContainText('\u041f\u0440\u0435\u0434\u0435\u043d \u043f\u043b\u0430\u043d\u043a');
    await expect(cards.nth(0)).toContainText('Дръж един дъмбел вертикално');
    await expect(cards.nth(0)).toContainText('Начална позиция');
    await expect(cards.nth(0)).toContainText('Изпълнение');
    await expect(cards.nth(0)).toContainText('Дишане');
    await expect(cards.nth(0)).toContainText('Ключови насоки');
    await expect(cards.nth(0)).toContainText('Чести грешки');
    await expect(cards.nth(0)).toContainText('По-лесен вариант');
    await expect(cards.nth(0)).toContainText('Безопасност');
    await expect(cards.nth(1)).toContainText('30–45 градуса');
    await expect(cards.nth(2)).toContainText('нестабилна, лека или стъклена маса');
    await expect(cards.nth(3)).not.toContainText('С мента в коленете');
    await expect(cards.nth(4)).toContainText('20–40 сек');
    await expect(cards.nth(4)).not.toContainText('8–12 повт.');
    await expect(cards.first().locator('details')).toHaveCount(5);
    expect(networkCalls).toBe(0);
    await expect(page.locator('.exercise-instructions')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });

  test('WO-1D: technique follow-up opens the existing workout cards without duplication', async ({ page }) => {
    const networkCalls = await page.evaluate(async () => {
      const originalFetch = window.fetch;
      let calls = 0;
      window.fetch = (...args) => { calls += 1; return originalFetch(...args); };
      const md = '| Exercise | Sets | Reps | Rest |\n| --- | --- | --- | --- |\n| Front Plank | 2 | 8–12 | 45 sec |';
      const workout = appendCoach();
      workout.innerHTML = renderMarkdown(md);
      startWorkout();
      const active = WO;
      document.getElementById('user-in').value = 'Explain each exercise';
      await send();
      window.__sameActiveWorkout = WO === active && WO.i === 0 && WO.phase === 'work';
      return calls;
    });
    await expect(page.locator('.workout-protocol')).toHaveCount(1);
    await expect(page.locator('.workout-protocol .workout-exercise-card')).toHaveCount(1);
    await expect(page.locator('.workout-protocol')).toContainText('20–40 сек');
    await expect(page.locator('.workout-protocol details[open]')).toHaveCount(5);
    await expect(page.locator('.exercise-instructions')).toHaveCount(0);
    await expect(page.locator('.start-wo')).toHaveCount(1);
    expect(networkCalls).toBe(0);
    expect(await page.evaluate(() => window.__sameActiveWorkout)).toBe(true);
    await page.evaluate(() => quitWorkout());
  });

  test('WO-MED-1: medical hold suspends the current workout and survives authenticated session restore', async ({ page }) => {
    await page.evaluate(async () => {
      const workout = appendCoach();
      workout.innerHTML = renderMarkdown([
        '| Exercise | Sets | Reps | Rest |',
        '| --- | --- | --- | --- |',
        '| Goblet Squat | 3 | 8 | 60 sec |'
      ].join('\n'));

      const originalFetch = window.fetch;
      window.fetch = async (url) => {
        if (url === '/chat') {
          return new Response([
            'data: {"medical_hold":true,"workout_suspended":true}',
            '',
            'data: {"t":"medical safety"}',
            '',
            'data: {"done":true}',
            '',
            ''
          ].join('\n'), { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
        }
        if (url === '/auth/me') {
          return new Response(JSON.stringify({ authenticated: true, plan: 'free', status: 'free', email: 'medical@example.test' }), { status: 200 });
        }
        if (url === '/api/profile') {
          return new Response(JSON.stringify({ profile: { _medical_hold: { status: 'ACTIVE_MEDICAL_HOLD' } } }), { status: 200 });
        }
        if (url === '/api/history') return new Response(JSON.stringify({ workouts: [] }), { status: 200 });
        if (url.startsWith('/api/conversations')) return new Response(JSON.stringify({ messages: [] }), { status: 200 });
        return originalFetch(url);
      };

      document.getElementById('user-in').value = '\u0431\u043e\u043b\u0438 \u043c\u0435 \u043b\u044f\u0432\u043e\u0442\u043e \u0440\u0430\u043c\u043e, \u0446\u044f\u043b\u0430\u0442\u0430 \u043c\u0438 \u0440\u044a\u043a\u0430 \u0438\u0437\u0442\u0440\u044a\u043f\u0432\u0430';
      await send();
      window.__medicalHoldAfterSse = medicalHoldActive;
      window.__medicalHoldPersisted = pfLoad()._medical_hold && pfLoad()._medical_hold.status;
      await loadSession();
      window.__medicalHoldAfterRestore = medicalHoldActive;
      window.fetch = originalFetch;
    });

    expect(await page.evaluate(() => window.__medicalHoldAfterSse)).toBe(true);
    expect(await page.evaluate(() => window.__medicalHoldPersisted)).toBe('ACTIVE_MEDICAL_HOLD');
    expect(await page.evaluate(() => window.__medicalHoldAfterRestore)).toBe(true);
    await expect(page.locator('.start-wo')).toBeHidden();
    await expect(page.locator('.workout-protocol')).toHaveCount(1);
    await expect(page.locator('#feed')).toContainText('medical safety');
    await page.evaluate(() => startWorkout());
    await expect(page.locator('#workout')).not.toHaveClass(/on/);
  });

  test('WO-1A: safe starter fallback keeps workout cards, rest and progression', async ({ page }) => {
    await page.evaluate(() => {
      const md = [
        '**Начална тренировка · 15 минути**',
        '| Упражнение | Серии | Повторения | Почивка | Бележка |',
        '| --- | --- | --- | --- | --- |',
        '| Леко ходене на място | 1 | 3 минути | 30 сек | Спокойно темпо |',
        '| Клек до стол | 2 | 6–8 | 60 сек | Контролиран обхват |',
        '| Лицеви опори на стена | 2 | 6–8 | 60 сек | Дръж тялото подравнено |',
        '| Глутеус мост | 2 | 8 | 60 сек | Кратка пауза горе |',
        '| Bird-dog | 2 | 6 на страна | 60 сек | Дръж торса стабилен |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });

    await expect(page.locator('.ex-card')).toHaveCount(5);
    await expect(page.locator('.start-wo')).toHaveCount(1);
    await page.locator('.start-wo').click();
    await expect(page.locator('#workout')).toHaveClass(/on/);
    await expect(page.locator('#wo-ptop-l')).toContainText('1/5');

    await page.evaluate(() => completeSet());
    await expect(page.locator('#rt-n')).toBeVisible();
    expect(await page.evaluate(() => WO.phase)).toBe('rest');

    await page.evaluate(() => {
      endRest();
      quitWorkout();
    });
  });

  test('WO-2: completion submits only blueprint-issued workout identifiers', async ({ page }) => {
    const posted = await page.evaluate(async () => {
      const projection = {
        plan_id: 'plan-test', plan_version: 'v2', sessions: [{
          session_id: 'session-test', session_index: 1, exercises: [{
            prescription_id: 'prescription-test', exercise_id: 'exercise.push_up',
            exercise_version: '1.0.0', display_name: 'Push-up', prescribed_sets: 1,
            rep_min: 8, rep_max: 12, rest_seconds: 60
          }]
        }]
      };
      pendingTrainingCompletion = projection;
      pendingCompletionSessions = projection.sessions.slice();
      const el = appendCoach();
      el.innerHTML = renderMarkdown([
        '| Exercise | Sets | Reps | Rest | Note |',
        '| --- | --- | --- | --- | --- |',
        '| Push-up | 1 | 8-12 | 60 | controlled |'
      ].join('\n'));
      let sent = null;
      const originalFetch = window.fetch;
      window.fetch = async (url, options) => {
        if (url === '/api/workout') { sent = JSON.parse(options.body); return new Response('{}', { status: 200 }); }
        return originalFetch(url, options);
      };
      SESSION.authenticated = true;
      startWorkout('session-test');
      completeSet();
      await new Promise((resolve) => setTimeout(resolve, 0));
      window.fetch = originalFetch;
      return sent;
    });

    expect(posted.workout_completion).toMatchObject({
      plan_id: 'plan-test', plan_version: 'v2', session_id: 'session-test',
      exercises: [{ prescription_id: 'prescription-test', exercise_id: 'exercise.push_up', exercise_version: '1.0.0' }]
    });
    expect(posted.workout_completion.exercises[0]).not.toHaveProperty('name');
  });

  test('WO-3: a traceable completion asks /chat for the next deterministic workout revision', async ({ page }) => {
    const posted = await page.evaluate(async () => {
      const projection = {
        plan_id: 'plan-next', plan_version: 'v2', sessions: [{
          session_id: 'session-next', session_index: 1, exercises: [{
            prescription_id: 'prescription-next', exercise_id: 'exercise.push_up',
            exercise_version: '1.0.0', display_name: 'Push-up', prescribed_sets: 1,
            rep_min: 8, rep_max: 12, rest_seconds: 60
          }]
        }]
      };
      pendingTrainingCompletion = projection;
      pendingCompletionSessions = projection.sessions.slice();
      const el = appendCoach();
      el.innerHTML = renderMarkdown('| Exercise | Sets | Reps | Rest |\n| --- | --- | --- | --- |\n| Push-up | 1 | 8-12 | 60 |');
      const originalFetch = window.fetch;
      let chat = null;
      window.fetch = async (url, options) => {
        if (url === '/api/workout') return new Response('{}', { status: 200 });
        if (url === '/chat') {
          chat = JSON.parse(options.body);
          return new Response('data: {"done":true}\n\n', {
            status: 200, headers: { 'content-type': 'text/event-stream' }
          });
        }
        return originalFetch(url, options);
      };
      SESSION.authenticated = true;
      startWorkout('session-next');
      completeSet();
      finishToCoach();
      await new Promise((resolve) => setTimeout(resolve, 350));
      window.fetch = originalFetch;
      return chat;
    });

    expect(posted.message).toBe('Следваща тренировка.');
    expect(posted.completed_workout).toMatchObject({
      plan_id: 'plan-next', plan_version: 'v2', session_id: 'session-next',
      exercises: [{ prescription_id: 'prescription-next', exercise_id: 'exercise.push_up' }]
    });
    expect(posted.recovery).toMatchObject({ source_version: 'browser-recovery-v1' });
  });

  test('WO-3A: legacy completion sends the completed exercises for post-workout coaching', async ({ page }) => {
    const posted = await page.evaluate(async () => {
      const originalFetch = window.fetch;
      let chat = null;
      window.fetch = async (url, options) => {
        if (url === '/chat') {
          chat = JSON.parse(options.body);
          return new Response('data: {"t":"Recovery noted."}\n\ndata: {"done":true}\n\n', {
            status: 200, headers: { 'content-type': 'text/event-stream' }
          });
        }
        return originalFetch(url, options);
      };
      WO = {
        ex: [
          { name: 'Squat', sets: '3', reps: '8', weight: '60', completedSets: 3 },
          { name: 'Row', sets: '2', reps: '10', weight: '', completedSets: 2 }
        ], contract: null, i: 1, set: 2, phase: 'work'
      };
      sessionStart = Date.now() - 20 * 60000;
      finishWorkout();
      finishToCoach();
      await new Promise((resolve) => setTimeout(resolve, 350));
      window.fetch = originalFetch;
      return chat;
    });

    expect(posted.message).toBe('Завърших я.');
    expect(posted.completed_workout).toMatchObject({
      completion: 100,
      exercises: [
        { name: 'Squat', completed_sets: 3, completed_repetitions: 8, completed_load: 60 },
        { name: 'Row', completed_sets: 2, completed_repetitions: 10, completed_load: null }
      ]
    });
    expect(posted.completed_workout).not.toHaveProperty('plan_id');
  });

  test('NP-1: nutrition parser recognizes a separator-less plan with no raw pipes', async ({ page }) => {
    await page.evaluate(() => {
      // A nutrition table WITHOUT the markdown separator row — the parser
      // (separatorlessNutritionBlock / pipeCells) must recognize it and render cards.
      const md = [
        'Закуска | 30 | 45 | 12 | 320',
        'Обяд | 40 | 55 | 15 | 520'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });

    // 4. parser produced nutrition cards (not raw markdown text)
    const nutri = page.locator('.nutri').first();
    await expect(page.locator('.nutri-meal').first()).toBeVisible();
    await expect(page.locator('.nutri-meal')).toHaveCount(2);

    // 8. NO raw pipe symbols remain in the recognized plan
    const nutriText = await nutri.innerText();
    expect(nutriText).not.toContain('|');
  });

  test('NP-1A: meal reasons remain inside their nutrition cards', async ({ page }) => {
    await page.evaluate(() => {
      const md = [
        '| Meal | Food | Quantity | Protein | Carbs | Fat | Calories | Why this meal |',
        '| --- | --- | --- | --- | --- | --- | --- | --- |',
        '| Breakfast | Eggs | 200 g | 40 | 0 | 20 | 340 | Starts the day toward your protein target. |',
        '| Lunch | Chicken | 200 g | 70 | 0 | 15 | 500 | Keeps protein on track for your daily target. |',
        '| Dinner | Salmon | 200 g | 65 | 0 | 28 | 600 | Completes the day within your target. |',
        '| Daily Total | | | 175 | 0 | 63 | 1440 | |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });

    await expect(page.locator('.nutri-meal')).toHaveCount(3);
    await expect(page.locator('.nm-reason')).toHaveCount(3);
    await expect(page.locator('.nm-reason').first()).toContainText('protein target');
    await expect(page.locator('.nm-reason').nth(1)).toContainText('daily target');
  });

  test('NP-1A1: meal titles use deterministic ingredient icons', async ({ page }) => {
    await page.evaluate(() => {
      const md = [
        '| Meal | Food | Quantity | Protein | Carbs | Fat | Calories |',
        '| --- | --- | --- | --- | --- | --- | --- |',
        '| Breakfast | Oats | 80 g | 10 | 45 | 6 | 280 |',
        '| Lunch | Chicken Breast | 180 g | 45 | 0 | 5 | 260 |',
        '| Snack | Apple | 150 g | 0 | 20 | 0 | 90 |',
        '| Daily Total | | | 55 | 65 | 11 | 630 |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });

    await expect(page.locator('.nutri-title .nm-meal-icon')).toHaveCount(3);
    await expect(page.locator('.nutri-title .nm-meal-icon svg')).toHaveCount(3);
  });

  test('NP-1A2: Bulgarian canonical Food column preserves foods and meal icons', async ({ page }) => {
    await page.evaluate(() => {
      const md = [
        '| Хранене | Храна | Количество | Белтъчини (g) | Въглехидрати (g) | Мазнини (g) | Ккал | Защо това хранене |',
        '| --- | --- | --- | --- | --- | --- | --- | --- |',
        '| Закуска | Овесени ядки | 80 г | 10 | 45 | 6 | 280 | За енергия сутрин. |',
        '| Общо | | | 10 | 45 | 6 | 280 | |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });

    await expect(page.locator('.nutri-title .nm-name')).toHaveText('Закуска');
    await expect(page.locator('.nutri-title .nm-meal-icon')).toHaveCount(1);
    await expect(page.locator('.nutri-meal').filter({ hasText: 'Овесени ядки' })).toHaveCount(1);
  });

  test('NP-1B: matched recipes render as collapsed meal-card details', async ({ page }) => {
    await page.evaluate(() => {
      const recipe = 'recipe:' + btoa(JSON.stringify({
        id: 'breakfast-eggs-oats', meal_id: 'meal-breakfast', title: 'Egg omelette', difficulty: 'easy', minutes: 12,
        steps: ['Whisk eggs.', 'Cook gently.'], tips: ['Use little oil.'],
        substitutions: ['Use spinach instead of tomato.'], storage: 'Eat fresh.', meal_prep: false
      }));
      const md = [
        '| Meal | Meal ID | Food | Quantity | Protein (g) | Carbs (g) | Fat (g) | Kcal | Why this meal | Recipe |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |',
        '| Breakfast | meal-breakfast | Eggs | 200 g | 40 | 0 | 20 | 340 | Starts the day toward your protein target. | ' + recipe + ' |',
        '| Daily Total | | | | 40 | 0 | 20 | 340 | | |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });

    await expect(page.locator('.nm-recipe')).toHaveCount(4);
    await expect(page.locator('.nm-recipe').first()).not.toHaveAttribute('open', '');
    await expect(page.locator('.nm-recipe-title')).toContainText('Egg omelette');
    await expect(page.locator('.nm-recipe').first()).toContainText('Whisk eggs.');
  });

  test('NP-1C: foods and a recipe stay bound to one meal card', async ({ page }) => {
    await page.evaluate(() => {
      const recipe = 'recipe:' + btoa(JSON.stringify({
        id: 'breakfast-eggs-oats', meal_id: 'meal-breakfast', title: 'Eggs with oats', difficulty: 'easy', minutes: 12,
        steps: ['Cook.'], tips: ['Use little oil.'], substitutions: ['Use spinach.'], storage: 'Eat fresh.', meal_prep: false
      }));
      const md = [
        '| Meal | Meal ID | Food | Quantity | Protein | Carbs | Fat | Calories | Why this meal | Recipe |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |',
        '| Breakfast | meal-breakfast | Eggs | 150 g | 21 | 2 | 14 | 207 | First meal. | ' + recipe + ' |',
        '| | | Oats | 80 g | 10 | 45 | 6 | 280 | | |',
        '| Lunch | meal-lunch | Chicken | 180 g | 45 | 0 | 5 | 260 | Lunch meal. | |',
        '| Daily Total | | | | 76 | 47 | 25 | 747 | | |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });

    const cards = page.locator('.nutri-meal');
    await expect(cards).toHaveCount(2);
    await expect(cards.nth(0)).toContainText('Breakfast');
    await expect(cards.nth(0)).toContainText('Eggs');
    await expect(cards.nth(0)).toContainText('Oats');
    await expect(cards.nth(0).locator('.nm-recipe-title')).toContainText('Eggs with oats');
    await expect(cards.nth(1).locator('.nm-recipe-title')).toHaveCount(0);
    await expect(page.locator('.nutri-total')).toContainText('76');
  });

  test('NP-1D: a recipe token cannot render without an owning meal', async ({ page }) => {
    await page.evaluate(() => {
      const recipe = 'recipe:' + btoa(JSON.stringify({
        id: 'orphan', title: 'Must stay hidden', difficulty: 'easy', minutes: 5,
        steps: ['No.'], tips: ['No.'], substitutions: ['No.'], storage: 'No.', meal_prep: false
      }));
      const md = [
        '| Food | Quantity | Protein | Carbs | Fat | Calories | Recipe |',
        '| --- | --- | --- | --- | --- | --- | --- |',
        '| Eggs | 150 g | 21 | 2 | 14 | 207 | ' + recipe + ' |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });

    await expect(page.locator('.nutri-meal')).toHaveCount(1);
    await expect(page.locator('.nm-recipe-title')).toHaveCount(0);
  });

  test('NP-1E: recipe payloads bind only to their stable meal IDs', async ({ page }) => {
    await page.evaluate(() => {
      const token = (mealId, title) => 'recipe:' + btoa(JSON.stringify({
        id: mealId + '-recipe', meal_id: mealId, title, difficulty: 'easy', minutes: 10,
        steps: ['Cook.'], tips: ['Tip.'], substitutions: ['Swap.'], storage: 'Fresh.', meal_prep: false
      }));
      const breakfast = token('meal-breakfast', 'Breakfast recipe');
      const lunch = token('meal-lunch', 'Lunch recipe');
      const dinner = token('meal-dinner', 'Dinner recipe');
      const md = [
        '| Meal | Meal ID | Food | Quantity | Protein | Carbs | Fat | Calories | Recipe |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- |',
        '| Breakfast | meal-breakfast | Eggs | 150 g | 21 | 2 | 14 | 207 | ' + breakfast + ' |',
        '| Lunch | meal-lunch | Chicken | 180 g | 45 | 0 | 5 | 260 | ' + lunch + ' |',
        '| Dinner | meal-dinner | Salmon | 180 g | 40 | 0 | 18 | 330 | ' + dinner + ' |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });

    const cards = page.locator('.nutri-meal');
    await expect(cards).toHaveCount(3);
    await expect(cards.nth(0).locator('.nm-recipe-title')).toContainText('Breakfast recipe');
    await expect(cards.nth(1).locator('.nm-recipe-title')).toContainText('Lunch recipe');
    await expect(cards.nth(2).locator('.nm-recipe-title')).toContainText('Dinner recipe');
    await expect(cards.nth(0).locator('.nm-recipe')).toHaveCount(4);
  });

  test('NP-1F: a meal with no matching recipe keeps its card and shows the neutral fallback', async ({ page }) => {
    await page.evaluate(() => {
      const md = [
        '| Meal | Meal ID | Food | Quantity | Protein | Carbs | Fat | Calories |',
        '| --- | --- | --- | --- | --- | --- | --- | --- |',
        '| Breakfast | meal-breakfast | Eggs | 150 g | 21 | 2 | 14 | 207 |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });

    const card = page.locator('.nutri-meal');
    await expect(card).toHaveCount(1);
    await expect(card).toContainText('Eggs');
    await expect(card.locator('.nm-recipe-missing')).toHaveCount(1);
    await expect(card.locator('.nm-recipe-missing')).toContainText(/No suitable recipe is available for this meal\.|Няма подходяща рецепта за това хранене\./);
    await expect(card.locator('.nm-recipe')).toHaveCount(0);
  });

  test('NR-1: nutrition readability — full words, units, colour is not the sole signal', async ({ page }) => {
    await page.evaluate(() => {
      const md = [
        '| Ястие | Протеин | Въглехидрати | Мазнини | Калории |',
        '| --- | --- | --- | --- | --- |',
        '| Обяд | 40 | 55 | 15 | 520 |',
        '| Общо | 40 | 55 | 15 | 520 |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });

    const nutri = page.locator('.nutri').first();
    // 5. full macro names + caption
    await expect(nutri).toContainText('Хранителна стойност');
    await expect(nutri).toContainText('Белтъчини');
    await expect(nutri).toContainText('Въглехидрати');
    await expect(nutri).toContainText('Мазнини');
    await expect(nutri).toContainText('Калории');
    // units г / kcal
    await expect(nutri).toContainText('г');
    await expect(nutri).toContainText('kcal');
    // colour is a helper: the WORD label carries meaning (readable without colour perception)
    await expect(page.locator('.macro .mname').first()).toHaveText('Белтъчини');
  });

  test('NR-2: nutrition macro values use whole-number display precision', async ({ page }) => {
    await page.evaluate(() => {
      const md = [
        '| Meal | Protein | Carbs | Fat | Calories |',
        '| --- | --- | --- | --- | --- |',
        '| Lunch | 12.49 | 53.51 | 7.50 | 521.60 |',
        '| Total | 12.49 | 53.51 | 7.50 | 521.60 |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });

    const nutrition = await page.locator('.nutri').first().innerText();
    expect(nutrition).toContain('12');
    expect(nutrition).toContain('54');
    expect(nutrition).toContain('522');
    expect(nutrition).not.toContain('12.49');
    expect(nutrition).not.toContain('53.51');
    expect(nutrition).not.toContain('521.60');
    await expect(page.locator('.nutri').first().locator('.nm-qty')).toHaveCount(0);
  });

  test('NR-3: nutrition quantity is sourced only from semantic serving fields', async ({ page }) => {
    await page.evaluate(() => {
      const serving = [
        '| Meal | Food | Serving Size | Protein | Carbs | Fat | Calories |',
        '| --- | --- | --- | --- | --- | --- | --- |',
        '| Breakfast | Eggs | 80 g | 12.49 | 53.51 | 7.50 | 521.60 |'
      ].join('\n');
      const unknown = [
        '| Meal | Food | Score | Protein | Carbs | Fat | Calories |',
        '| --- | --- | --- | --- | --- | --- | --- |',
        '| Lunch | Chicken | 9.75 | 12.49 | 53.51 | 7.50 | 521.60 |'
      ].join('\n');
      const first = appendCoach();
      first.innerHTML = renderMarkdown(serving);
      const second = appendCoach();
      second.innerHTML = renderMarkdown(unknown);
    });

    const plans = page.locator('.nutri');
    await expect(plans).toHaveCount(2);
    await expect(plans.nth(0).locator('.nm-food-qty')).toHaveText('80 g');
    await expect(plans.nth(1).locator('.nm-food-qty')).toHaveCount(0);
    await expect(plans.nth(1)).not.toContainText('9.75');
  });

  test('VX-1: voice UI — mic button, state-machine markup, voice selector persistence', async ({ page }) => {
    // 6a. mic button present, secondary control with an initial idle state + accessible name
    const mic = page.locator('#mic-btn');
    await expect(mic).toBeVisible();
    await expect(mic).toHaveAttribute('data-state', 'idle');
    await expect(mic).toHaveAttribute('aria-label', /.+/);

    // 6b. state-machine markup: shape-based indicators (not colour-only)
    await expect(mic.locator('.mic-dots')).toHaveCount(1);   // THINKING
    await expect(mic.locator('.mic-wave')).toHaveCount(1);   // SPEAKING
    // send stays the primary, distinct action
    await expect(page.locator('.send-btn')).toBeVisible();

    // deterministic state machine drives data-state
    const speaking = await page.evaluate(() => {
      Voice.set('SPEAKING');
      const s = document.getElementById('mic-btn').getAttribute('data-state');
      Voice.set('IDLE');
      return s;
    });
    expect(speaking).toBe('speaking');

    // 6c. voice selector lives in Settings, persists the choice
    const sel = await page.evaluate(() => {
      showSettings();
      const s = document.getElementById('voice-select');
      const opts = s ? [...s.options].map((o) => o.value) : [];
      let ls = null;
      if (s) { s.value = 'calm'; voicePick('calm'); ls = localStorage.getItem('apexVoice'); }
      if (typeof closePanel === 'function') closePanel();
      VoiceReg.set('alpha');
      return { exists: !!s, opts, ls };
    });
    expect(sel.exists).toBe(true);
    expect(sel.opts).toEqual(expect.arrayContaining(['alpha', 'calm']));
    expect(sel.ls).toBe('calm');
  });

  test('VX-2: spoken turns mark one chat request and speak the separate delivery projection', async ({ page }) => {
    const result = await page.evaluate(async () => {
      const chatPayloads = [];
      let spoken = null;
      const originalFetch = window.fetch;
      const originalSpeak = VoiceOut.speak;
      const originalStop = VoiceIn.stop;
      window.fetch = async (url, options) => {
        if (url === '/chat') {
          chatPayloads.push(JSON.parse(options.body));
          return new Response(
            'data: {"t":"Visible reply"}\n\ndata: {"speech_text":"Voice-safe reply"}\n\ndata: {"done":true}\n\n',
            { headers: { 'content-type': 'text/event-stream' } }
          );
        }
        return originalFetch(url, options);
      };
      VoiceOut.speak = async (text) => { spoken = text; };
      VoiceIn.stop = () => {};
      Voice.on = true;
      Voice._onFinal('spoken request');
      await new Promise((resolve) => setTimeout(resolve, 30));
      Voice.on = false;
      document.getElementById('user-in').value = 'typed request';
      await send();
      window.fetch = originalFetch;
      VoiceOut.speak = originalSpeak;
      VoiceIn.stop = originalStop;
      return { chatPayloads, spoken };
    });

    expect(result.chatPayloads).toHaveLength(2);
    expect(result.chatPayloads[0]).toMatchObject({ message: 'spoken request', voice: true });
    expect(result.chatPayloads[1]).toMatchObject({ message: 'typed request' });
    expect(result.chatPayloads[1]).not.toHaveProperty('voice');
    expect(result.spoken).toBe('Voice-safe reply');
  });

  test('VX-3: voice playback falls back to the visible reply only when projection is absent', async ({ page }) => {
    const spoken = await page.evaluate(() => {
      let delivered = null;
      const originalSay = Voice.say;
      Voice.say = (text) => { delivered = text; };
      Voice.on = true;
      afterReply('Visible fallback');
      Voice.on = false;
      Voice.say = originalSay;
      return delivered;
    });

    expect(spoken).toBe('Visible fallback');
  });

  test('CL-1: lifecycle keeps typing until content and finalizes immediately on done', async ({ page }) => {
    const snapshots = await page.evaluate(async () => {
      ownedStorageRemove('apexHistory');
      document.getElementById('feed').innerHTML = '';
      ChatLifecycle.current = null;
      const originalFetch = window.fetch;
      window.fetch = async () => {
        const enc = new TextEncoder();
        return new Response(new ReadableStream({
          start(controller) {
            setTimeout(() => controller.enqueue(enc.encode('data: {"t":"Visible"}\n\n')), 120);
            setTimeout(() => controller.enqueue(enc.encode('data: {"done":true}\n\n')), 180);
            // Deliberately never close: done must own completion.
          }
        }), { headers: { 'content-type': 'text/event-stream' } });
      };
      document.getElementById('user-in').value = 'Lifecycle';
      const pending = send();
      await new Promise((resolve) => setTimeout(resolve, 40));
      const waiting = {
        state: ChatLifecycle.current.state,
        typing: document.querySelectorAll('.typing').length,
        assistants: document.querySelectorAll('.msg.a').length
      };
      await pending;
      const completed = {
        state: ChatLifecycle.current.state,
        typing: document.querySelectorAll('.typing').length,
        assistants: document.querySelectorAll('.msg.a').length,
        text: document.querySelector('.msg.a .body').textContent,
        history: getHistory()
      };
      window.fetch = originalFetch;
      return { waiting, completed };
    });
    expect(snapshots.waiting).toEqual({ state: 'WAITING_FIRST_TOKEN', typing: 1, assistants: 0 });
    expect(snapshots.completed.state).toBe('COMPLETED');
    expect(snapshots.completed.typing).toBe(0);
    expect(snapshots.completed.assistants).toBe(1);
    expect(snapshots.completed.text).toBe('Visible');
    expect(snapshots.completed.history).toEqual([
      { role: 'user', content: 'Lifecycle' }, { role: 'assistant', content: 'Visible' }
    ]);
  });

  test('CL-2: HTTP failure retries in place without duplicate messages', async ({ page }) => {
    const result = await page.evaluate(async () => {
      ownedStorageRemove('apexHistory');
      document.getElementById('feed').innerHTML = '';
      ChatLifecycle.current = null;
      const originalFetch = window.fetch;
      let calls = 0;
      window.fetch = async () => {
        calls++;
        if (calls === 1) return new Response('{"error":"server_error"}', {
          status: 500, headers: { 'content-type': 'application/json' }
        });
        return new Response('data: {"t":"Recovered"}\n\ndata: {"done":true}\n\n', {
          headers: { 'content-type': 'text/event-stream' }
        });
      };
      const input = document.getElementById('user-in');
      input.value = 'Retry this';
      await send();
      const failed = {
        state: ChatLifecycle.current.state,
        users: document.querySelectorAll('.msg.u').length,
        assistants: document.querySelectorAll('.msg.a').length,
        history: getHistory(), input: input.value
      };
      await send();
      const recovered = {
        state: ChatLifecycle.current.state,
        users: document.querySelectorAll('.msg.u').length,
        assistants: document.querySelectorAll('.msg.a').length,
        history: getHistory()
      };
      window.fetch = originalFetch;
      return { failed, recovered };
    });
    expect(result.failed.state).toBe('FAILED');
    expect(result.failed.users).toBe(1);
    expect(result.failed.assistants).toBe(1);
    expect(result.failed.history).toEqual([{ role: 'user', content: 'Retry this' }]);
    expect(result.failed.input).toBe('Retry this');
    expect(result.recovered.state).toBe('COMPLETED');
    expect(result.recovered.users).toBe(1);
    expect(result.recovered.assistants).toBe(1);
    expect(result.recovered.history).toEqual([
      { role: 'user', content: 'Retry this' }, { role: 'assistant', content: 'Recovered' }
    ]);
  });

  test('CL-3: malformed and interrupted streams never persist partial assistant output', async ({ page }) => {
    const result = await page.evaluate(async () => {
      const reset = () => {
        ownedStorageRemove('apexHistory');
        document.getElementById('feed').innerHTML = '';
        ChatLifecycle.current = null;
      };
      const originalFetch = window.fetch;
      reset();
      window.fetch = async () => new Response('data: not-json\n\n', {
        headers: { 'content-type': 'text/event-stream' }
      });
      document.getElementById('user-in').value = 'Malformed';
      await send();
      const malformed = { state: ChatLifecycle.current.state, history: getHistory() };
      reset();
      window.fetch = async () => {
        const enc = new TextEncoder();
        return new Response(new ReadableStream({
          start(controller) {
            controller.enqueue(enc.encode('data: {"t":"Partial"}\n\n'));
            setTimeout(() => controller.error(new Error('cut')), 20);
          }
        }), { headers: { 'content-type': 'text/event-stream' } });
      };
      document.getElementById('user-in').value = 'Interrupted';
      await send();
      const interrupted = {
        state: ChatLifecycle.current.state,
        assistants: document.querySelectorAll('.msg.a').length,
        visible: document.querySelector('.msg.a .body').textContent,
        history: getHistory()
      };
      window.fetch = originalFetch;
      return { malformed, interrupted };
    });
    expect(result.malformed.state).toBe('FAILED');
    expect(result.malformed.history).toEqual([{ role: 'user', content: 'Malformed' }]);
    expect(result.interrupted.state).toBe('INTERRUPTED');
    expect(result.interrupted.assistants).toBe(1);
    expect(result.interrupted.visible).not.toContain('Partial');
    expect(result.interrupted.history).toEqual([{ role: 'user', content: 'Interrupted' }]);
  });

  test('CL-4: exact stop cancels the owned request without persisting partial output', async ({ page }) => {
    const result = await page.evaluate(async () => {
      ownedStorageRemove('apexHistory');
      document.getElementById('feed').innerHTML = '';
      ChatLifecycle.current = null;
      const originalFetch = window.fetch;
      window.fetch = async () => {
        const enc = new TextEncoder();
        return new Response(new ReadableStream({
          start(controller) { setTimeout(() => controller.enqueue(enc.encode('data: {"t":"Late"}\n\n')), 500); }
        }), { headers: { 'content-type': 'text/event-stream' } });
      };
      const input = document.getElementById('user-in');
      input.value = 'Long request';
      const pending = send();
      await new Promise((resolve) => setTimeout(resolve, 30));
      input.value = 'Спри.';
      await send();
      await pending;
      const snapshot = {
        state: ChatLifecycle.current.state,
        typing: document.querySelectorAll('.typing').length,
        assistants: document.querySelectorAll('.msg.a').length,
        text: document.querySelector('.msg.a .body').textContent,
        history: getHistory(), input: input.value
      };
      window.fetch = originalFetch;
      return snapshot;
    });
    expect(result.state).toBe('CANCELLED');
    expect(result.typing).toBe(0);
    expect(result.assistants).toBe(1);
    expect(result.text).toBe('Заявката е отменена.');
    expect(result.input).toBe('Long request');
    expect(result.history).toEqual([{ role: 'user', content: 'Long request' }]);
  });

  test('CL-8: cancelled retry reuses the request and its single assistant lifecycle', async ({ page }) => {
    const result = await page.evaluate(async () => {
      ownedStorageRemove('apexHistory');
      document.getElementById('feed').innerHTML = '';
      ChatLifecycle.current = null;
      const originalFetch = window.fetch;
      let calls = 0;
      window.fetch = async () => {
        calls++;
        if (calls === 1) {
          return new Response(new ReadableStream({ start() {} }), {
            headers: { 'content-type': 'text/event-stream' }
          });
        }
        return new Response('data: {"t":"Recovered"}\n\ndata: {"done":true}\n\n', {
          headers: { 'content-type': 'text/event-stream' }
        });
      };
      const input = document.getElementById('user-in');
      input.value = 'Original request';
      const first = send();
      await new Promise((resolve) => setTimeout(resolve, 30));
      input.value = 'Stop';
      await send();
      await first;
      const cancelled = {
        state: ChatLifecycle.current.state, attempt: ChatLifecycle.current.attempt,
        input: input.value, requestId: document.querySelector('.msg.a').dataset.requestId,
        users: document.querySelectorAll('.msg.u').length,
        assistants: document.querySelectorAll('.msg.a').length
      };
      await send();
      const completed = {
        state: ChatLifecycle.current.state, attempt: ChatLifecycle.current.attempt,
        requestId: document.querySelector('.msg.a').dataset.requestId,
        users: document.querySelectorAll('.msg.u').length,
        assistants: document.querySelectorAll('.msg.a').length,
        text: document.querySelector('.msg.a .body').textContent,
        history: getHistory(), calls
      };
      window.fetch = originalFetch;
      return { cancelled, completed };
    });
    expect(result.cancelled).toMatchObject({
      state: 'CANCELLED', attempt: 1, input: 'Original request', users: 1, assistants: 1
    });
    expect(result.completed).toMatchObject({
      state: 'COMPLETED', attempt: 2, users: 1, assistants: 1, text: 'Recovered', calls: 2
    });
    expect(result.completed.requestId).toBe(result.cancelled.requestId);
    expect(result.completed.history).toEqual([
      { role: 'user', content: 'Original request' }, { role: 'assistant', content: 'Recovered' }
    ]);
  });

  test('CL-9: quota exhaustion owns one failed terminal assistant message', async ({ page }) => {
    const result = await page.evaluate(async () => {
      ownedStorageRemove('apexHistory');
      document.getElementById('feed').innerHTML = '';
      ChatLifecycle.current = null;
      const originalFetch = window.fetch;
      window.fetch = async () => new Response(
        'data: {"limit_reached":true,"hours_left":4}\n\n',
        { headers: { 'content-type': 'text/event-stream' } }
      );
      document.getElementById('user-in').value = 'Quota request';
      await send();
      const snapshot = {
        state: ChatLifecycle.current.state,
        assistants: document.querySelectorAll('.msg.a').length,
        typing: document.querySelectorAll('.typing').length,
        text: document.querySelector('.msg.a .body').textContent,
        history: getHistory()
      };
      window.fetch = originalFetch;
      return snapshot;
    });
    expect(result.state).toBe('FAILED');
    expect(result.assistants).toBe(1);
    expect(result.typing).toBe(0);
    expect(result.text).toBe('Достигна безплатния лимит за днес');
    expect(result.history).toEqual([{ role: 'user', content: 'Quota request' }]);
  });

  test('CL-10: a coalesced large stream paints progressively without full-buffer reparsing', async ({ page }) => {
    const result = await page.evaluate(async () => {
      ownedStorageRemove('apexHistory');
      document.getElementById('feed').innerHTML = '';
      ChatLifecycle.current = null;
      const originalFetch = window.fetch;
      const originalStreamRender = streamRender;
      let streamRenderCalls = 0, progressivePaints = 0, lastLength = 0;
      streamRender = (...args) => { streamRenderCalls++; return originalStreamRender(...args); };
      const observer = new MutationObserver(() => {
        const body = document.querySelector('.msg.a .body');
        const length = body ? body.textContent.length : 0;
        if (ChatLifecycle.current?.state === 'STREAMING' && length > lastLength) progressivePaints++;
        lastLength = length;
      });
      observer.observe(document.getElementById('feed'), { subtree: true, childList: true, characterData: true });
      let frames = 0, maxFrameGap = 0, previousFrame = 0, tracking = true;
      const frame = timestamp => {
        if (previousFrame) maxFrameGap = Math.max(maxFrameGap, timestamp - previousFrame);
        previousFrame = timestamp; frames++;
        if (tracking) requestAnimationFrame(frame);
      };
      requestAnimationFrame(frame);
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      const framesBefore = frames;
      let payload = '';
      for (let i = 0; i < 2500; i++) payload += 'data: {"t":"word "}\n\n';
      payload += 'data: {"done":true}\n\n';
      window.fetch = async () => new Response(payload, {
        headers: { 'content-type': 'text/event-stream' }
      });
      document.getElementById('user-in').value = 'Large stream';
      const started = performance.now();
      await send();
      const elapsed = performance.now() - started;
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      tracking = false;observer.disconnect();window.fetch = originalFetch;streamRender = originalStreamRender;
      return {
        state: ChatLifecycle.current.state,
        assistants: document.querySelectorAll('.msg.a').length,
        textLength: document.querySelector('.msg.a .body').textContent.length,
        fullLength: ChatLifecycle.current.full.length,
        streamRenderCalls, progressivePaints, elapsed,
        frames: frames - framesBefore, maxFrameGap
      };
    });
    expect(result.state).toBe('COMPLETED');
    expect(result.assistants).toBe(1);
    expect(result.fullLength).toBe(12500);
    expect(result.textLength).toBe(12499);
    expect(result.streamRenderCalls).toBe(0);
    expect(result.progressivePaints).toBeGreaterThan(5);
    expect(result.frames).toBeGreaterThan(5);
    expect(result.elapsed).toBeLessThan(2000);
    expect(result.maxFrameGap).toBeLessThan(500);
  });

  test('CL-11: final streamed markup is identical to the canonical renderer', async ({ page }) => {
    const result = await page.evaluate(async () => {
      ownedStorageRemove('apexHistory');
      document.getElementById('feed').innerHTML = '';
      ChatLifecycle.current = null;
      const markdown = [
        '# Heading', '',
        'Paragraph with **strong**, *emphasis*, `inline code`, and [link](https://example.com).', '',
        '- First item', '- Second item', '',
        '```', '<unsafe> & literal', '```', '',
        '| Column | Value |', '| --- | --- |', '| Alpha | 1 |'
      ].join('\n');
      const expected = renderMarkdown(markdown);
      const originalFetch = window.fetch;
      const midpoint = Math.floor(markdown.length / 2);
      const payload = [
        'data: ' + JSON.stringify({ t: markdown.slice(0, midpoint) }),
        'data: ' + JSON.stringify({ t: markdown.slice(midpoint) }),
        'data: {"done":true}'
      ].join('\n\n') + '\n\n';
      window.fetch = async () => new Response(payload, {
        headers: { 'content-type': 'text/event-stream' }
      });
      document.getElementById('user-in').value = 'Canonical rendering';
      await send();
      const actual = document.querySelector('.msg.a .body').innerHTML;
      window.fetch = originalFetch;
      return { expected, actual, state: ChatLifecycle.current.state };
    });
    expect(result.state).toBe('COMPLETED');
    expect(result.actual).toBe(result.expected);
  });

  test('CL-5: auto-follow is sticky only until the user scrolls away', async ({ page }) => {
    const result = await page.evaluate(async () => {
      ownedStorageRemove('apexHistory');
      const feed = document.getElementById('feed');
      feed.innerHTML = '';
      ChatLifecycle.current = null;
      for (let i = 0; i < 24; i++) appendCoach().textContent = 'Existing content '.repeat(10);
      hardScroll();
      const originalFetch = window.fetch;
      window.fetch = async () => {
        const enc = new TextEncoder();
        return new Response(new ReadableStream({
          start(controller) {
            setTimeout(() => controller.enqueue(enc.encode('data: {"t":"First "}\n\n')), 40);
            setTimeout(() => controller.enqueue(enc.encode('data: {"t":"'+('More '.repeat(120))+'"}\n\n')), 140);
            setTimeout(() => controller.enqueue(enc.encode('data: {"done":true}\n\n')), 220);
          }
        }), { headers: { 'content-type': 'text/event-stream' } });
      };
      document.getElementById('user-in').value = 'Scroll';
      const pending = send();
      await new Promise((resolve) => setTimeout(resolve, 80));
      const followed = feed.scrollHeight - feed.scrollTop - feed.clientHeight;
      feed.scrollTop = 0;
      feed.dispatchEvent(new Event('scroll'));
      await pending;
      const stayed = { top: feed.scrollTop, follow: ChatLifecycle.current.follow,
        jump: document.getElementById('jump-latest').classList.contains('on') };
      window.fetch = originalFetch;
      return { followed, stayed };
    });
    expect(result.followed).toBeLessThanOrEqual(1);
    expect(result.stayed.top).toBe(0);
    expect(result.stayed.follow).toBe(false);
    expect(result.stayed.jump).toBe(true);
  });

  test('CL-6: a failed spoken turn terminates the shared lifecycle and voice state', async ({ page }) => {
    const result = await page.evaluate(async () => {
      ownedStorageRemove('apexHistory');
      document.getElementById('feed').innerHTML = '';
      ChatLifecycle.current = null;
      const originalFetch = window.fetch;
      const originalStop = VoiceIn.stop;
      window.fetch = async () => { throw new Error('offline'); };
      VoiceIn.stop = () => {};
      Voice.on = true;
      Voice._onFinal('Spoken failure');
      await new Promise((resolve) => setTimeout(resolve, 40));
      const snapshot = { lifecycle: ChatLifecycle.current.state, voice: Voice.state,
        assistants: document.querySelectorAll('.msg.a').length, history: getHistory() };
      Voice.on = false;
      VoiceIn.stop = originalStop;
      window.fetch = originalFetch;
      return snapshot;
    });
    expect(result.lifecycle).toBe('FAILED');
    expect(result.voice).toBe('ERROR');
    expect(result.assistants).toBe(1);
    expect(result.history).toEqual([{ role: 'user', content: 'Spoken failure' }]);
  });

  test('CL-7: voice session start uses the same lifecycle without parallel persistence', async ({ page }) => {
    const result = await page.evaluate(async () => {
      ownedStorageRemove('apexHistory');
      document.getElementById('feed').innerHTML = '';
      ChatLifecycle.current = null;
      const originalFetch = window.fetch;
      const originalSpeak = VoiceOut.speak;
      const originalListen = Voice.listen;
      let payload = null, spoken = null;
      window.fetch = async (url, options) => {
        payload = JSON.parse(options.body);
        return new Response('data: {"t":"Voice greeting"}\n\ndata: {"done":true}\n\n', {
          headers: { 'content-type': 'text/event-stream' }
        });
      };
      VoiceOut.speak = async (text) => { spoken = text; };
      Voice.listen = () => {};
      Voice.on = true;
      await Voice.greet();
      await new Promise((resolve) => setTimeout(resolve, 0));
      const snapshot = { state: ChatLifecycle.current.state, payload, spoken,
        users: document.querySelectorAll('.msg.u').length,
        assistants: document.querySelectorAll('.msg.a').length, history: getHistory() };
      Voice.on = false;
      VoiceOut.speak = originalSpeak;
      Voice.listen = originalListen;
      window.fetch = originalFetch;
      return snapshot;
    });
    expect(result.state).toBe('COMPLETED');
    expect(result.payload.session_start).toBe(true);
    expect(result.spoken).toBe('Voice greeting');
    expect(result.users).toBe(0);
    expect(result.assistants).toBe(1);
    expect(result.history).toEqual([]);
  });

  test('MB-1: no horizontal overflow on a mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.evaluate(() => {
      const md = [
        '| Упражнение | Серии | Повторения | Почивка |',
        '| --- | --- | --- | --- |',
        '| Лицеви опори с дълго име за проверка на пренасяне | 3 | 12 | 60 |',
        '| Клекове | 3 | 15 | 60 |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });
    // 7. document must not scroll horizontally (allow 1px sub-pixel rounding)
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test('JS-1: approved shell renders workout + nutrition with no uncaught errors', async ({ page }) => {
    await page.evaluate(() => {
      const md = [
        '| Упражнение | Серии | Повторения |',
        '| --- | --- | --- |',
        '| Клекове | 3 | 15 |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });
    expect(consoleErrors).toEqual([]);
  });

  test('AUTH-1: URL DEV token is verified before auth session and grants PRO access', async ({ page }) => {
    await page.route('**/verify-token', async (route) => {
      const payload = route.request().postDataJSON();
      expect(payload.token).toBe('dev-url-token');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ valid: true, isDev: true, plan: 'pro', expiry: 0 })
      });
    });
    await page.route('**/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ authenticated: false, plan: 'free', status: 'free' })
      });
    });
    await page.evaluate(() => localStorage.removeItem('apexToken'));
    const order = [];
    page.on('request', (request) => {
      const path = new URL(request.url()).pathname;
      if (path === '/verify-token' || path === '/auth/me') order.push(path);
    });

    await page.goto('/app?token=dev-url-token');
    await expect.poll(() => page.evaluate(() => SESSION.plan)).toBe('pro');
    const state = await page.evaluate(() => ({
      token: localStorage.getItem('apexToken'),
      plan: SESSION.plan,
      status: SESSION.status,
      isDev: SESSION.isDev,
      elite: isElite(),
      search: location.search
    }));

    expect(order.slice(0, 2)).toEqual(['/verify-token', '/auth/me']);
    expect(state).toEqual({
      token: 'dev-url-token',
      plan: 'pro',
      status: 'active',
      isDev: true,
      elite: true,
      search: ''
    });
  });

  test('AUTH-2: authenticated startup restores server profile and workout history', async ({ page }) => {
    const requests = [];
    await page.route('**/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true, email: 'sync@example.com', plan: 'free', status: 'free'
        })
      });
    });
    await page.route('**/api/profile', async (route) => {
      requests.push([route.request().method(), '/api/profile']);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ profile: { goal: 'server-goal', age: '42' } })
      });
    });
    await page.route('**/api/history', async (route) => {
      requests.push([route.request().method(), '/api/history']);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          workouts: [{
            id: 'server-workout', occurred_at: '2026-07-24T08:00:00Z',
            type: 'strength', exercises: [{ name: 'Squat', sets: 3, reps: 8 }],
            difficulty: 'medium', completion: 100
          }],
          nutrition: [],
          timeline: []
        })
      });
    });
    await page.route('**/api/conversations?limit=60', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ messages: [] })
      });
    });
    page.on('request', (request) => {
      if (new URL(request.url()).pathname === '/api/sync') requests.push([request.method(), '/api/sync']);
    });
    await page.evaluate(() => {
      activateDataOwner('account', 'sync@example.com');
      ownedStorageSet('apexProfile', JSON.stringify({ goal: 'local-goal', localOnly: 'kept' }));
      ownedStorageSet('apexWorkoutLog', JSON.stringify([
        {
          ts: Date.parse('2026-07-24T07:59:30Z'),
          date: '7/24/2026',
          type: 'strength',
          exercises: [{ name: 'Squat', sets: 3, reps: 8 }],
          diff: 'local-difficulty',
          completion: 100,
          localOnly: 'kept'
        },
        { ts: Date.parse('2026-07-23T08:00:00Z'), type: 'local-only', exercises: [] }
      ]));
    });

    await page.goto('/app');
    await expect.poll(() => page.evaluate(() => pfLoad().goal)).toBe('server-goal');
    const restored = await page.evaluate(() => ({
      profile: pfLoad(),
      workouts: JSON.parse(ownedStorageGet('apexWorkoutLog') || '[]')
    }));

    expect(requests).toContainEqual(['GET', '/api/profile']);
    expect(requests).toContainEqual(['GET', '/api/history']);
    expect(requests).not.toContainEqual(['POST', '/api/sync']);
    expect(restored.profile).toMatchObject({
      goal: 'server-goal', age: '42', localOnly: 'kept'
    });
    expect(restored.workouts).toEqual([
      { ts: Date.parse('2026-07-23T08:00:00Z'), type: 'local-only', exercises: [] },
      {
        ts: Date.parse('2026-07-24T08:00:00Z'),
        date: '2026-07-24',
        serverId: 'server-workout',
        type: 'strength',
        exercises: [{ name: 'Squat', sets: 3, reps: 8 }],
        diff: 'medium',
        completion: 100,
        localOnly: 'kept'
      }
    ]);
  });

  test('AUTH-3: anonymous startup and local writes never call account data APIs', async ({ page }) => {
    const accountRequests = [];
    await page.route('**/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ authenticated: false, plan: 'free', status: 'free' })
      });
    });
    page.on('request', (request) => {
      const path = new URL(request.url()).pathname;
      if (path === '/api/profile' || path === '/api/history' || path === '/api/workout') {
        accountRequests.push([request.method(), path]);
      }
    });

    await page.goto('/app');
    await page.evaluate(() => {
      SESSION.authenticated = false;
      accountSaveProfile({ goal: 'local-only' });
      accountLogWorkout({ ts: Date.now(), type: 'local-only', exercises: [] });
    });
    await page.waitForTimeout(100);

    expect(accountRequests).toEqual([]);
  });

  test('AUTH-4: authenticated profile save and workout completion write to account APIs', async ({ page }) => {
    const calls = await page.evaluate(async () => {
      SESSION.authenticated = true;
      const sent = [];
      const originalFetch = window.fetch;
      window.fetch = async (url, options = {}) => {
        sent.push({
          url,
          method: options.method || 'GET',
          body: options.body ? JSON.parse(options.body) : null
        });
        return new Response(JSON.stringify({ ok: true, id: 'server-workout' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      };
      document.getElementById('pf-age').value = '33';
      saveProfile();
      logWorkout({
        ts: Date.now(),
        date: '2026-07-24',
        type: 'strength',
        exercises: [{ name: 'Squat', sets: 3, reps: 8 }],
        diff: 'medium',
        completion: 100
      });
      await new Promise((resolve) => setTimeout(resolve, 0));
      window.fetch = originalFetch;
      return sent;
    });

    expect(calls).toContainEqual(expect.objectContaining({
      url: '/api/profile',
      method: 'PUT',
      body: expect.objectContaining({
        profile: expect.objectContaining({ age: '33', language: 'bg' })
      })
    }));
    expect(calls).toContainEqual(expect.objectContaining({
      url: '/api/workout',
      method: 'POST',
      body: expect.objectContaining({
        session: expect.objectContaining({ type: 'strength', completion: 100 })
      })
    }));
  });

  test('AUTH-5: account profile language overrides an incognito browser default after login', async ({ page }) => {
    const restored = await page.evaluate(async () => {
      lang = 'en';
      localStorage.setItem('apexLang', 'en');
      const originalFetch = window.fetch;
      window.fetch = async (url) => {
        if (url === '/auth/me') {
          return new Response(JSON.stringify({ authenticated: true, email: 'bg@example.com', plan: 'free', status: 'free' }), {
            status: 200, headers: { 'Content-Type': 'application/json' }
          });
        }
        if (url === '/api/profile') {
          return new Response(JSON.stringify({ profile: { age: '33', language: 'bg' } }), {
            status: 200, headers: { 'Content-Type': 'application/json' }
          });
        }
        if (url === '/api/history') {
          return new Response(JSON.stringify({ workouts: [], nutrition: [], timeline: [] }), {
            status: 200, headers: { 'Content-Type': 'application/json' }
          });
        }
        if (url === '/api/conversations?limit=60') {
          return new Response(JSON.stringify({ messages: [] }), {
            status: 200, headers: { 'Content-Type': 'application/json' }
          });
        }
        return originalFetch(url);
      };
      await loadSession(null);
      const result = { lang, documentLang: document.documentElement.lang, stored: localStorage.getItem('apexLang') };
      window.fetch = originalFetch;
      return result;
    });

    expect(restored).toEqual({ lang: 'bg', documentLang: 'bg', stored: 'bg' });
  });

  test('CP-1: collapsed Bulgarian day plan renders as cards with no raw pipes', async ({ page }) => {
    await page.evaluate(() => {
      const md = '| Обяд: | | | | Пиле | 200 г | 46 | 0 | 6 | 210 | | Ориз | 150 г | 4 | 45 | 1 | 200 |';
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });
    // One meal-level card contains all foods from the collapsed row.
    await expect(page.locator('.nutri-meal')).toHaveCount(1);
    const nutri = page.locator('.nutri').first();
    await expect(nutri).toContainText('Обяд');
    await expect(nutri).toContainText('Пиле');
    await expect(nutri).toContainText('Ориз');
    await expect(nutri).toContainText('Белтъчини');   // readability preserved (BG)
    expect(await nutri.innerText()).not.toContain('|');
  });

  test('CP-2: collapsed English day plan renders as cards with no raw pipes', async ({ page }) => {
    await page.evaluate(() => {
      const md = '| Lunch: | | | | Chicken | 200 g | 46 | 0 | 6 | 210 | | Rice | 150 g | 4 | 45 | 1 | 200 |';
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });
    await expect(page.locator('.nutri-meal')).toHaveCount(1);
    const nutri = page.locator('.nutri').first();
    await expect(nutri).toContainText('Lunch');
    await expect(nutri).toContainText('Chicken');
    await expect(nutri).toContainText('Rice');
    expect(await nutri.innerText()).not.toContain('|');
  });

  test('CP-3: mixed normal breakfast + collapsed lunch — both render, no raw pipes', async ({ page }) => {
    await page.evaluate(() => {
      const md = [
        '| Закуска | Протеин | Въглехидрати | Мазнини | Калории |',
        '| --- | --- | --- | --- | --- |',
        '| Овесена каша | 12 | 54 | 7 | 320 |',
        '| Обяд: | | | | Пиле | 200 г | 46 | 0 | 6 | 210 | | Ориз | 150 г | 4 | 45 | 1 | 200 |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });
    const nutriText = (await page.locator('.nutri').allInnerTexts()).join('\n');
    expect(nutriText).toContain('Овесена каша');   // normal breakfast row
    expect(nutriText).toContain('Обяд');            // collapsed lunch label
    expect(nutriText).toContain('Пиле');
    expect(nutriText).toContain('Ориз');
    expect(nutriText).not.toContain('|');           // no raw pipes anywhere
    await expect(page.locator('.nutri-meal').filter({ hasText: 'Пиле' })).toHaveCount(1);
  });

  test('CP-4: ordinary text containing pipes stays plain text (never nutrition)', async ({ page }) => {
    await page.evaluate(() => {
      // Starts with a meal word AND contains "|", but has no numeric food rows,
      // so it must NOT be parsed as a collapsed nutrition block.
      const md = 'Обядът беше страхотен | много вкусно | горещо препоръчвам';
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });
    await expect(page.locator('.nutri-meal')).toHaveCount(0);
    await expect(page.locator('.msg').last()).toContainText('много вкусно');
  });

  test('CP-5: collapsed plan has no horizontal overflow on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.evaluate(() => {
      const md = '| Вечеря: | | | | Сьомга на фурна с гарнитура | 220 г | 44 | 2 | 18 | 360 | | Зелена салата | 150 г | 3 | 8 | 5 | 90 |';
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });
    await expect(page.locator('.nutri-meal').first()).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });

  // ── NUTRITION V4 — mixed-format recovery ──
  async function enterEnglish(page) {
    await page.goto('/app?lang=en');
    await page.evaluate(() => {
      try { if (typeof enterConsult === 'function') enterConsult(''); } catch (e) {}
      const m = document.getElementById('profile-modal'); if (m) m.classList.remove('on');
    });
  }
  const renderMd = (page, lines) => page.evaluate((md) => {
    const el = appendCoach(); el.innerHTML = renderMarkdown(md);
  }, Array.isArray(lines) ? lines.join('\n') : lines);
  const lastMsgText = (page) => page.locator('.msg').last().innerText();

  test('MR-1: normal → pipe → collapsed all merge into one plan (no raw pipes)', async ({ page }) => {
    await renderMd(page, [
      '**Вечеря**',
      '| Пиле | 200 г | 46 | 0 | 6 | 210 |',
      '| Броколи | 100 г | 3 | 6 | 0 | 35 |',
      '| Закуска: | | | | Ябълка | 100 г | 0 | 25 | 0 | 95 | | Ядки | 30 г | 6 | 6 | 15 | 180 |'
    ]);
    const txt = (await page.locator('.nutri').allInnerTexts()).join('\n');
    for (const f of ['Пиле', 'Броколи', 'Ябълка', 'Ядки']) expect(txt).toContain(f);
    expect(await lastMsgText(page)).not.toContain('|');
  });

  test('MR-2: collapsed → markdown table continue as one plan', async ({ page }) => {
    await renderMd(page, [
      '| Обяд: | | | | Пиле | 200 г | 46 | 0 | 6 | 210 | | Ориз | 150 г | 4 | 45 | 1 | 200 |',
      '| Продукт | Протеин | Въглехидрати | Мазнини | Калории |',
      '| --- | --- | --- | --- | --- |',
      '| Кисело мляко | 8 | 12 | 4 | 110 |'
    ]);
    const txt = (await page.locator('.nutri').allInnerTexts()).join('\n');
    for (const f of ['Пиле', 'Ориз', 'Кисело мляко']) expect(txt).toContain(f);
    expect(await lastMsgText(page)).not.toContain('|');
  });

  test('MR-3: Bulgarian mixed formats', async ({ page }) => {
    await renderMd(page, [
      'Закуска',
      '| Овесена каша | 80 г | 12 | 54 | 7 | 320 |',
      'Вечеря',
      '| Сьомга | 200 г | 44 | 0 | 18 | 360 |'
    ]);
    const txt = (await page.locator('.nutri').allInnerTexts()).join('\n');
    for (const s of ['Закуска', 'Овесена каша', 'Вечеря', 'Сьомга', 'Белтъчини']) expect(txt).toContain(s);
    expect(await lastMsgText(page)).not.toContain('|');
  });

  test('MR-4: English mixed formats', async ({ page }) => {
    await enterEnglish(page);
    await renderMd(page, [
      '**Breakfast**',
      '| Oatmeal | 80 g | 12 | 54 | 7 | 320 |',
      '| Lunch: | | | | Chicken | 200 g | 46 | 0 | 6 | 210 | | Rice | 150 g | 4 | 45 | 1 | 200 |'
    ]);
    const txt = (await page.locator('.nutri').allInnerTexts()).join('\n');
    for (const f of ['Breakfast', 'Oatmeal', 'Chicken', 'Rice', 'Protein']) expect(txt).toContain(f);
    expect(txt).not.toContain('**');
    expect(await lastMsgText(page)).not.toContain('|');
  });

  test('MR-5: mixed Bulgarian + English meals in one plan', async ({ page }) => {
    await renderMd(page, [
      'Закуска',
      '| Овесена каша | 80 г | 12 | 54 | 7 | 320 |',
      '**Lunch**',
      '| Chicken | 200 g | 46 | 0 | 6 | 210 |'
    ]);
    const txt = (await page.locator('.nutri').allInnerTexts()).join('\n');
    for (const s of ['Закуска', 'Овесена каша', 'Lunch', 'Chicken']) expect(txt).toContain(s);
    expect(await lastMsgText(page)).not.toContain('|');
  });

  test('MR-6: a broken row never rejects the whole meal', async ({ page }) => {
    await renderMd(page, [
      '**Обяд**',
      '| Ориз | 150 г | 4 | 45 | 1 | 200 |',
      '| ??? счупен ред |',
      '| Боб | 100 г | 8 | 20 | 1 | 120 |'
    ]);
    const txt = (await page.locator('.nutri').allInnerTexts()).join('\n');
    expect(txt).toContain('Ориз');
    expect(txt).toContain('Боб');      // meal survived the broken row
    expect(await lastMsgText(page)).not.toContain('|');
  });

  test('MR-7: totals in the middle still become the final summary', async ({ page }) => {
    await renderMd(page, [
      '**Закуска**',
      '| Яйца | 100 г | 13 | 1 | 11 | 155 |',
      '| Общо | | | 13 | 1 | 11 | 155 |',
      '**Обяд**',
      '| Риба тон | 100 г | 26 | 0 | 1 | 116 |'
    ]);
    await expect(page.locator('.nutri-total')).toHaveCount(1);
    const txt = (await page.locator('.nutri').allInnerTexts()).join('\n');
    expect(txt).toContain('Риба тон');   // meal after the mid-total still rendered
    expect(await lastMsgText(page)).not.toContain('|');
  });

  test('MR-8: totals at the end become the summary card', async ({ page }) => {
    await renderMd(page, [
      '**Вечеря**',
      '| Сьомга | 200 г | 44 | 0 | 18 | 360 |',
      '| Общо | | | 44 | 0 | 18 | 360 |'
    ]);
    await expect(page.locator('.nutri-total')).toBeVisible();
    await expect(page.locator('.nutri-total')).toContainText('360');
    expect(await lastMsgText(page)).not.toContain('|');
  });

  test('MR-9: bold headers render without markdown markers', async ({ page }) => {
    await renderMd(page, [
      '**Закуска**',
      '| Овесена каша | 80 г | 12 | 54 | 7 | 320 |'
    ]);
    const txt = (await page.locator('.nutri').allInnerTexts()).join('\n');
    expect(txt).toContain('Закуска');
    expect(txt).not.toContain('**');
    expect(await lastMsgText(page)).not.toContain('|');
  });

  test('MR-10: plain headers are recognized', async ({ page }) => {
    await renderMd(page, [
      'Следобедна закуска',
      '| Кисело мляко | 150 г | 8 | 12 | 4 | 110 |'
    ]);
    const titles = await page.locator('.nutri-title .nm-name').allInnerTexts();
    expect(titles.join(' ')).toContain('Следобедна закуска');
    expect(await lastMsgText(page)).not.toContain('|');
  });

  test('MR-11: repeated meal names keep their own foods', async ({ page }) => {
    await renderMd(page, [
      'Междинна закуска',
      '| Ябълка | 100 г | 0 | 25 | 0 | 95 |',
      'Обяд',
      '| Пиле | 200 г | 46 | 0 | 6 | 210 |',
      'Междинна закуска',
      '| Ядки | 30 г | 6 | 6 | 15 | 180 |'
    ]);
    const txt = (await page.locator('.nutri').allInnerTexts()).join('\n');
    for (const f of ['Ябълка', 'Пиле', 'Ядки']) expect(txt).toContain(f);
    // both "Междинна закуска" sections are present
    const titles = await page.locator('.nutri-title .nm-name').allInnerTexts();
    expect(titles.filter((x) => /Междинна закуска/.test(x)).length).toBe(2);
  });

  test('MR-12: mixed plan has no horizontal overflow on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await renderMd(page, [
      '**Вечеря**',
      '| Сьомга на фурна с голяма зелена гарнитура | 220 г | 44 | 2 | 18 | 360 |',
      '| Салата: | | | | Домати и краставици | 150 г | 3 | 8 | 5 | 90 | | Зехтин | 15 г | 0 | 0 | 15 | 135 |'
    ]);
    await expect(page.locator('.nutri-meal').first()).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test('MR-13: no visible raw pipes anywhere in a heavily-mixed plan', async ({ page }) => {
    await renderMd(page, [
      '**Закуска**',
      '| Овесена каша | 80 г | 12 | 54 | 7 | 320 |',
      '| Банан | 120 г | 1 | 27 | 0 | 105 |',
      '| Обяд: | | | | Пиле | 200 г | 46 | 0 | 6 | 210 | | Ориз | 150 г | 4 | 45 | 1 | 200 |',
      '| счупено |',
      '| Общо | | | 63 | 126 | 13 | 835 |'
    ]);
    expect(await lastMsgText(page)).not.toContain('|');
    await expect(page.locator('.nutri-meal').first()).toBeVisible();
  });

  test('MR-14: duplicated foods are not rendered twice', async ({ page }) => {
    await renderMd(page, [
      '**Закуска**',
      '| Овесена каша | 80 г | 12 | 54 | 7 | 320 |',
      '| Овесена каша | 80 г | 12 | 54 | 7 | 320 |'
    ]);
    await expect(page.locator('.nutri-meal').filter({ hasText: 'Овесена каша' })).toHaveCount(1);
  });

  test('MR-15: meal order is preserved', async ({ page }) => {
    await enterEnglish(page);
    await renderMd(page, [
      '**Breakfast**', '| Oatmeal | 80 g | 12 | 54 | 7 | 320 |',
      '**Lunch**', '| Chicken | 200 g | 46 | 0 | 6 | 210 |',
      '**Dinner**', '| Salmon | 200 g | 44 | 0 | 18 | 360 |'
    ]);
    const names = await page.locator('.nutri .nm-name').allInnerTexts();
    const order = names.join('\n');
    expect(order.indexOf('Breakfast')).toBeLessThan(order.indexOf('Lunch'));
    expect(order.indexOf('Lunch')).toBeLessThan(order.indexOf('Dinner'));
  });

  test('WO-CAT-1: canonical catalog localizes every starter exercise and preserves prescription types', async ({ page }) => {
    await page.evaluate(() => {
      const md = [
        '| Exercise | Sets | Reps | Rest |',
        '| --- | --- | --- | --- |',
        '| Easy march in place | 1 | 3 minutes | 30 sec |',
        '| Chair squat | 2 | 6-8 | 60 sec |',
        '| Wall Push-Up | 2 | 6-8 | 60 sec |',
        '| Glute bridge | 2 | 8 | 60 sec |',
        '| Bird-dog | 2 | 6 per side | 60 sec |'
      ].join('\n');
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });

    const protocol = page.locator('.workout-protocol');
    await expect(protocol).toHaveCount(1);
    await expect(protocol.locator('.workout-exercise-card')).toHaveCount(5);
    await expect(protocol.locator('.start-wo')).toHaveCount(1);
    await expect(protocol).not.toContainText('Bird-dog');
    await expect(protocol.locator('[data-exercise-id="bird_dog"]')).toContainText('\u041f\u0440\u043e\u0442\u0438\u0432\u043e\u043f\u043e\u043b\u043e\u0436\u043d\u0430 \u0440\u044a\u043a\u0430 \u0438 \u043a\u0440\u0430\u043a \u043e\u0442 \u0447\u0435\u0442\u0438\u0440\u0438 \u043e\u043f\u043e\u0440\u0438');
    await expect(protocol.locator('[data-exercise-id="marching_in_place"]')).toContainText('\u041f\u0440\u043e\u0434\u044a\u043b\u0436\u0438\u0442\u0435\u043b\u043d\u043e\u0441\u0442');
    await expect(protocol.locator('[data-exercise-id="marching_in_place"]')).not.toContainText('\u043c\u0438\u043d\u0443\u0442\u0438 \u043f\u043e\u0432\u0442.');
    await expect(protocol.locator('[data-exercise-id="bird_dog"]')).toContainText('\u041f\u043e\u0432\u0442\u043e\u0440\u0435\u043d\u0438\u044f \u043d\u0430 \u0441\u0442\u0440\u0430\u043d\u0430');
    await expect(protocol.locator('.ei-section:empty')).toHaveCount(0);
    await expect(protocol.locator('[data-exercise-figure], svg')).toHaveCount(0);
    const catalog = await page.evaluate(() => {
      const engineNames = ['Wall Push-Up', 'Incline Push-Up', 'Push-Up', 'Table Row',
        'Bodyweight Squat', 'Goblet Squat', 'Reverse Lunge', 'Bodyweight Hip Hinge',
        'Dumbbell Romanian Deadlift', 'Dumbbell Row', 'Resistance-Band Row',
        'Dumbbell Overhead Press', 'Seated Dumbbell Press', 'Pull-Up', 'Front Plank',
        'Barbell Back Squat', 'Easy march in place', 'Chair squat', 'Glute bridge', 'Bird-dog'];
      const fields = ['overview', 'starting', 'execution', 'breathing', 'cues', 'mistakes', 'regression', 'safety'];
      return {
        missing: engineNames.filter((name) => !ApexExerciseInstructions.find(name)),
        incomplete: ApexExerciseInstructions.records.filter((record) =>
          ['bg', 'en'].some((language) => fields.some((field) => !record[language][field]))).map((record) => record.canonical_id)
      };
    });
    expect(catalog.missing).toEqual([]);
    expect(catalog.incomplete).toEqual([]);
  });

  test('WO-CAT-2: a single-exercise question renders one focused card without replay or network', async ({ page }) => {
    const calls = await page.evaluate(async () => {
      const md = [
        '| Exercise | Sets | Reps | Rest |', '| --- | --- | --- | --- |',
        '| Chair squat | 2 | 6-8 | 60 sec |', '| Bird-dog | 2 | 6 per side | 60 sec |'
      ].join('\n');
      const workout = appendCoach();
      workout.innerHTML = renderMarkdown(md);
      const originalFetch = window.fetch;
      let count = 0;
      window.fetch = (...args) => { count += 1; return originalFetch(...args); };
      document.getElementById('user-in').value = '\u043a\u0430\u043a\u0432\u043e \u0435 \u0442\u043e\u0432\u0430 \u0443\u043f\u0440\u0430\u0436\u043d\u0435\u043d\u0438\u0435 bird dog';
      await send();
      return count;
    });

    await expect(page.locator('.workout-protocol')).toHaveCount(1);
    await expect(page.locator('.workout-protocol .start-wo')).toHaveCount(1);
    const focused = page.locator('.focused-exercise-instruction');
    await expect(focused).toHaveCount(1);
    await expect(focused.locator('.workout-exercise-card')).toHaveCount(1);
    await expect(focused.locator('.start-wo')).toHaveCount(0);
    await expect(focused).toContainText('\u0422\u0435\u0445\u043d\u0438\u043a\u0430 \u043d\u0430 \u0443\u043f\u0440\u0430\u0436\u043d\u0435\u043d\u0438\u0435\u0442\u043e');
    await expect(focused).toContainText('\u041f\u0440\u043e\u0442\u0438\u0432\u043e\u043f\u043e\u043b\u043e\u0436\u043d\u0430 \u0440\u044a\u043a\u0430 \u0438 \u043a\u0440\u0430\u043a \u043e\u0442 \u0447\u0435\u0442\u0438\u0440\u0438 \u043e\u043f\u043e\u0440\u0438');
    await expect(focused).toContainText('6 \u043f\u043e\u0432\u0442\u043e\u0440\u0435\u043d\u0438\u044f \u043d\u0430 \u0441\u0442\u0440\u0430\u043d\u0430');
    await expect(focused).not.toContainText('6 \u043d\u0430 \u0441\u0442\u0440\u0430\u043d\u0430 \u043f\u043e\u0432\u0442\u043e\u0440\u0435\u043d\u0438\u044f');
    await expect(focused.locator('details[open]')).toHaveCount(5);
    expect(calls).toBe(0);
  });

  test('WO-CAT-3: English session uses English canonical names and instructions', async ({ page }) => {
    await page.evaluate(() => {
      lang = 'en';
      const md = [
        '| Exercise | Sets | Reps | Rest |', '| --- | --- | --- | --- |',
        '| Bird-dog | 2 | 6 per side | 60 sec |', '| Front Plank | 2 | 8-12 | 45 sec |'
      ].join('\n');
      const workout = appendCoach();
      workout.innerHTML = renderMarkdown(md);
    });
    const protocol = page.locator('.workout-protocol');
    await expect(protocol).toContainText('Bird-dog');
    await expect(protocol).toContainText('Front Plank');
    await expect(protocol).toContainText('Starting position');
    await expect(protocol).toContainText('20–40 seconds');
    await expect(protocol).not.toContainText('\u041f\u0440\u043e\u0442\u0438\u0432\u043e\u043f\u043e\u043b\u043e\u0436\u043d\u0430 \u0440\u044a\u043a\u0430');
  });
});

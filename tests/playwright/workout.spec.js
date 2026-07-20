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
        localStorage.setItem('apexProfile', JSON.stringify({
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
    await expect(firstName).toHaveText('Лицеви опори');

    // 3. sets AND reps are visible on the card
    const firstStats = page.locator('.ex-card').first().locator('.ex-stats');
    await expect(firstStats).toContainText('3');            // sets value
    await expect(firstStats).toContainText(/серии|sets/);
    await expect(firstStats).toContainText('12');           // reps value
    await expect(firstStats).toContainText(/повт|reps/);

    // approved workout entry point is present
    await expect(page.locator('.start-wo')).toBeVisible();
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

  test('CP-1: collapsed Bulgarian day plan renders as cards with no raw pipes', async ({ page }) => {
    await page.evaluate(() => {
      const md = '| Обяд: | | | | Пиле | 200 г | 46 | 0 | 6 | 210 | | Ориз | 150 г | 4 | 45 | 1 | 200 |';
      const el = appendCoach();
      el.innerHTML = renderMarkdown(md);
    });
    // meal-label card + two food cards
    await expect(page.locator('.nutri-meal')).toHaveCount(3);
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
    await expect(page.locator('.nutri-meal')).toHaveCount(3);
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
});

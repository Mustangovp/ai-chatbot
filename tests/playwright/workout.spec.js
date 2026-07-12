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
});

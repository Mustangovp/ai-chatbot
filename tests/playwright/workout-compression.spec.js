const { test, expect } = require('@playwright/test');

const ids = [
  'dumbbell.goblet_squat', 'dumbbell.floor_press', 'bodyweight.table_row',
  'bodyweight.glute_bridge', 'bodyweight.plank', 'bodyweight.march_in_place'
];

async function mount(page, language) {
  await page.goto('/app?lang=' + language);
  await page.evaluate(({ language, ids }) => {
    lang = language;
    ownedStorageSet('apexProfile', JSON.stringify({ goal: 'strength', age: '30', weight: '75',
      height: '178', gender: 'male', level: 'beginner', equip: 'home' }));
    enterConsult('');
    document.getElementById('profile-modal').classList.remove('on');
    const exercises = ids.map((id, index) => ({
      prescription_id: 'compressed-' + index, exercise_id: id, exercise_version: '1.0.0',
      display_name: ApexExerciseInstructions.display(ApexExerciseInstructions.findByExerciseId(id), language),
      prescribed_sets: 2, prescription_type: index === 4 ? 'duration' : 'repetitions',
      rep_min: index === 4 ? null : 8, rep_max: index === 4 ? null : 12,
      duration_min_seconds: index === 4 ? 20 : null, duration_max_seconds: index === 4 ? 40 : null,
      rest_seconds: 60, difficulty: index < 2 ? 'intermediate' : 'beginner'
    }));
    const session = { session_id: 'compression-session', session_index: 1, exercises };
    pendingTrainingCompletion = { plan_id: 'compression-plan', plan_version: 'training-plan-blueprint-v3', sessions: [session] };
    pendingCompletionSessions = [session];
    const rows = exercises.map(item => `| ${item.display_name} | 2 | ${item.prescription_type === 'duration' ? '20-40 sec' : '8-12'} | 60 | RPE 6, RIR 4; ${language === 'bg' ? '\u0442\u0435\u043c\u043f\u043e' : 'tempo'} 2-1-2-0 |`);
    appendCoach().innerHTML = renderMarkdown(['| Exercise | Sets | Reps | Rest | Note |',
      '| --- | --- | --- | --- | --- |', ...rows].join('\n'));
    hardScroll();
  }, { language, ids });
}

for (const language of ['bg', 'en']) {
  for (const width of [1440, 390, 360]) {
    test(`compressed overview retains all guidance and authority in ${language} at ${width}px`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width === 1440 ? 900 : width === 390 ? 844 : 800 });
      await mount(page, language);
      const source = await page.evaluate(() => JSON.stringify(pendingTrainingCompletion));
      const cards = page.locator('.workout-protocol .workout-exercise-card');
      await expect(cards).toHaveCount(6);
      await expect(cards.locator(':scope > details')).toHaveCount(6);
      await expect(cards.locator('details[open]')).toHaveCount(0);
      await expect(cards.locator('.workout-card-hero .ex-diff, .workout-card-hero .ex-muscle')).toHaveCount(0);
      await expect(cards.locator('.workout-card-note')).toHaveCount(0);
      await expect(cards.locator('.workout-key-cue')).toHaveCount(6);
      await expect(cards.nth(2).locator('.workout-key-cue')).toHaveText(await page.evaluate(language => {
        return ApexExerciseInstructions.findByExerciseId('bodyweight.table_row')[language].safety;
      }, language));
      for (const [index, id] of ids.entries()) {
        await expect(cards.nth(index).locator('.exercise-visual')).toHaveAttribute('data-exercise-visual-id', id);
        await expect(cards.nth(index).locator('.exercise-visual img')).toHaveAttribute('src',
          `/static/exercise/visuals/v1/${id}--thumb.webp?v=canonical-workout-r4`);
        const collapsed = await cards.nth(index).boundingBox();
        expect(collapsed.height).toBeLessThan(340);
        await expect(cards.nth(index).locator('.workout-card-dose')).toContainText(index === 4 ? '2 × 20–40' : '2 × 8-12');
        await expect(cards.nth(index).locator('.workout-card-stats')).toContainText(language === 'bg' ? '60 сек' : '60 sec');
      }
      const start = page.locator('.start-wo');
      await expect(start).toHaveCount(1);
      await expect(start).toBeInViewport();
      const layout = await page.evaluate(() => {
        const button = document.querySelector('.start-wo').getBoundingClientRect();
        const footer = document.querySelector('.workout-start').getBoundingClientRect();
        const last = [...document.querySelectorAll('.workout-exercise-card')].at(-1).getBoundingClientRect();
        return { buttonWidth: button.width, footerWidth: footer.width, gap: button.top - last.bottom,
          overflow: document.documentElement.scrollWidth > innerWidth };
      });
      expect(layout.overflow).toBe(false);
      expect(layout.gap).toBeGreaterThanOrEqual(14);
      if (width < 560) expect(Math.abs(layout.buttonWidth - layout.footerWidth)).toBeLessThan(1);
      await page.screenshot({ path: testInfo.outputPath(`start-${language}-${width}.png`) });
      await cards.first().scrollIntoViewIfNeeded();
      await page.screenshot({ path: testInfo.outputPath(`overview-${language}-${width}.png`) });

      const details = cards.first().locator(':scope > details');
      const summary = details.locator(':scope > summary');
      await expect(summary).toHaveText(language === 'bg' ? 'Детайли за изпълнение' : 'Execution details');
      await summary.focus();
      await expect(summary).toBeFocused();
      expect(await summary.evaluate(element => getComputedStyle(element).outlineStyle)).toBe('solid');
      await summary.press('Enter');
      await expect(details).toHaveAttribute('open', '');
      const deep = details.locator('.workout-deep-guidance');
      await expect(deep).not.toHaveAttribute('open', '');
      expect(await cards.first().evaluate(card => card.getBoundingClientRect().height)).toBeGreaterThan(340);
      await expect(details.locator('.workout-prescribed-meta')).toContainText('2-1-2-0');
      await expect(details.locator('.workout-prescribed-meta')).toContainText('RPE 6');
      await expect(details.locator('.workout-prescribed-meta')).toContainText('RIR 4');
      await deep.locator('summary').press('Space');
      await expect(deep).toHaveAttribute('open', '');
      const original = await page.evaluate(language => ApexExerciseInstructions.findByExerciseId('dumbbell.goblet_squat')[language], language);
      for (const key of ['starting', 'execution', 'breathing', 'cues', 'mistakes', 'regression', 'safety']) {
        for (const value of Array.isArray(original[key]) ? original[key] : [original[key]]) {
          await expect(cards.first()).toContainText(value);
        }
      }
      await page.screenshot({ path: testInfo.outputPath(`expanded-${language}-${width}.png`) });
      await summary.press('Enter');
      await expect(details).not.toHaveAttribute('open', '');
      await start.click();
      await expect(page.locator('#workout')).toHaveClass(/on/);
      await page.locator('#workout').evaluate(async element => {
        await Promise.all(element.getAnimations().filter(animation =>
          animation.effect.getTiming().iterations !== Infinity).map(animation => animation.finished));
      });
      const activeTop = await page.locator('.wo-step').evaluate(element => ({
        top: element.getBoundingClientRect().top,
        stageTop: element.closest('.wo-stage').getBoundingClientRect().top
      }));
      expect(activeTop.top).toBeGreaterThanOrEqual(activeTop.stageTop);
      await expect(page.locator('button[onclick="completeSet()"]')).toBeInViewport();
      await expect(page.locator('#wo-reps-in')).toHaveValue('');
      await expect(page.locator('.wo-ex-meta')).not.toContainText('2-0-2');
      const technique = page.locator('.wo-technique');
      await expect(technique).not.toHaveAttribute('open', '');
      await page.screenshot({ path: testInfo.outputPath(`active-${language}-${width}.png`) });
      await technique.locator(':scope > summary').click();
      await expect(technique).toHaveAttribute('open', '');
      await expect(technique.locator('.workout-prescribed-meta')).toContainText('2-1-2-0');
      await expect(page.locator('#wo-reps-in')).toHaveValue('');
      expect(await page.evaluate(() => JSON.stringify(pendingTrainingCompletion))).toBe(source);
      expect(await page.evaluate(() => JSON.stringify(WO.ex.map(exercise => exercise.completion))))
        .toBe(JSON.stringify(JSON.parse(source).sessions[0].exercises));
    });
  }
  test(`metadata deduplication preserves unique coaching and does not invent tempo in ${language}`, async ({ page }) => {
    await mount(page, language);
    const result = await page.evaluate(language => {
      const cue = language === 'bg' ? 'Пази торса стабилен.' : 'Keep the torso stable.';
      const note = `RPE 6, RIR 4; ${language === 'bg' ? 'темпо' : 'tempo'} 2-1-2-0; ${cue}`;
      return { known: workoutDisplayMeta({ note }), unknown: workoutDisplayMeta({ note: cue }), cue };
    }, language);
    expect(result.known).toEqual({ rpe: '6', rir: '4', tempo: '2-1-2-0', note: result.cue });
    expect(result.unknown).toEqual({ rpe: '—', rir: '—', tempo: '—', note: result.cue });
  });
}

test('completed workout exposes its existing start action without changing conversational scrolling', async ({ page }) => {
  await mount(page, 'en');
  const result = await page.evaluate(() => {
    const finish = raw => {
      const x = ChatLifecycle.begin('synthetic request', {}, []);
      ChatLifecycle.waiting(x);ChatLifecycle.content(x, raw);ChatLifecycle.complete(x);
      return document.getElementById('feed');
    };
    const feed = finish(Array(120).fill('Ordinary conversational guidance.').join('\n'));
    const conversationAtBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 2;
    const exercise = renderedWorkoutExercises['compression-session'][0];
    const session = { session_id: 'scroll-session', session_index: 1, exercises: [exercise.completion] };
    pendingTrainingCompletion = { plan_id: 'scroll-plan', plan_version: 'training-plan-blueprint-v3', sessions: [session] };
    pendingCompletionSessions = [session];
    finish(`| Exercise | Sets | Reps | Rest |\n| --- | --- | --- | --- |\n| ${exercise.name} | 2 | 8-12 | 60 |\n\n` +
      Array(120).fill('Additional explanation remains available.').join('\n'));
    return { conversationAtBottom };
  });
  expect(result).toEqual({ conversationAtBottom: true });
  await expect.poll(() => page.evaluate(() => {
    const button = [...document.querySelectorAll('.start-wo')].at(-1).getBoundingClientRect();
    const bounds = document.getElementById('feed').getBoundingClientRect();
    return button.top >= bounds.top - 1 && button.bottom <= bounds.bottom + 1;
  })).toBe(true);
});

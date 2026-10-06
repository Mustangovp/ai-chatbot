const { test, expect } = require('@playwright/test');

const profile = { goal: 'strength', level: 'intermediate', equip: 'home', age: '30', weight: '75', height: '178', gender: 'male' };
const macros = { kcal: '420', protein_g: '20', carbs_g: '40', fat_g: '20' };
const measurements = ['raw', 'cooked', 'drained', 'ready_to_eat', 'as_served', 'package_weight', null];
const saved = () => ({ latest_plan: {
  created_at: '2026-10-01T10:00:00Z',
  targets: { kcal: '1700.0000000000000001', protein_g: null, carbs_g: null, fat_g: null },
  totals: { kcal: '1680', protein_g: '80', carbs_g: '160', fat_g: '80' },
  meals: ['breakfast', 'snack', 'lunch', 'dinner'].map((meal_type, index) => ({
    meal_type, time: ['08:00', null, '13:00', '19:00'][index], macros,
    foods: (index === 0 ? measurements : [null]).map((measurement_state, food) => ({
      display_name: index === 0 ? `Saved Rice ${food + 1}` : 'Ориз', grams: '100.25', measurement_state
    }))
  })),
  restrictions: ['peanut allergy']
} });

async function setup(page, { language = 'en', authenticated = true, data = saved(), status = 200 } = {}) {
  const calls = { chat: 0, reads: 0, writes: 0 };
  page.on('request', request => { if (new URL(request.url()).pathname === '/chat') calls.chat++; });
  await page.route('**/auth/me', route => route.fulfill({ json: authenticated ? {
    authenticated: true, email: 'local-nutrition@example.com', plan: 'free', status: 'free'
  } : { authenticated: false, plan: 'free', status: 'free' } }));
  await page.route('**/api/profile', route => route.fulfill({ json: { profile: { ...profile, language }, training_constraint_records: [] } }));
  await page.route('**/api/history', route => route.fulfill({ json: { workouts: [], nutrition: [{ content: 'PRIVATE_LEGACY_NUTRITION' }] } }));
  await page.route('**/api/conversations?*', route => route.fulfill({ json: { messages: [] } }));
  await page.route('**/api/athlete-model', route => route.fulfill({ json: {} }));
  await page.route('**/api/nutrition', route => {
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

async function openNutrition(page, language = 'en') {
  await page.locator('#menu-btn').click();
  await page.locator('#drawer').getByText(language === 'bg' ? 'Хранене' : 'Nutrition', { exact: true }).click();
  await expect(page.locator('#saved-nutrition')).toBeVisible();
  await expect(page.locator('#saved-nutrition')).toHaveAttribute('aria-busy', 'false');
}

for (const language of ['en', 'bg']) {
  test(`Nutrition is exactly three factual sections and one explicit CTA in ${language}`, async ({ page }) => {
    const calls = await setup(page, { language });
    await openNutrition(page, language);
    const root = page.locator('#saved-nutrition');
    await expect(root.locator('[data-nutrition-block]')).toHaveCount(3);
    await expect(root.locator('h3')).toHaveText(language === 'bg' ?
      ['Последен запазен план', 'Таргети на плана', 'Ограничения в този план'] :
      ['Latest saved plan', 'Plan targets', 'Restrictions in this plan']);
    await expect(root.locator('button')).toHaveCount(1);
    await expect(root.locator('canvas, svg, img, .card, .chart, .gauge, .ex-glyph')).toHaveCount(0);
    await expect(page.locator('#consult')).not.toHaveClass(/\bon\b/);
    await expect(page.locator('#user-in')).toHaveValue('');
    expect(calls).toEqual({ chat: 0, reads: 1, writes: 0 });
    await expect(root).not.toContainText(/consumed|remaining|eaten|adherence|compliance|score|hydration|deficit|%|PRIVATE_LEGACY|изядени|оставащи|придържане/i);
    await expect(root.locator('[datetime]')).toHaveAttribute('datetime', '2026-10-01T10:00:00Z');
    await expect(root.locator('[data-saved-meal] h4')).toHaveText(language === 'bg' ?
      ['Закуска', 'Снак', 'Обяд', 'Вечеря'] : ['Breakfast', 'Snack', 'Lunch', 'Dinner']);
    await expect(root.locator('[data-saved-meal="snack"] time')).toHaveCount(0);
    await expect(root.locator('.saved-nutrition-restrictions li')).toHaveText(['peanut allergy']);
    await expect(root.locator('#saved-nutrition-create')).toHaveText(language === 'bg' ? 'Създай нов хранителен план' : 'Create a new nutrition plan');
  });

  test(`saved food names, quantities and all measurement labels are preserved in ${language}`, async ({ page }) => {
    await setup(page, { language });
    await openNutrition(page, language);
    const labels = language === 'bg' ? ['сурово', 'сготвено', 'отцедено', 'готово за консумация', 'както е сервирано', 'тегло от опаковката'] :
      ['raw', 'cooked', 'drained', 'ready to eat', 'as served', 'package weight'];
    const unit = language === 'bg' ? 'г' : 'g';
    await expect(page.locator('[data-saved-meal="breakfast"] .saved-nutrition-foods li')).toHaveText(
      measurements.map((state, index) => `Saved Rice ${index + 1} · 100.25 ${unit}${state ? ' · ' + labels[index] : ''}`));
    await expect(page.locator('[data-saved-meal="lunch"] .saved-nutrition-foods li')).toHaveText(`Ориз · 100.25 ${unit}`);
    for (const foods of await page.locator('.saved-nutrition-foods').all()) {
      await expect(foods).not.toContainText(/kcal|protein|carbs|fat|протеин|мазнини|въглехидрати/i);
    }
    await expect(page.locator('.saved-nutrition-meal').first().locator('.saved-nutrition-macros')).toContainText('420 kcal');
  });

  test(`missing targets are omitted and plan totals are separate in ${language}`, async ({ page }) => {
    await setup(page, { language });
    await openNutrition(page, language);
    await expect(page.locator('[data-saved-targets]')).toHaveText((language === 'bg' ? 'Калории ' : 'Calories ') + '1700.0000000000000001 kcal');
    await expect(page.locator('[data-saved-targets]')).not.toContainText(/0 g|0 г|protein|carbs|fat|протеин|мазнини|въглехидрати/i);
    await expect(page.locator('.saved-nutrition-total')).toHaveText(language === 'bg' ? 'Общо в плана' : 'Plan total');
    await expect(page.locator('[data-saved-totals]')).toContainText('1680 kcal');
    const value = await page.evaluate(() => savedNutritionQuantity('100.2500000000000001'));
    expect(value).toBe('100.2500000000000001');
  });

  test(`structured empty state never promotes legacy history in ${language}`, async ({ page }) => {
    const calls = await setup(page, { language, data: { latest_plan: null } });
    await openNutrition(page, language);
    const root = page.locator('#saved-nutrition');
    await expect(root).toContainText(language === 'bg' ? 'Още няма запазен валидиран хранителен план.' : 'No validated nutrition plan has been saved yet.');
    await expect(root.locator('.saved-nutrition-meal, [data-saved-targets], [data-saved-totals]')).toHaveCount(0);
    await expect(root).not.toContainText('PRIVATE_LEGACY_NUTRITION');
    await expect(root.locator('#saved-nutrition-create')).toHaveText(language === 'bg' ? 'Създай хранителен план' : 'Create nutrition plan');
    expect(calls.chat).toBe(0);
  });

  test(`no restrictions copy refers only to this saved plan in ${language}`, async ({ page }) => {
    const data = saved(); data.latest_plan.restrictions = [];
    await setup(page, { language, data });
    await openNutrition(page, language);
    await expect(page.locator('[data-nutrition-block="restrictions"]')).toContainText(language === 'bg' ?
      'Няма запазени хранителни ограничения в този план.' : 'No dietary restrictions are saved with this plan.');
  });

  test(`anonymous Nutrition remains truthful and FREE creation is explicit in ${language}`, async ({ page }) => {
    const calls = await setup(page, { language, authenticated: false });
    await page.evaluate(() => ownedStorageSet('apexHistory', JSON.stringify([{ role: 'assistant', content: 'PRIVATE_ANONYMOUS_PLAN' }])));
    await openNutrition(page, language);
    await expect(page.locator('#saved-nutrition')).toContainText(language === 'bg' ?
      'Влез в профила си, за да запазваш и отваряш хранителните си планове между сесиите.' :
      'Sign in to save and reopen your nutrition plans across sessions.');
    await expect(page.locator('#saved-nutrition')).not.toContainText(/unauthenticated|401|PRIVATE_ANONYMOUS_PLAN/);
    expect(calls).toEqual({ chat: 0, reads: 0, writes: 0 });
    await page.route('**/chat', route => route.fulfill({ contentType: 'text/event-stream', body: 'data: {"t":"Local test response"}\n\ndata: {"done":true}\n\n' }));
    const request = page.waitForRequest('**/chat');
    await page.locator('#saved-nutrition-create').click();
    expect((await request).postDataJSON().message).toBe(language === 'bg' ? 'Направи ми хранителен план' : 'Build me a nutrition plan');
    await expect(page.locator('#consult')).toHaveClass(/\bon\b/);
    await expect(page.locator('#panel-modal')).not.toHaveClass(/\bon\b/);
    expect(calls.chat).toBe(1);
  });
}

test('saved plan CTA reuses existing nutrition seed only on click', async ({ page }) => {
  const calls = await setup(page);
  await openNutrition(page);
  await page.route('**/chat', route => route.fulfill({ contentType: 'text/event-stream', body: 'data: {"done":true}\n\n' }));
  const request = page.waitForRequest('**/chat');
  await page.locator('#saved-nutrition-create').click();
  expect((await request).postDataJSON().message).toBe('Build me a nutrition plan');
  expect(calls.chat).toBe(1);
});

test('unavailable account data is not presented as an empty plan', async ({ page }) => {
  await setup(page, { status: 503, data: { error: 'nutrition_data_unavailable' } });
  await openNutrition(page);
  await expect(page.locator('#saved-nutrition')).toContainText('Nutrition data is unavailable at the moment.');
  await expect(page.locator('#saved-nutrition')).not.toContainText('No validated nutrition plan has been saved yet.');
});

test('a response arriving after account ownership changes is discarded', async ({ page }) => {
  await setup(page);
  let release;
  const wait = new Promise(resolve => { release = resolve; });
  await page.route('**/api/nutrition', async route => { await wait; await route.fulfill({ json: saved() }); });
  await page.locator('#menu-btn').click();
  await page.locator('#drawer').getByText('Nutrition', { exact: true }).click();
  await expect(page.locator('#saved-nutrition')).toHaveAttribute('aria-busy', 'true');
  await page.evaluate(() => { SESSION.authenticated = false; rotateAnonymousOwner(); showNutrition(); });
  release();
  await expect(page.locator('#saved-nutrition')).toContainText('Sign in to save and reopen');
  await expect(page.locator('.saved-nutrition-meal')).toHaveCount(0);
});

for (const width of [1440, 390, 360]) {
  test(`Nutrition at ${width}px is readable, scrollable and leaves Core unchanged`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 1440 ? 900 : width === 390 ? 844 : 800 });
    await setup(page, { language: 'bg' });
    const before = await page.locator('#core').boundingBox();
    await openNutrition(page, 'bg');
    const sheet = page.locator('#panel-modal .sheet');
    expect(await sheet.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const row of await page.locator('#saved-nutrition li').all()) {
      expect(await row.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    }
    await expect(page.locator('#saved-nutrition-create')).toBeInViewport();
    if (process.env.APEX_NUTRITION_SCREENSHOTS) {
      await page.screenshot({ path: require('path').join(process.env.APEX_NUTRITION_SCREENSHOTS, `nutrition-${width}.png`) });
      await page.locator('[data-nutrition-block="targets"]').scrollIntoViewIfNeeded();
      await page.screenshot({ path: require('path').join(process.env.APEX_NUTRITION_SCREENSHOTS, `nutrition-targets-${width}.png`) });
    }
    await page.locator('#panel-close').scrollIntoViewIfNeeded();
    await page.locator('#panel-close').click();
    expect(await page.locator('#core').boundingBox()).toEqual(before);
    await expect(page.locator('#core')).toBeVisible();
  });
}

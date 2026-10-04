const { test, expect } = require('@playwright/test');

const profile = {
  goal: 'strength', age: '30', weight: '75', height: '178', gender: 'male',
  level: 'intermediate', equipment: 'home', sleepQuality: 'average',
  stressLevel: 'moderate', recoveryFeel: 'ok', activityLevel: 'moderate', frequency: '3',
};

async function prepare(page, { saved = null, accountLanguage = null, legacyLanguage = false } = {}) {
  await page.addInitScript(({ saved, profile }) => {
    if (sessionStorage.getItem('language-test-seeded')) return;
    sessionStorage.setItem('language-test-seeded', 'true');
    if (saved !== null) localStorage.setItem('apexLang', saved);
    localStorage.setItem('apexAnonymousOwnerV1', 'language-test');
    localStorage.setItem('apexOwnedV1:anonymous:language-test:apexProfile', JSON.stringify(profile));
  }, { saved, profile });
  const state = { profile: { ...profile }, writes: [], reads: 0 };
  if (accountLanguage) state.profile[legacyLanguage ? 'lang' : 'language'] = accountLanguage;
  await page.route('**/auth/me', route => route.fulfill({ json: {
    authenticated: accountLanguage !== null, email: accountLanguage ? 'language@example.test' : null,
    plan: 'free', status: 'free',
  } }));
  await page.route('**/api/profile', async route => {
    if (route.request().method() === 'PUT') {
      state.profile = route.request().postDataJSON().profile;
      state.writes.push(state.profile);
      await route.fulfill({ json: { ok: true } });
    } else {
      state.reads++;
      await route.fulfill({ json: { profile: state.profile, training_constraints: [] } });
    }
  });
  await page.route('**/api/history', route => route.fulfill({ json: { workouts: [] } }));
  await page.route('**/api/conversations?limit=60', route => route.fulfill({ json: { messages: [] } }));
  return state;
}

async function expectLanguage(page, language) {
  await expect.poll(() => page.evaluate(() => typeof lang === 'string' ? lang : null)).toBe(language);
  await expect(page.locator('html')).toHaveAttribute('lang', language);
  await expect(page.locator('#brand-tagline')).toHaveText(
    language === 'en' ? 'Your peak. Your pulse.' : 'Твоят връх. Твоят пулс.',
  );
}

for (const authenticated of [false, true]) {
  test.describe(`landing continuity ${authenticated ? 'authenticated' : 'anonymous'}`, () => {
    test.use({ locale: 'bg-BG', viewport: { width: 390, height: 844 } });
    for (const [path, language] of [['/', 'bg'], ['/en', 'en']]) {
      test(`${path} CTA keeps ${language} despite opposite saved/account preference`, async ({ page }) => {
        const opposite = language === 'en' ? 'bg' : 'en';
        const state = await prepare(page, { saved: opposite, accountLanguage: authenticated ? opposite : null });
        await page.goto(path);
        expect(await page.evaluate(() => localStorage.getItem('apexLang'))).toBe(opposite);
        await page.locator('.nav-cta').click();
        await expectLanguage(page, language);
        await expect.poll(() => page.evaluate(() => localStorage.getItem('apexLang'))).toBe(language);
        if (authenticated) {
          await expect.poll(() => state.profile.language).toBe(language);
          expect(state.profile).toEqual({ ...profile, language });
          expect(state.writes).toHaveLength(1);
        }
      });
    }
  });
}

for (const [locale, saved, expected] of [
  ['bg-BG', 'en', 'en'], ['en-US', 'bg', 'bg'],
  ['en-US', null, 'en'], ['bg-BG', null, 'bg'],
]) {
  test.describe(`browser ${locale}, saved ${saved}`, () => {
    test.use({ locale });
    test(`direct app resolves to ${expected}`, async ({ page }) => {
      await prepare(page, { saved });
      await page.goto('/app');
      await expectLanguage(page, expected);
    });
  });
}

for (const language of ['en', 'bg']) {
  test(`explicit ${language} survives account sync, query cleanup, and refresh`, async ({ page }) => {
    const opposite = language === 'en' ? 'bg' : 'en';
    const state = await prepare(page, { saved: opposite, accountLanguage: opposite });
    await page.goto('/app?lang=' + language);
    await expect.poll(() => state.profile.language).toBe(language);
    await expectLanguage(page, language);
    await expect(page).toHaveURL(/\/app$/);
    expect(state.writes).toEqual([{ ...profile, language }]);
    await page.evaluate(() => loadSession(null));
    await expectLanguage(page, language);
    expect(state.writes).toHaveLength(1);
    await page.reload();
    await expectLanguage(page, language);
    await expect.poll(() => state.reads).toBeGreaterThanOrEqual(3);
    expect(state.writes).toHaveLength(1);
  });
}

test('saved preference beats an opposite authenticated profile without a query', async ({ page }) => {
  const state = await prepare(page, { saved: 'en', accountLanguage: 'bg' });
  await page.goto('/app');
  await expect.poll(() => state.profile.language).toBe('en');
  await expectLanguage(page, 'en');
  expect(state.profile).toEqual({ ...profile, language: 'en' });
});

test.describe('account preference fallback', () => {
  test.use({ locale: 'en-US' });
  test('account preference beats browser fallback when no local preference exists', async ({ page }) => {
    const state = await prepare(page, { accountLanguage: 'bg' });
    await page.goto('/app');
    await expectLanguage(page, 'bg');
    expect(await page.evaluate(() => localStorage.getItem('apexLang'))).toBe('bg');
    expect(state.writes).toHaveLength(0);
  });
  test('legacy profile lang is respected and synchronized without losing fields', async ({ page }) => {
    const state = await prepare(page, { saved: 'en', accountLanguage: 'bg', legacyLanguage: true });
    await page.goto('/app');
    await expect.poll(() => state.profile.language).toBe('en');
    await expectLanguage(page, 'en');
    expect(state.profile).toEqual({ ...profile, language: 'en', lang: 'en' });
  });
});

test('in-app language switch replaces the navigation choice and persists after refresh', async ({ page }) => {
  const state = await prepare(page, { accountLanguage: 'en' });
  await page.goto('/app?lang=en');
  await expect.poll(() => state.reads).toBe(1);
  await page.evaluate(() => toggleLang());
  await expect.poll(() => state.profile.language).toBe('bg');
  await expectLanguage(page, 'bg');
  await page.evaluate(() => loadSession(null));
  await expectLanguage(page, 'bg');
  await page.reload();
  await expectLanguage(page, 'bg');
  expect(state.profile).toEqual({ ...profile, language: 'bg' });
});

test('failed account profile fetch never causes a partial profile upload', async ({ page }) => {
  const state = await prepare(page, { accountLanguage: 'bg' });
  await page.route('**/api/profile', route => route.fulfill({ status: 503, json: { error: 'unavailable' } }));
  await page.goto('/app?lang=en');
  await expect.poll(() => page.evaluate(() => SESSION.authenticated)).toBe(true);
  await expectLanguage(page, 'en');
  expect(state.writes).toHaveLength(0);
  expect(state.profile).toEqual({ ...profile, language: 'bg' });
});

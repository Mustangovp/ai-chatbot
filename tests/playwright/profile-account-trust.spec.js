const { test, expect } = require('@playwright/test');
const path = require('path');

const profile = { goal: 'strength', age: '33', weight: '76', height: '178', gender: 'male',
  level: 'intermediate', equipment: 'home', sleepQuality: 'average', stressLevel: 'moderate',
  recoveryFeel: 'ok', activityLevel: 'moderate', frequency: '3', notes: '',
  allergies: 'synthetic food', foodPreferences: ['synthetic preference'], preferences: { synthetic: true } };
const deferred = () => { let release; const promise = new Promise(resolve => { release = resolve; }); return { promise, release }; };

async function setup(page, { language = 'en', authenticated = true, cached = null, accountProfile = {} } = {}) {
  const state = { current: authenticated ? 'a' : null, reads: [], writes: [], logoutCalls: 0, syncCalls: 0,
    profileStatus: 200, putStatus: 200, putAck: true, logoutStatus: 200, logoutAck: true,
    accounts: {
      a: { email: 'account-a@example.test', profile: { ...profile, ...accountProfile, language },
        constraints: [{ id: 'constraint-a', pattern: 'vertical_push', removable: true }],
        messages: [{ role: 'assistant', content: 'ACCOUNT_A_PRIVATE_SYNTHETIC' }], workouts: [] },
      b: { email: 'account-b@example.test', profile: { ...profile, age: '55', language }, constraints: [], messages: [], workouts: [] },
    } };
  await page.addInitScript(({ language, profile, cached }) => {
    if (sessionStorage.getItem('account-trust-seeded')) return;
    sessionStorage.setItem('account-trust-seeded', 'yes');
    localStorage.setItem('apexAnonymousOwnerV1', 'account-trust-anon'); localStorage.setItem('apexLang', language);
    localStorage.setItem('apexOwnedV1:anonymous:account-trust-anon:apexProfile', JSON.stringify({ ...profile, age: '22', notes: 'ANONYMOUS_ONLY' }));
    if (cached) localStorage.setItem('apexOwnedV1:account:account-a@example.test:apexProfile', JSON.stringify(cached));
  }, { language, profile, cached });
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/sync') state.syncCalls++; });
  await page.route('**/auth/me', route => route.fulfill({ json: { authenticated: !!state.current,
    email: state.current ? state.accounts[state.current].email : null, plan: 'free', status: 'free' } }));
  await page.route('**/api/profile', async route => {
    const owner = state.current, account = state.accounts[owner];
    if (route.request().method() === 'PUT') {
      const patch = route.request().postDataJSON().profile; state.writes.push({ owner, patch });
      if (state.putHold) await state.putHold.promise;
      if (state.putNetworkFailure) return route.abort('failed');
      if (state.putStatus === 200 && state.putAck) account.profile = { ...account.profile, ...patch };
      return route.fulfill({ status: state.putStatus, json: { ok: state.putAck, profile: account.profile } });
    }
    const snapshot = structuredClone(account || { profile: {}, constraints: [] });
    state.reads.push('profile'); if (state.readHold) await state.readHold.promise;
    return route.fulfill({ status: state.profileStatus, json: { profile: snapshot.profile,
      training_constraint_records: state.constraintUnavailable ? null : snapshot.constraints,
      training_constraint_load_state: state.constraintUnavailable ? 'unavailable' : 'ready' } });
  });
  for (const [url, kind] of [['**/api/history', 'history'], ['**/api/conversations?*', 'conversation']]) {
    await page.route(url, async route => {
      const account = structuredClone(state.accounts[state.current] || { workouts: [], messages: [] });
      state.reads.push(kind); if (state.readHold) await state.readHold.promise;
      return route.fulfill({ json: kind === 'history' ? { workouts: account.workouts } : { messages: account.messages } });
    });
  }
  await page.route('**/auth/logout', async route => {
    state.logoutCalls++; if (state.logoutHold) await state.logoutHold.promise;
    if (state.logoutNetworkFailure) return route.abort('failed');
    if (state.logoutStatus === 200 && state.logoutAck) state.current = null;
    return route.fulfill({ status: state.logoutStatus, json: { ok: state.logoutAck } });
  });
  await page.goto('/app?lang=' + language);
  await expect.poll(() => page.evaluate(() => DATA_OWNER.kind)).toBe(authenticated ? 'account' : 'anonymous');
  await expect.poll(() => page.evaluate(() => pfLoad().age)).toBe(authenticated ? '33' : '22');
  return state;
}
async function openProfile(page) {
  await page.locator('#menu-btn').click(); await page.locator('[onclick="menuAction(\'profile\')"]').click();
  await expect(page.locator('#profile-modal')).toHaveClass(/\bon\b/);
}
async function saveAge(page, age = '44') {
  await openProfile(page); await page.locator('#pf-age').fill(age);
  await page.locator('#w1-next').click(); await page.locator('#w2-next').click(); await page.locator('#w3-save').click();
}
async function assertNoA(page) {
  expect(await page.evaluate(() => JSON.stringify({ profile: pfLoad(), history: getHistory(), constraints: ACTIVE_TRAINING_CONSTRAINTS }))).not.toContain('ACCOUNT_A_PRIVATE_SYNTHETIC');
  await expect(page.locator('#feed')).not.toContainText('ACCOUNT_A_PRIVATE_SYNTHETIC');
  expect(await page.locator('#pf-notes').inputValue()).not.toContain('ACCOUNT_A_PRIVATE_SYNTHETIC');
}

for (const next of ['anonymous', 'b', 'a-again']) {
  test(`P0: delayed account sync is discarded after transition to ${next}`, async ({ page }) => {
    const state = await setup(page, { accountProfile: { notes: 'ACCOUNT_A_PRIVATE_SYNTHETIC' } });
    await page.evaluate(() => { openProfile(2); enterConsult(''); appendCoach().textContent = 'ACCOUNT_A_PRIVATE_SYNTHETIC'; });
    state.readHold = deferred(); state.reads = [];
    await page.evaluate(() => { window.oldAccountSync = syncFromAccount(); });
    await expect.poll(() => state.reads.length).toBe(3);
    const held = state.readHold; state.readHold = null;
    await page.evaluate(() => logout());
    await assertNoA(page);
    if (next !== 'anonymous') {
      state.current = next === 'b' ? 'b' : 'a';
      if (next === 'a-again') state.accounts.a.profile.notes = 'NEW_ACCOUNT_A_TRUTH';
      await page.evaluate(() => loadSession(null));
    }
    held.release(); await page.evaluate(() => window.oldAccountSync);
    if (next === 'a-again') expect(await page.evaluate(() => pfLoad().notes)).toBe('NEW_ACCOUNT_A_TRUTH');
    else await assertNoA(page);
    expect(await page.evaluate(() => ACTIVE_TRAINING_CONSTRAINTS.length)).toBe(next === 'a-again' ? 1 : 0);
    expect(await page.evaluate(() => localStorage.getItem('apexOwnedV1:account:account-a@example.test:apexProfile'))).toBeTruthy();
  });
}

test('P0: owner transition clears draft, chat, panels and workout transient state', async ({ page }) => {
  await setup(page, { accountProfile: { notes: 'ACCOUNT_A_PRIVATE_SYNTHETIC' } });
  await page.evaluate(() => { openProfile(2); enterConsult(''); appendCoach().textContent = 'ACCOUNT_A_PRIVATE_SYNTHETIC';
    pendingWorkouts = { foreign: [{ name: 'ACCOUNT_A_PRIVATE_SYNTHETIC' }] }; pendingTrainingCompletion = { plan_id: 'foreign' };
    showPanel('Foreign', '<p>ACCOUNT_A_PRIVATE_SYNTHETIC</p>'); });
  await page.evaluate(() => logout()); await assertNoA(page);
  expect(await page.evaluate(() => ({ pendingWorkouts, pendingTrainingCompletion, WO, history: getHistory() }))).toEqual({ pendingWorkouts: {}, pendingTrainingCompletion: null, WO: null, history: [] });
  await expect(page.locator('#profile-modal')).not.toHaveClass(/\bon\b/); await expect(page.locator('#panel-modal')).not.toHaveClass(/\bon\b/);
  await expect(page.locator('#panel-body')).toBeEmpty(); await expect(page.locator('#brief-context')).not.toContainText('Get stronger');
});

test('P0: late auth/me cannot sign the previous account back in after confirmed logout', async ({ page }) => {
  await setup(page); const held = deferred(); let started = false;
  await page.route('**/auth/me', async route => { started = true; await held.promise;
    await route.fulfill({ json: { authenticated: true, email: 'account-a@example.test', plan: 'free' } }); });
  await page.evaluate(() => { window.oldSessionRead = loadSession(null); }); await expect.poll(() => started).toBe(true);
  await page.evaluate(() => logout()); held.release(); expect(await page.evaluate(() => window.oldSessionRead)).toBeNull();
  expect(await page.evaluate(() => SESSION.authenticated)).toBe(false); await assertNoA(page);
});

for (const stage of ['headers', 'chunk', 'json']) {
  test(`P0: old chat ${stage} cannot deliver content or metadata after logout`, async ({ page }) => {
    await setup(page);
    await page.evaluate(stage => {
      const original = window.fetch; window.chatGateStarted = false;
      const wait = new Promise(resolve => { window.releaseChatGate = resolve; });
      const payload = { t: 'ACCOUNT_A_PRIVATE_SYNTHETIC', training_completion: { plan_id: 'ACCOUNT_A_PRIVATE_SYNTHETIC' }, done: true };
      window.fetch = async (url, options) => {
        if (url !== '/chat') return original(url, options);
        if (stage === 'headers') {
          window.chatGateStarted = true; await wait;
          return new Response('data: ' + JSON.stringify(payload) + '\n\n', { headers: { 'Content-Type': 'text/event-stream' } });
        }
        if (stage === 'json') return { ok: true, headers: new Headers({ 'Content-Type': 'application/json' }),
          json: async () => { window.chatGateStarted = true; await wait; return { reply: 'ACCOUNT_A_PRIVATE_SYNTHETIC' }; } };
        return { ok: true, headers: new Headers({ 'Content-Type': 'text/event-stream' }), body: { getReader: () => ({
          read: async () => { window.chatGateStarted = true; await wait; return { done: false, value: new TextEncoder().encode('data: ' + JSON.stringify(payload) + '\n\n') }; },
          cancel: () => Promise.resolve() }) } };
      };
      const exchange = ChatLifecycle.begin('synthetic request', {}, getHistory());
      window.oldChat = runChatExchange(exchange, { message: 'synthetic request' });
    }, stage);
    await expect.poll(() => page.evaluate(() => window.chatGateStarted)).toBe(true);
    await page.evaluate(() => logout()); await page.evaluate(() => releaseChatGate()); await page.evaluate(() => window.oldChat);
    await assertNoA(page); expect(await page.evaluate(() => pendingTrainingCompletion)).toBeNull();
    expect(await page.evaluate(() => getHistory())).toEqual([]);
  });
}

test('P0: late account projection read cannot affect the next owner', async ({ page }) => {
  await setup(page); const held = deferred(); let started = false;
  await page.route('**/api/profile', async route => { started = true; await held.promise;
    await route.fulfill({ json: { athlete_core: { recovery_bias: 'protective' } } }); });
  await page.evaluate(() => { window.oldProjection = refreshAthleteCoreProjection(); }); await expect.poll(() => started).toBe(true);
  await page.evaluate(() => logout()); held.release(); expect(await page.evaluate(() => window.oldProjection)).toBe(false);
  expect(await page.evaluate(() => core.presence.serverProjection)).toBeNull();
});

test('server profile replaces stale account fields and anonymous state is never uploaded', async ({ page }) => {
  const state = await setup(page, { cached: { ...profile, age: '99', staleOnly: 'foreign cached value' } });
  expect(await page.evaluate(() => pfLoad())).toEqual(state.accounts.a.profile);
  expect(state.writes).toEqual([]); expect(state.syncCalls).toBe(0);
  state.accounts.a.profile = { language: 'en' }; state.accounts.a.messages = [];
  await page.evaluate(() => syncFromAccount());
  expect(await page.evaluate(() => pfLoad())).toEqual({ language: 'en' }); expect(await page.evaluate(() => getHistory())).toEqual([]);
});

test('profile success waits for a valid acknowledgement and preserves hidden fields', async ({ page }) => {
  const state = await setup(page); state.putHold = deferred(); await saveAge(page);
  await expect.poll(() => state.writes.length).toBe(1);
  await expect(page.locator('#profile-modal')).toHaveAttribute('aria-busy', 'true'); await expect(page.locator('#w3-save')).toBeDisabled();
  await expect(page.locator('#profile-status')).toHaveText('Saving to your account…');
  expect(await page.evaluate(() => pfLoad().age)).toBe('33'); await expect(page.locator('#profile-modal')).toHaveClass(/\bon\b/);
  state.putHold.release(); await expect(page.locator('#profile-modal')).not.toHaveClass(/\bon\b/);
  await expect(page.locator('#toast')).toHaveText('Profile saved to your account.');
  expect(state.writes[0].patch).toEqual({ language: 'en', age: '44' });
  expect(state.accounts.a.profile).toMatchObject({ age: '44', allergies: profile.allergies, foodPreferences: profile.foodPreferences, preferences: profile.preferences });
  await page.reload(); await expect.poll(() => page.evaluate(() => pfLoad().age)).toBe('44');
});

test('editing visible lifestyle fields does not replace independent unexposed account evidence', async ({ page }) => {
  const state = await setup(page, { accountProfile: { healthNotes: 'independent synthetic account evidence',
    _medical_hold: { status: 'synthetic existing flag' } } });
  await openProfile(page); await page.locator('#w1-next').click(); await page.locator('#w2-next').click();
  await page.locator('#pf-meds').fill('synthetic medication field'); await page.locator('#w3-save').click();
  await expect(page.locator('#profile-modal')).not.toHaveClass(/\bon\b/);
  expect(state.writes[0].patch).toEqual({ language: 'en', medications: 'synthetic medication field' });
  expect(state.accounts.a.profile).toMatchObject({ healthNotes: 'independent synthetic account evidence',
    allergies: profile.allergies, foodPreferences: profile.foodPreferences, _medical_hold: { status: 'synthetic existing flag' } });
});

for (const failure of ['503', 'network', 'invalid-ack']) for (const language of ['bg', 'en']) {
  test(`profile ${failure} keeps draft for retry with truthful ${language} status`, async ({ page }) => {
    const state = await setup(page, { language });
    if (failure === '503') state.putStatus = 503; if (failure === 'network') state.putNetworkFailure = true;
    if (failure === 'invalid-ack') state.putAck = false;
    await saveAge(page);
    await expect(page.locator('#profile-status')).toContainText(language === 'en' ? 'Could not save' : 'Не успяхме да запазим');
    await expect(page.locator('#profile-status')).toHaveAttribute('aria-live', 'polite');
    await expect(page.locator('#pf-age')).toHaveValue('44'); await expect(page.locator('#w3-save')).toBeEnabled();
    await expect(page.locator('#profile-modal')).toHaveClass(/\bon\b/); expect(state.accounts.a.profile.age).toBe('33');
    await expect(page.locator('#toast')).not.toContainText(language === 'en' ? 'Profile saved' : 'Профилът е запазен');
    state.putStatus = 200; state.putNetworkFailure = false; state.putAck = true; await page.locator('#w3-save').click();
    await expect(page.locator('#profile-modal')).not.toHaveClass(/\bon\b/); expect(state.accounts.a.profile.age).toBe('44');
  });
}

test('P0: old profile save acknowledgement cannot write or announce under another owner', async ({ page }) => {
  const state = await setup(page); state.putHold = deferred(); await saveAge(page); await expect.poll(() => state.writes.length).toBe(1);
  const save = state.putHold; state.putHold = null; await page.evaluate(() => logout());
  state.current = 'b'; await page.evaluate(() => loadSession(null));
  const ack = page.waitForResponse(response => response.url().endsWith('/api/profile') && response.request().method() === 'PUT');
  save.release(); await ack;
  await expect.poll(() => page.evaluate(() => pfLoad().age)).toBe('55'); await expect(page.locator('#toast')).not.toHaveText('Profile saved to your account.');
});

test('old same-owner profile read cannot roll back a confirmed explicit save', async ({ page }) => {
  const state = await setup(page); state.readHold = deferred(); await page.evaluate(() => { window.oldRead = syncFromAccount(); });
  await expect.poll(() => state.reads.length).toBe(6); const read = state.readHold; state.readHold = null;
  await saveAge(page); await expect(page.locator('#profile-modal')).not.toHaveClass(/\bon\b/);
  read.release(); await page.evaluate(() => window.oldRead); expect(await page.evaluate(() => pfLoad().age)).toBe('44');
});

test('logout waits for acknowledgement before changing identity', async ({ page }) => {
  const state = await setup(page); state.logoutHold = deferred(); await page.evaluate(() => { window.logoutResult = logout(); });
  await expect.poll(() => state.logoutCalls).toBe(1); expect(await page.evaluate(() => SESSION.authenticated)).toBe(true);
  expect(await page.evaluate(() => DATA_OWNER.kind)).toBe('account'); await expect(page.locator('#toast')).not.toHaveText('Signed out.');
  state.logoutHold.release(); expect(await page.evaluate(() => window.logoutResult)).toBe(true); expect(await page.evaluate(() => DATA_OWNER.kind)).toBe('anonymous');
});

for (const failure of ['503', 'network', 'invalid-ack']) {
  test(`failed logout ${failure} keeps account authority`, async ({ page }) => {
    const state = await setup(page);
    if (failure === '503') state.logoutStatus = 503; if (failure === 'network') state.logoutNetworkFailure = true;
    if (failure === 'invalid-ack') state.logoutAck = false;
    expect(await page.evaluate(() => logout())).toBe(false); expect(await page.evaluate(() => SESSION.authenticated)).toBe(true);
    expect(await page.evaluate(() => dataOwnerToken())).toBe('account:account-a@example.test'); await expect(page.locator('#toast')).toContainText('Could not sign out');
  });
}

for (const language of ['bg', 'en']) {
  test(`constraint loading failure is not empty in ${language}`, async ({ page }) => {
    const state = await setup(page, { language }); state.constraintUnavailable = true; await page.evaluate(() => syncFromAccount()); await openProfile(page);
    await expect(page.locator('#training-constraints')).toHaveAttribute('data-load-state', 'unavailable');
    await expect(page.locator('#training-constraints-status')).toContainText(language === 'en' ? 'could not be loaded' : 'не са заредени');
    await expect(page.locator('#training-constraints-status')).not.toContainText(language === 'en' ? 'No active' : 'Няма записани');
    state.constraintUnavailable = false; await page.evaluate(() => syncFromAccount());
    await expect(page.locator('#training-constraints')).toContainText(language === 'en' ? 'Avoid overhead pressing' : 'Избягвай преси над глава');
    await page.locator('#profile-cancel').click(); await page.reload(); await openProfile(page);
    await expect(page.locator('#training-constraints-list')).toContainText(language === 'en' ? 'Avoid overhead pressing' : 'Избягвай преси над глава');
  });

  test(`local reset is current-owner only, retains server truth and device settings in ${language}`, async ({ page }) => {
    const state = await setup(page, { language });
    await page.evaluate(() => { apexStorageSet('apexVoice', 'calm'); ownedStorageSet('apexCoachMemory', JSON.stringify({ synthetic: true })); showSettings(); });
    await expect(page.locator('.settings-reset-note')).toContainText(language === 'en' ? 'Does not delete account data' : 'Не изтрива данните в акаунта');
    await expect(page.locator('.settings-reset-note')).toContainText(language === 'en' ? 'return after refresh' : 'върнат след обновяване');
    page.once('dialog', dialog => dialog.accept()); await page.locator('[onclick="resetLocal()"]').click();
    await expect(page.locator('#profile-modal')).toHaveClass(/\bon\b/);
    expect(await page.evaluate(() => OWNED_STORAGE_KEYS.map(key => ownedStorageGet(key)))).toEqual([null, null, null, null]);
    expect(await page.evaluate(() => ({ language: apexStorageGet('apexLang'), voice: VoiceReg.current(), authenticated: SESSION.authenticated,
      anonymous: !!localStorage.getItem('apexOwnedV1:anonymous:account-trust-anon:apexProfile') }))).toEqual({ language, voice: 'calm', authenticated: true, anonymous: true });
    expect(state.writes).toEqual([]); expect(state.accounts.a.profile.allergies).toBe(profile.allergies);
    await page.reload(); await openProfile(page); await expect(page.locator('#training-constraints-list')).toContainText(language === 'en' ? 'Avoid overhead pressing' : 'Избягвай преси над глава');
    await expect(page.locator('#pf-age')).toHaveValue('33'); expect(await page.evaluate(() => VoiceReg.current())).toBe('calm');
  });
}

test('Cancel and backdrop discard draft without mutating local or account truth', async ({ page }) => {
  const state = await setup(page); await openProfile(page); await page.locator('#pf-age').fill('77'); await page.locator('#profile-cancel').click();
  await expect(page.locator('#menu-btn')).toBeFocused(); await openProfile(page); await expect(page.locator('#pf-age')).toHaveValue('33');
  await page.locator('#w1-next').click(); await page.locator('#w2-next').click(); await page.locator('#pf-notes').fill('UNSAVED_DRAFT');
  await page.locator('#profile-modal').click({ position: { x: 2, y: 2 } }); await openProfile(page); await page.locator('#w1-next').click(); await page.locator('#w2-next').click();
  await expect(page.locator('#pf-notes')).toHaveValue(''); expect(state.writes).toEqual([]);
});

test('unknown profile values are not fabricated by preselected controls', async ({ page }) => {
  await setup(page); await page.evaluate(() => { ownedStorageSet('apexProfile', '{}'); openProfile(); });
  for (const id of ['pf-goal', 'pf-gender', 'pf-level', 'pf-equip', 'pf-sleep', 'pf-stress', 'pf-recovery', 'pf-freq'])
    await expect(page.locator('#' + id)).toHaveValue('');
});

test('language save after local reset sends only an explicit language patch', async ({ page }) => {
  const state = await setup(page); page.once('dialog', dialog => dialog.accept()); await page.evaluate(() => resetLocal());
  await page.evaluate(() => toggleLang()); await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].patch).toEqual({ language: 'bg' }); expect(state.accounts.a.profile.allergies).toBe(profile.allergies);
  expect(await page.evaluate(() => lang)).toBe('bg');
});

test('profile keyboard semantics, focus containment, Escape and restoration', async ({ page }) => {
  await setup(page); await openProfile(page); const modal = page.locator('#profile-modal');
  await expect(modal).toHaveAttribute('role', 'dialog'); await expect(modal).toHaveAttribute('aria-modal', 'true');
  await expect(modal).toHaveAttribute('aria-labelledby', 'w1-title'); await expect(page.locator('#w1-title')).toBeFocused();
  await page.keyboard.press('Shift+Tab'); await expect(page.locator('#profile-cancel')).toBeFocused(); await page.keyboard.press('Tab'); await expect(page.locator('#pf-goal')).toBeFocused();
  for (let count = 0; count < 15; count++) { await page.keyboard.press('Tab'); expect(await page.evaluate(() => !!document.activeElement.closest('#profile-modal'))).toBe(true); }
  await page.keyboard.press('Escape'); await expect(modal).not.toHaveClass(/\bon\b/); await expect(page.locator('#menu-btn')).toBeFocused();
});

for (const language of ['bg', 'en']) for (const width of [1440, 390, 360]) {
  test(`profile/settings geometry, labels and Save/Cancel at ${width}px in ${language}`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 1440 ? 900 : width === 390 ? 844 : 800 });
    await setup(page, { language }); await openProfile(page);
    for (let step = 1; step <= 3; step++) {
      if (step > 1) await page.locator('#w' + (step - 1) + '-next').click();
      const sheet = page.locator('#profile-modal .sheet'); expect(await sheet.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (process.env.APEX_PROFILE_SCREENSHOTS) await page.screenshot({ path: path.join(process.env.APEX_PROFILE_SCREENSHOTS, `profile-${language}-${width}-${step}.png`), animations: 'disabled' });
    }
    for (const id of ['pf-meds', 'pf-supps', 'pf-injuries', 'pf-surgeries', 'pf-limits', 'pf-notes']) {
      const input = page.locator('#' + id); expect(await input.evaluate(el => !!document.querySelector(`label[for="${el.id}"]`))).toBe(true);
      if (language === 'bg') expect(await input.getAttribute('placeholder')).toMatch(/[А-Яа-я]/);
      if (width < 500) expect(await input.evaluate(el => el.clientWidth)).toBeGreaterThan(250);
    }
    await page.locator('#w3-save').scrollIntoViewIfNeeded(); await expect(page.locator('#w3-save')).toBeInViewport();
    await page.locator('#profile-cancel').scrollIntoViewIfNeeded(); await expect(page.locator('#profile-cancel')).toBeInViewport();
    if (process.env.APEX_PROFILE_SCREENSHOTS) await page.screenshot({ path: path.join(process.env.APEX_PROFILE_SCREENSHOTS, `profile-bottom-${language}-${width}.png`), animations: 'disabled' });
    await page.locator('#profile-cancel').click(); await page.locator('#menu-btn').click(); await page.locator('[onclick="menuAction(\'settings\')"]').click();
    await expect(page.locator('#panel-title')).toBeFocused(); await expect(page.locator('#settings-language')).toHaveText(language.toUpperCase());
    await page.locator('#panel-modal .sheet').evaluate(el => Promise.all(el.getAnimations().map(animation => animation.finished)));
    expect(await page.locator('#settings-language').evaluate(el => el.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    await expect(page.locator('#voice-select')).toBeVisible(); expect(await page.locator('#panel-modal .sheet').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    if (process.env.APEX_PROFILE_SCREENSHOTS) await page.screenshot({ path: path.join(process.env.APEX_PROFILE_SCREENSHOTS, `settings-${language}-${width}.png`), animations: 'disabled' });
  });
}

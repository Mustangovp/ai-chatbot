const { test, expect } = require('@playwright/test');

test.use({ baseURL: process.env.LIVE_VOICE_BASE_URL || 'http://127.0.0.1:5001' });

const available = {
  tts: { remaining_requests: 4, available: true, error: null },
  media: { remaining_seconds: 120, session_seconds: 120, available: true, error: null },
};

async function mount(page, language = 'en') {
  await page.goto('/app?lang=' + language);
  await page.evaluate(async () => {
    await loadSession(); enterConsult(''); document.getElementById('profile-modal').classList.remove('on');
  });
}

for (const language of ['bg', 'en']) {
  for (const kind of ['tts', 'media']) {
    test(`${language}: ${kind} exhaustion prevents microphone, WebSocket and speech; text still works`, async ({ page }) => {
      const allowance = JSON.parse(JSON.stringify(available));
      allowance[kind].available = false; allowance[kind].error = kind + '_quota_exhausted';
      allowance[kind][kind === 'tts' ? 'remaining_requests' : 'remaining_seconds'] = 0;
      let statusCalls = 0, speechCalls = 0, chatCalls = 0;
      await page.route('**/api/live-voice/allowances', route => {
        statusCalls++; return route.fulfill({ json: allowance });
      });
      await page.route('**/speak', route => { speechCalls++; return route.abort(); });
      await page.route('**/chat', route => {
        chatCalls++; return route.fulfill({ contentType: 'text/event-stream', body: 'data: {"t":"Text works"}\n\ndata: {"done":true}\n\n' });
      });
      await mount(page, language);
      const result = await page.evaluate(async () => {
        LIVE_VOICE_CONFIG.transport = 'relay'; window.microphones = 0; window.sockets = 0;
        Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true, value: async () => { microphones++; throw new Error('must not open microphone'); } });
        window.WebSocket = class { constructor() { sockets++; } };
        await Voice.start(); await Voice.start();
        return { microphones, sockets, on: Voice.on, blocked: Voice.blockedCode, state: Voice.state };
      });
      expect(result).toEqual({ microphones: 0, sockets: 0, on: false, blocked: kind + '_quota_exhausted', state: 'ERROR' });
      expect(statusCalls).toBe(1); expect(speechCalls).toBe(0);
      await expect(page.locator('#mic-btn')).toBeDisabled();
      await expect(page.locator('#toast')).toContainText(language === 'bg' ? 'изчерпан' : 'remaining');
      await expect(page.locator('#toast')).not.toContainText('временно недостъпен');
      await page.locator('#user-in').fill('A safe text question');
      await page.locator('.send-btn').click();
      await expect(page.locator('#feed')).toContainText('Text works');
      expect(chatCalls).toBe(1); expect(speechCalls).toBe(0);
    });
  }
}

test('handshake race rechecks status once, without reconnect or microphone fallback', async ({ page }) => {
  await mount(page);
  const result = await page.evaluate(async () => {
    let checks = 0, sockets = 0, stopped = 0, error;
    const transport = new ApexLiveVoice.RelayTransport({
      preflight: async () => ++checks === 1 ? { tts: { available: true }, media: { available: true } }
        : { tts: { available: true }, media: { available: false, error: 'media_quota_exhausted' } },
      media: { getUserMedia: async () => ({ getTracks: () => [{ stop() { stopped++; } }] }) },
      Socket: class { constructor() { sockets++; queueMicrotask(() => { this.onerror(); this.onclose(); }); } close() {} },
      Context: class {}, Worklet: class {},
    });
    try { await transport.connect({ language: 'bg', signal: new AbortController().signal, onEvent() {} }); }
    catch (failure) { error = failure.code; transport.close(); }
    return { checks, sockets, stopped, error };
  });
  expect(result).toEqual({ checks: 2, sockets: 1, stopped: 1, error: 'media_quota_exhausted' });
});

test('TTS exhaustion during a session stops speech before another provider-bound request', async ({ page }) => {
  let submissions = 0;
  await page.route('**/api/live-voice/allowances', route => route.fulfill({ json: {
    tts: { remaining_requests: 0, available: false, error: 'tts_quota_exhausted' },
    media: { remaining_seconds: 0, session_seconds: 120, available: false, error: 'media_session_active' },
  } }));
  await page.route('**/speak', route => { submissions++; return route.abort(); });
  await mount(page);
  const result = await page.evaluate(async () => {
    await Voice.start();
    // Already-connected mock stands in for the active relay. The speech path
    // now uses the real, non-billable relay preflight before any POST /speak.
    LIVE_VOICE_CONFIG.transport = 'relay';
    await Voice.say('Synthetic fifth reply');
    return { active: liveVoiceController.active, on: Voice.on, blocked: Voice.blockedCode,
      playback: VoiceOut.lastPlaybackOutcome };
  });
  expect(submissions).toBe(0);
  expect(result).toEqual({ active: false, on: false, blocked: 'tts_quota_exhausted', playback: null });
  await expect(page.locator('#mic-btn')).toBeDisabled();
});

for (const [status, code, message] of [
  [429, 'tts_quota_exhausted', 'no spoken replies remaining'],
  [403, 'forbidden', 'not available to this account'],
  [403, 'pilot_expired', 'Pilot access has expired'],
  [403, 'pilot_disabled', 'voice pilot is disabled'],
  [502, 'tts_unavailable', 'Audio could not be retrieved'],
]) {
  test(`speech ${status} ${code}: safe specific error, no retry, no false playback completion`, async ({ page }) => {
    let submitted = 0;
    await page.route('**/speak', route => { submitted++; return route.fulfill({ status, json: { error: code } }); });
    await mount(page);
    await page.evaluate(async () => { VoiceIn.start = () => false; Voice.on = true; await Voice.say('Synthetic reply'); });
    await expect(page.locator('#toast')).toContainText(message);
    expect(submitted).toBe(1);
    expect(await page.evaluate(() => VoiceOut.lastPlaybackOutcome)).toBeNull();
    expect(await page.evaluate(() => Voice.on)).toBe(false);
    if (status !== 502) await expect(page.locator('#mic-btn')).toBeDisabled();
  });
}

for (const outcome of ['ENDED', 'ERROR', 'CANCELLED', 'PLAY_REJECTED']) {
  test(`playback truth: ${outcome} is distinct from HTTP 200`, async ({ page }) => {
    await page.route('**/speak', route => route.fulfill({ contentType: 'audio/mpeg', body: 'synthetic-only' }));
    await mount(page);
    await page.evaluate(mode => {
      window.playbackEvents = [];
      VoiceBus.on('playback', event => playbackEvents.push(event));
      window.Audio = class {
        constructor() { window.testAudio = this; }
        play() { return mode === 'PLAY_REJECTED' ? Promise.reject(new Error('autoplay denied')) : Promise.resolve(); }
        pause() {}
      };
      window.playbackResult = VoiceOut.speak('Synthetic, no real audio').catch(error => error.code);
    }, outcome);
    await expect.poll(() => page.evaluate(() => !!window.testAudio)).toBe(true);
    if (outcome !== 'PLAY_REJECTED') {
      // Neither a successful HTTP response nor a resolved play() is a start.
      expect(await page.evaluate(() => VoiceOut.lastPlaybackOutcome)).toBeNull();
      expect(await page.evaluate(() => playbackEvents)).toEqual([]);
      await page.evaluate(() => { testAudio.onplaying(); testAudio.onplaying(); });
      expect(await page.evaluate(() => playbackEvents)).toEqual([{ outcome: 'PLAYBACK_STARTED' }]);
      expect(await page.evaluate(() => VoiceOut.lastPlaybackOutcome)).toBe('PLAYBACK_STARTED');
      await page.evaluate(mode => {
        const lateEnded = testAudio.onended;
        if (mode === 'ENDED') testAudio.onended();
        else if (mode === 'ERROR') testAudio.onerror();
        else { VoiceOut.stop(); lateEnded(); }
      }, outcome);
    }
    const result = await page.evaluate(async () => ({ result: await playbackResult, outcome: VoiceOut.lastPlaybackOutcome,
      events: playbackEvents, playing: VoiceOut.playing }));
    const expected = 'PLAYBACK_' + (outcome === 'PLAY_REJECTED' ? 'ERROR' : outcome);
    const events = outcome === 'PLAY_REJECTED' ? [] : [{ outcome: 'PLAYBACK_STARTED' }];
    events.push({ outcome: expected });
    expect(result).toEqual({ result: expected === 'PLAYBACK_ERROR' ? 'playback_error' : expected,
      outcome: expected, events, playing: false });
  });
}

for (const language of ['bg', 'en']) {
  for (const code of ['pilot_expired', 'pilot_disabled', 'forbidden']) {
    test(`${language}: ${code} preflight is distinct, terminal, and makes no voice request`, async ({ page }) => {
      let checks = 0, speech = 0;
      await page.route('**/api/live-voice/allowances', route => {
        checks++; return route.fulfill({ status: 403, json: { error: code, terminal: true } });
      });
      await page.route('**/speak', route => { speech++; return route.abort(); });
      await mount(page, language);
      const state = await page.evaluate(async () => {
        LIVE_VOICE_CONFIG.transport = 'relay'; let microphone = 0, socket = 0;
        Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true,
          value: async () => { microphone++; throw new Error('must not request microphone'); } });
        window.WebSocket = class { constructor() { socket++; } };
        await Voice.start(); await Voice.start();
        return { microphone, socket, blocked: Voice.blockedCode, active: Voice.on };
      });
      expect(state).toEqual({ microphone: 0, socket: 0, blocked: code, active: false });
      expect(checks).toBe(1); expect(speech).toBe(0);
      const expected = {
        bg: { pilot_expired: 'Тестовият достъп е приключил', pilot_disabled: 'Гласовият тест е спрян', forbidden: 'Нямаш достъп' },
        en: { pilot_expired: 'Pilot access has expired', pilot_disabled: 'voice pilot is disabled', forbidden: 'not available to this account' },
      };
      await expect(page.locator('#toast')).toContainText(expected[language][code]);
      await expect(page.locator('#mic-btn')).toBeDisabled();
      await expect(page.locator('#user-in')).toBeEnabled();
    });
  }
}

test('fresh expired pilot config never falls through into the legacy greeting', async ({ page }) => {
  await mount(page);
  const result = await page.evaluate(async () => {
    LIVE_VOICE_CONFIG.enabled = false; LIVE_VOICE_CONFIG.transport = 'disabled';
    LIVE_VOICE_CONFIG.pilot_error = 'pilot_expired';
    let greetings = 0; Voice.greet = () => { greetings++; };
    await Voice.start();
    return { greetings, on: Voice.on, blocked: Voice.blockedCode };
  });
  expect(result).toEqual({ greetings: 0, on: false, blocked: 'pilot_expired' });
});

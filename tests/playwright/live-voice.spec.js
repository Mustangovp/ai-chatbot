const { test, expect } = require('@playwright/test');

test.use({ baseURL: process.env.LIVE_VOICE_BASE_URL || 'http://127.0.0.1:5001' });

async function harness(page) {
  await page.goto('/app?lang=en');
  await page.addScriptTag({ url: '/static/live_voice.js' });
  await page.evaluate(() => {
    window.makeVoiceLab = (overrides = {}) => {
      const lab = { owner: 'synthetic-a', states: [], facts: [], turns: [], transports: [],
        tasks: new Map(), nextTask: 0, fallbacks: 0, cancelled: 0, stopped: 0 };
      lab.controller = new ApexLiveVoice.Controller({
        transportFactory: () => { const t = new ApexLiveVoice.MockTransport(); lab.transports.push(t); return t; },
        owner: () => lab.owner, language: () => 'en', onState: s => lab.states.push(s),
        onFact: f => lab.facts.push(f), onTranscript: async t => { lab.turns.push(t); },
        cancelAuthority: () => { lab.cancelled++; }, speak: async () => {},
        stopSpeaking: () => { lab.stopped++; }, fallback: () => { lab.fallbacks++; },
        schedule: (fn, delay) => { const id = ++lab.nextTask; lab.tasks.set(id, { fn, delay }); return id; },
        unschedule: id => lab.tasks.delete(id), ...overrides
      });
      lab.runTask = () => { const [id, task] = lab.tasks.entries().next().value; lab.tasks.delete(id); task.fn(); return task.delay; };
      return lab;
    };
  });
}

test('mock: final transcript delegates once; autonomous responses/tools/private errors never deliver', async ({ page }) => {
  await harness(page);
  const result = await page.evaluate(async () => {
    const lab = makeVoiceLab(); await lab.controller.start();
    const t = lab.transports[0];
    t.emit({ type: 'response.output_text.delta', delta: 'Unvalidated overhead press 3x10' });
    t.emit({ type: 'response.function_call_arguments.done', arguments: '{"change_plan":true}' });
    const turn = { type: 'conversation.item.input_audio_transcription.completed', item_id: 'item-one', transcript: 'Avoid overhead pressing' };
    t.emit(turn); t.emit(turn); await Promise.resolve(); await Promise.resolve();
    const result = { turns: lab.turns, facts: lab.facts, seen: lab.controller.seen.size };
    t.emit({ type: 'error', error: { message: 'private-provider-secret' } });
    result.fallbacks = lab.fallbacks; result.states = lab.states; lab.controller.stop(); return result;
  });
  expect(result.turns).toEqual(['Avoid overhead pressing']);
  expect(result.facts).toContain('keystroke');
  expect(result.seen).toBe(1); expect(result.fallbacks).toBe(1);
  expect(JSON.stringify(result)).not.toContain('private-provider-secret');
});

test('mock: interruption cancels audio/backend and stale playback cannot finish a later turn', async ({ page }) => {
  await harness(page);
  const result = await page.evaluate(async () => {
    let finish;
    const lab = makeVoiceLab({ speak: () => new Promise(resolve => { finish = resolve; }) });
    await lab.controller.start(); const pending = lab.controller.say('Validated explanation');
    lab.transports[0].emit({ type: 'input_audio_buffer.speech_started' });
    lab.transports[0].emit({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'two', transcript: 'Correct that' });
    const before = lab.controller.state;
    finish(); await pending; await Promise.resolve();
    const result = { before, turns: lab.turns, states: lab.states, cancelled: lab.cancelled, tasks: lab.tasks.size };
    lab.controller.stop(); return result;
  });
  expect(result.before).toBe('THINKING');
  expect(result.turns).toEqual(['Correct that']);
  expect(result.states).toContain('INTERRUPTED'); expect(result.cancelled).toBeGreaterThan(0);
  expect(result.tasks).toBe(0);
});

test('mock: reconnect is bounded, no replay, and old connection callbacks are discarded', async ({ page }) => {
  await harness(page);
  const result = await page.evaluate(async () => {
    const lab = makeVoiceLab(); await lab.controller.start();
    const old = lab.transports[0].onEvent; const delays = [];
    for (let i = 0; i < 2; i++) {
      lab.transports[i].disconnect(); delays.push(lab.runTask());
      await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    }
    old({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'stale', transcript: 'must not send' });
    lab.transports[2].disconnect();
    return { delays, count: lab.transports.length, closed: lab.transports.every(t => t.closed),
      turns: lab.turns, fallbacks: lab.fallbacks, tasks: lab.tasks.size, active: lab.controller.active };
  });
  expect(result).toEqual({ delays: [250, 1000], count: 3, closed: true, turns: [], fallbacks: 1, tasks: 0, active: false });
});

test('mock: blocked connection expires deterministically and falls back without replay', async ({ page }) => {
  await harness(page);
  const result = await page.evaluate(async () => {
    const transport = { connect: () => new Promise(() => {}), close() { this.closed = true; } };
    const lab = makeVoiceLab({ transportFactory: () => transport });
    const pending = lab.controller.start(); const deadline = lab.runTask(); await pending;
    return { deadline, active: lab.controller.active, closed: transport.closed, fallbacks: lab.fallbacks, tasks: lab.tasks.size };
  });
  expect(result).toEqual({ deadline: 20000, active: false, closed: true, fallbacks: 1, tasks: 0 });
});

test('mock: server-ended session releases resources without reconnect or fallback', async ({ page }) => {
  await harness(page);
  const result = await page.evaluate(async () => {
    let ended = 0;
    const lab = makeVoiceLab({ onEnded: () => { ended++; } });
    await lab.controller.start();
    lab.transports[0].emit({ type: 'session.ended' });
    return { ended, active: lab.controller.active, closed: lab.transports.every(t => t.closed),
      tasks: lab.tasks.size, connections: lab.transports.length, fallbacks: lab.fallbacks, state: lab.controller.state };
  });
  expect(result).toEqual({ ended: 1, active: false, closed: true, tasks: 0,
    connections: 1, fallbacks: 0, state: 'IDLE' });
});

test('mock: account switch stops the connection and ignores in-flight transcript', async ({ page }) => {
  await harness(page);
  const result = await page.evaluate(async () => {
    const lab = makeVoiceLab(); await lab.controller.start(); const old = lab.transports[0].onEvent;
    lab.owner = 'synthetic-b';
    old({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'late', transcript: 'private old account turn' });
    return { active: lab.controller.active, closed: lab.transports[0].closed, turns: lab.turns, state: lab.controller.state };
  });
  expect(result).toEqual({ active: false, closed: true, turns: [], state: 'IDLE' });
});

test('mock: Stop during connection cancels it and cannot revive an old session', async ({ page }) => {
  await harness(page);
  const result = await page.evaluate(async () => {
    let release;
    const t = { connect: () => new Promise(resolve => { release = resolve; }), close() { this.closed = true; } };
    const lab = makeVoiceLab({ transportFactory: () => t });
    const pending = lab.controller.start(); lab.controller.stop(); release(); await pending;
    return { active: lab.controller.active, closed: t.closed, state: lab.controller.state, tasks: lab.tasks.size };
  });
  expect(result).toEqual({ active: false, closed: true, state: 'IDLE', tasks: 0 });
});

test('mock: backend rejection does not replay a turn or expose private errors', async ({ page }) => {
  await harness(page);
  const result = await page.evaluate(async () => {
    let sent = 0;
    const lab = makeVoiceLab({ onTranscript: async () => { sent++; throw new Error('private backend detail'); } });
    await lab.controller.start();
    lab.transports[0].emit({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'failed', transcript: 'One turn' });
    for (let i = 0; i < 6; i++) await Promise.resolve();
    const result = { sent, state: lab.controller.state, states: lab.states, fallbacks: lab.fallbacks };
    lab.controller.stop(); return result;
  });
  expect(result.sent).toBe(1); expect(result.state).toBe('ERROR');
  expect(JSON.stringify(result)).not.toContain('private backend detail');
  expect(result.fallbacks).toBe(0);
});

test('mock relay: same-origin PCM only, no provider peer, microphone and context cleanup', async ({ page }) => {
  await harness(page);
  const result = await page.evaluate(async () => {
    let stopped = 0, closed = 0, contextClosed = 0; const calls = [];
    const track = { stop: () => { stopped++; } };
    class Socket {
      constructor(url) { calls.push(url); this.readyState = 1; this.bufferedAmount = 0;
        queueMicrotask(() => this.onmessage({ data: '{"type":"session.ready","seconds":120}' })); }
      send(frame) { calls.push(frame.byteLength); }
      close() { closed++; }
    }
    class Context {
      constructor() { this.audioWorklet = { addModule: async url => { calls.push(url); } }; }
      createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
      createGain() { return { gain: {}, connect() {}, disconnect() {} }; }
      async resume() {}
      async close() { contextClosed++; }
    }
    class Worklet { constructor() { this.port = {}; } connect() {} disconnect() {} }
    const t = new ApexLiveVoice.RelayTransport({ Socket, Context, Worklet,
      media: { getUserMedia: async () => ({ getTracks: () => [track], getAudioTracks: () => [track] }) },
    });
    const abort = new AbortController();
    await t.connect({ language: 'bg', signal: abort.signal, onEvent() {}, onDisconnect() {} });
    t.capture.port.onmessage({ data: new ArrayBuffer(4800) });
    t.mute(true); const muted = track.enabled === false; abort.abort();
    return { calls, stopped, closed, contextClosed, muted, stream: t.stream };
  });
  expect(result.calls).toEqual(['ws://127.0.0.1:5001/api/live-voice/media?lang=bg', '/static/live_voice_capture.js', 4800]);
  expect(result).toMatchObject({ stopped: 1, closed: 1, contextClosed: 1, muted: true, stream: null });
});

test('mock relay: late microphone permission after Stop releases tracks', async ({ page }) => {
  await harness(page);
  const result = await page.evaluate(async () => {
    let grant, stopped = 0;
    const t = new ApexLiveVoice.RelayTransport({ media: { getUserMedia: () => new Promise(resolve => { grant = resolve; }) }, Socket: class {}, Context: class {}, Worklet: class {} });
    const abort = new AbortController();
    const pending = t.connect({ language: 'en', signal: abort.signal }).catch(() => 'cancelled');
    abort.abort(); grant({ getTracks: () => [{ stop() { stopped++; } }] });
    return { outcome: await pending, stopped, closed: t.closed };
  });
  expect(result).toEqual({ outcome: 'cancelled', stopped: 1, closed: true });
});

test('mock relay: abrupt worker socket loss cannot reconnect or submit queued audio/turns', async ({ page }) => {
  await harness(page);
  const result = await page.evaluate(async () => {
    let sockets = 0, sent = 0, tracksStopped = 0, contextsClosed = 0, ended = 0, socket;
    class Socket {
      constructor() {
        socket = this; sockets++; this.readyState = 1; this.bufferedAmount = 0;
        queueMicrotask(() => this.onmessage({ data: '{"type":"session.ready","seconds":15}' }));
      }
      send() { sent++; }
      close() { this.readyState = 3; }
    }
    class Context {
      constructor() { this.audioWorklet = { addModule: async () => {} }; }
      createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
      createGain() { return { gain: {}, connect() {}, disconnect() {} }; }
      async resume() {}
      async close() { contextsClosed++; }
    }
    class Worklet { constructor() { this.port = {}; } connect() {} disconnect() {} }
    const lab = makeVoiceLab({
      transportFactory: () => new ApexLiveVoice.RelayTransport({ Socket, Context, Worklet,
        media: { getUserMedia: async () => ({ getTracks: () => [{ stop() { tracksStopped++; } }] }) } }),
      onEnded: () => { ended++; }
    });
    await lab.controller.start();
    const lateAudio = lab.controller.transport.capture.port.onmessage;
    const lateEvent = socket.onmessage;
    socket.onclose({ code: 1006 });
    lateAudio({ data: new ArrayBuffer(4800) });
    lateEvent({ data: JSON.stringify({ type: 'conversation.item.input_audio_transcription.completed',
      item_id: 'queued-before-worker-loss', transcript: 'Do not submit this turn' }) });
    await Promise.resolve();
    return { sockets, sent, tracksStopped, contextsClosed, ended, active: lab.controller.active,
      tasks: lab.tasks.size, turns: lab.turns, fallbacks: lab.fallbacks };
  });
  expect(result).toEqual({ sockets: 1, sent: 0, tracksStopped: 1, contextsClosed: 1,
    ended: 1, active: false, tasks: 0, turns: [], fallbacks: 0 });
});

test('mock relay: denied microphone is isolated and no socket is opened', async ({ page }) => {
  await harness(page);
  const result = await page.evaluate(async () => {
    let sent = 0;
    const t = new ApexLiveVoice.RelayTransport({ media: { getUserMedia: async () => { throw new Error('denied'); } },
      Socket: class { constructor() { sent++; } }, Context: class {}, Worklet: class {} });
    const lab = makeVoiceLab({ transportFactory: () => t }); await lab.controller.start();
    return { sent, closed: t.closed, active: lab.controller.active, fallbacks: lab.fallbacks };
  });
  expect(result).toEqual({ sent: 0, closed: true, active: false, fallbacks: 1 });
});

for (const language of ['bg', 'en']) {
  test(`app mock integration: ${language} shared chat/speech boundary and owner cleanup`, async ({ page }) => {
    let requests = [];
    await page.route('**/chat', async route => {
      requests.push(route.request().postDataJSON());
      await route.fulfill({ contentType: 'text/event-stream', body: 'data: ' + JSON.stringify({ t: language === 'bg' ? 'Запазвам ограничението ти.' : 'Your restriction remains in place.' }) + '\n\ndata: ' + JSON.stringify({ speech_text: language === 'bg' ? 'Без преси над глава.' : 'No overhead pressing.' }) + '\n\ndata: {"done":true}\n\n' });
    });
    await page.goto('/app?lang=' + language);
    // The real app must have local-only config enabled by the preview server.
    expect(await page.evaluate(() => LIVE_VOICE_CONFIG.enabled)).toBe(true);
    await page.evaluate(async language => {
      lang = language; SESSION.authenticated = true;
      activateDataOwner('account', 'local-mock-owner');
      ownedStorageSet('apexProfile', JSON.stringify({ goal: 'general', age: 30, weight: 75, height: 178,
        gender: 'male', level: 'intermediate', equip: 'home', language }));
      enterConsult(''); document.getElementById('profile-modal').classList.remove('on');
      window.mockSpoken = [];
      VoiceOut.speak = async text => { mockSpoken.push(text); };
      await Voice.start();
      liveVoiceController.transport.emit({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'utterance-1',
        transcript: language === 'bg' ? 'По-трудна тренировка без преси над глава.' : 'Harder workout, avoid overhead pressing.' });
    }, language);
    await expect.poll(() => requests.length).toBe(1);
    await expect.poll(() => page.evaluate(() => ChatLifecycle.current && ChatLifecycle.current.state)).toBe('COMPLETED');
    expect(requests[0]).toMatchObject({ lang: language, voice: true });
    expect(requests[0].message).toContain(language === 'bg' ? 'без преси над глава' : 'avoid overhead pressing');
    expect(await page.evaluate(() => mockSpoken)).toEqual([language === 'bg' ? 'Без преси над глава.' : 'No overhead pressing.']);
    await expect(page.locator('#mic-btn')).toHaveAttribute('aria-label', language === 'bg' ? 'Слушам те…' : 'Listening…');
    const cleaned = await page.evaluate(() => {
      const transport = liveVoiceController.transport;
      activateDataOwner('account', 'different-mock-owner');
      return { closed: transport.closed, active: liveVoiceController.active, on: Voice.on, feed: document.getElementById('feed').textContent };
    });
    expect(cleaned).toEqual({ closed: true, active: false, on: false, feed: '' });
  });
}

test('app: anonymous user cannot start account realtime; existing voice remains available', async ({ page }) => {
  await page.goto('/app');
  const result = await page.evaluate(() => {
    SESSION.authenticated = false; const live = getLiveVoice();
    return { absent: live === null, originalInput: typeof VoiceIn.start, originalOutput: typeof VoiceOut.speak };
  });
  expect(result).toEqual({ absent: true, originalInput: 'function', originalOutput: 'function' });
});

test('app: transport failure safely falls back to existing input without replay', async ({ page }) => {
  await page.goto('/app?lang=en');
  const result = await page.evaluate(async () => {
    await loadSession(); let nativeStarts = 0, greetings = 0;
    VoiceIn.start = () => { nativeStarts++; return true; };
    Object.defineProperty(VoiceIn, 'supported', { get: () => true });
    Voice.greet = () => { greetings++; };
    await Voice.start();
    liveVoiceController.transport.emit({ type: 'error', error: { message: 'private failure' } });
    const result = { nativeStarts, greetings, active: liveVoiceController.active, state: Voice.state };
    Voice.stop(); return result;
  });
  expect(result).toEqual({ nativeStarts: 1, greetings: 0, active: false, state: 'LISTENING' });
});

test('app: pagehide stops the mock microphone session and queued reconnect', async ({ page }) => {
  await page.goto('/app?lang=en');
  const result = await page.evaluate(async () => {
    await loadSession(); await Voice.start(); const transport = liveVoiceController.transport;
    transport.disconnect(); window.dispatchEvent(new Event('pagehide'));
    return { closed: transport.closed, active: liveVoiceController.active, on: Voice.on,
      retry: liveVoiceController.retryTimer, state: Voice.state };
  });
  expect(result).toEqual({ closed: true, active: false, on: false, retry: null, state: 'IDLE' });
});

for (const language of ['bg', 'en']) {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }, { width: 360, height: 800 }]) {
    test(`mock review: ${language} ${viewport.width} Core and voice remain readable`, async ({ page }, testInfo) => {
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      await page.setViewportSize(viewport); await page.goto('/app?lang=' + language);
      await page.evaluate(async () => { await loadSession(); enterConsult(''); document.getElementById('profile-modal').classList.remove('on'); await Voice.start(); });
      await expect(page.locator('#mic-btn')).toHaveAttribute('data-state', 'listening');
      await expect(page.locator('#mic-btn')).toHaveAttribute('aria-pressed', 'true');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await expect.poll(() => page.evaluate(() => {
        const canvas = document.getElementById('core');
        return canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data.some(value => value > 0);
      })).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`mock-${language}-${viewport.width}.png`) });
      await page.evaluate(() => Voice.stop());
      expect(errors).toEqual([]);
    });
  }
}

test('mock preview: local lab uses real app bridge, no eval or provider request', async ({ page }) => {
  let externalRequests = 0;
  page.on('request', request => { if (/api\.openai\.com|google-analytics\.com/.test(request.url())) externalRequests++; });
  await page.goto('/live-voice-preview');
  await expect(page.locator('#status')).toContainText('MOCK: IDLE');
  await page.getByRole('button', { name: 'Connect', exact: true }).click();
  await expect(page.locator('#status')).toContainText('MOCK: LISTENING');
  await page.getByRole('button', { name: 'Send turn', exact: true }).click();
  const app = page.frameLocator('#app');
  await expect(app.locator('#feed')).toContainText('This is a mock reply.');
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(page.locator('#status')).toContainText('MOCK: IDLE');
  expect(externalRequests).toBe(0);
});

for (const [label, evidence] of [
  ['unexpected script', { transcript: 'Çuwaşlım?' }],
  ['unreliable detected language', { transcript: 'A short unclear utterance', languages: [] }],
  ['unsupported detected language', { transcript: 'A short unclear utterance', languages: [{ code: 'tr' }] }],
  ['reported low confidence', { transcript: 'Дай ми тренировка', logprobs: [{ logprob: -4 }] }],
]) {
  test(`BG: ${label} requests clarification without treating it as user intent`, async ({ page }) => {
    await harness(page);
    const result = await page.evaluate(async evidence => {
      let settled; const complete = new Promise(resolve => { settled = resolve; });
      const uncertain = [], lab = makeVoiceLab({ language: () => 'bg', onUncertain: async issue => uncertain.push(issue),
        onState: state => { if (state === 'LISTENING' && uncertain.length) settled(); } });
      await lab.controller.start();
      lab.transports[0].emit({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'uncertain-1', ...evidence });
      await complete;
      const result = { turns: lab.turns, uncertain: uncertain.length, state: lab.controller.state };
      lab.controller.stop(); return result;
    }, evidence);
    expect(result).toEqual({ turns: [], uncertain: 1, state: 'LISTENING' });
  });
}

test('BG: English words do not change the selected response language', async ({ page }) => {
  await harness(page);
  const result = await page.evaluate(async () => {
    const lab = makeVoiceLab({ language: () => 'bg' }); await lab.controller.start();
    lab.transports[0].emit({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'mixed-1',
      transcript: 'Why are you speaking English?', languages: [{ code: 'en' }] });
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    const result = { turns: lab.turns, language: lab.controller.connectedLanguage };
    lab.controller.stop(); return result;
  });
  expect(result).toEqual({ turns: ['Why are you speaking English?'], language: 'bg' });
});

test('BG: uncertain input gets Bulgarian clarification, not a chat request', async ({ page }) => {
  const requests = [];
  page.on('request', request => { if (new URL(request.url()).pathname === '/chat') requests.push(request); });
  await page.goto('/app?lang=bg');
  await page.evaluate(async () => {
    await loadSession(); enterConsult(''); document.getElementById('profile-modal').classList.remove('on');
    window.clarifications = []; VoiceOut.speak = async (text, language) => clarifications.push({ text, language });
    await Voice.start();
    liveVoiceController.transport.emit({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'bad-1', transcript: 'Çuwaşlım?' });
  });
  await expect(page.locator('#feed')).toContainText('Не те разбрах ясно');
  await expect(page.locator('#feed')).not.toContainText('Çuwaşlım');
  expect(requests).toHaveLength(0);
  expect(await page.evaluate(() => clarifications)).toEqual([{ text: 'Не те разбрах ясно. Моля, повтори на български или напиши съобщението.', language: 'bg' }]);
  await page.evaluate(() => Voice.stop());
});

test('BG: explicit voice preference is acknowledged before rendering and speech, survives English complaint and refresh', async ({ page }) => {
  const requests = [];
  await page.route('**/chat', async route => {
    requests.push(route.request().postDataJSON());
    const text = 'Ще отговарям на български. Смяната на езика не променя тренировката.';
    await route.fulfill({ contentType: 'text/event-stream', headers: { 'Content-Language': 'bg-BG' },
      body: 'data: ' + JSON.stringify({ t: text }) + '\n\ndata: ' + JSON.stringify({ speech_text: text }) + '\n\ndata: {"done":true}\n\n' });
  });
  await page.goto('/app?lang=en');
  await page.evaluate(async () => {
    await loadSession(); enterConsult(''); document.getElementById('profile-modal').classList.remove('on');
    window.languageSpeech = []; VoiceOut.speak = async (text, language) => languageSpeech.push({ text, language });
    await Voice.start();
    liveVoiceController.transport.emit({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'language-1', transcript: 'Аз говоря на български.' });
  });
  await expect.poll(() => page.evaluate(() => ChatLifecycle.current && ChatLifecycle.current.state)).toBe('COMPLETED');
  await expect.poll(() => page.evaluate(() => liveVoiceController.connectedLanguage)).toBe('bg');
  expect(requests[0].lang).toBe('en');
  await page.evaluate(() => liveVoiceController.transport.emit({ type: 'conversation.item.input_audio_transcription.completed',
    item_id: 'language-2', transcript: 'Why are you speaking English?', languages: [{ code: 'en' }] }));
  await expect.poll(() => requests.length).toBe(2);
  await expect.poll(() => page.evaluate(() => ChatLifecycle.current.state)).toBe('COMPLETED');
  expect(requests[1].lang).toBe('bg');
  expect(await page.evaluate(() => languageSpeech.every(item => item.language === 'bg' && /български/.test(item.text)))).toBe(true);
  await expect(page.locator('html')).toHaveAttribute('lang', 'bg');
  await page.goto('/app');
  await page.evaluate(() => loadSession());
  await expect(page.locator('html')).toHaveAttribute('lang', 'bg');
});

for (const width of [390, 360]) {
  test(`BG: canonical workout and DEMO truth at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 }); await page.goto('/app?lang=bg');
    await page.evaluate(async () => {
      await loadSession(); enterConsult(''); document.getElementById('profile-modal').classList.remove('on');
      const ids = ['dumbbell.front_squat', 'bodyweight.push_up', 'dumbbell.bent_over_row', 'dumbbell.romanian_deadlift', 'bodyweight.hollow_hold'];
      const exercises = ids.map((id, index) => ({ prescription_id: 'language-p-' + index, exercise_id: id, exercise_version: '1.0.0',
        prescribed_sets: 2, rep_min: index === 4 ? null : 8, rep_max: index === 4 ? null : 12,
        prescription_type: index === 4 ? 'duration' : 'repetitions', duration_min_seconds: index === 4 ? 20 : null,
        duration_max_seconds: index === 4 ? 40 : null, rest_seconds: 60, difficulty: 'intermediate' }));
      const session = { session_id: 'bg-language-session', session_index: 1, exercises };
      pendingTrainingCompletion = { plan_id: 'bg-language-plan', plan_version: 'training-plan-blueprint-v3', sessions: [session] };
      pendingCompletionSessions = [session]; window.beforeLanguageContract = JSON.stringify(pendingTrainingCompletion);
      appendCoach().innerHTML = renderMarkdown(['| Exercise | Sets | Reps | Rest | Note |', '| --- | --- | --- | --- | --- |',
        ...exercises.map(item => '| ' + ApexExerciseInstructions.display(ApexExerciseInstructions.findByExerciseId(item.exercise_id), 'en') +
          ' | 2 | ' + (item.prescription_type === 'duration' ? '20-40 sec' : '8-12') + ' | 60 | RPE 7, RIR 3; tempo 2-0-2-0 |')].join('\n'));
    });
    const cards = page.locator('.workout-exercise-card');
    await expect(cards).toHaveCount(5);
    expect((await cards.locator('.ex-name').allTextContents()).every(name => /[А-Яа-я]/.test(name))).toBe(true);
    await expect(cards.first().locator('.workout-card-stats')).toContainText('Серии');
    await expect(cards.first().locator('.workout-card-stats')).toContainText('Почивка');
    await expect(cards.last().locator('.workout-card-stats')).toContainText('Продължителност');
    await expect(cards.first().locator('.workout-execution-details')).toContainText('Начална позиция');
    await expect(cards.first().locator('.workout-execution-details')).not.toContainText('Starting position');
    await expect(page.locator('#local-demo-notice')).toBeVisible();
    await expect(page.locator('#local-demo-notice')).toContainText('DEMO');
    await expect(page.locator('#local-demo-notice')).toContainText('Синтетичен');
    await expect(page.locator('#apex-position-readout')).toBeHidden();
    await expect(page.locator('#mic-btn')).toHaveAttribute('title', 'Говори с APEX');
    await expect(page.locator('.send-btn')).toHaveAttribute('aria-label', 'Изпрати');
    await page.evaluate(() => { selectAppLanguage('en'); selectAppLanguage('bg'); });
    expect(await page.evaluate(() => JSON.stringify(pendingTrainingCompletion) === beforeLanguageContract)).toBe(true);
    await expect(cards.first().locator('.ex-name')).toContainText('клек');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

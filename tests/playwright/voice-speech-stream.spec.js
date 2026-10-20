const { test, expect } = require('@playwright/test');

test.use({ baseURL: process.env.LIVE_VOICE_BASE_URL || 'http://127.0.0.1:5001' });

async function mount(page) {
  await page.goto('/app?lang=bg');
  await page.evaluate(async () => {
    await loadSession(); enterConsult(''); document.getElementById('profile-modal').classList.remove('on');
  });
}

for (const mode of ['ENDED', 'TRUNCATED', 'PROVIDER_ERROR', 'CANCELLED', 'APPEND_ERROR', 'PLAY_REJECTED']) {
  test(`incremental speech: ${mode}, one request and truthful completion`, async ({ page }) => {
    await mount(page);
    await page.evaluate(mode => {
      window.lab = { posts: 0, appends: 0, revoked: 0, events: [], cancelled: 0 };
      VoiceBus.on('playback', event => lab.events.push(event));
      class Source extends EventTarget {
        static isTypeSupported(mime) { return mime === 'audio/mpeg'; }
        constructor() {
          super(); this.readyState = 'closed';
          queueMicrotask(() => { this.readyState = 'open'; this.dispatchEvent(new Event('sourceopen')); });
        }
        addSourceBuffer() {
          const buffer = new EventTarget();
          buffer.appendBuffer = () => {
            lab.appends++;
            queueMicrotask(() => {
              buffer.dispatchEvent(new Event(mode === 'APPEND_ERROR' ? 'error' : 'updateend'));
              if (mode !== 'APPEND_ERROR' && lab.audio.onplaying) lab.audio.onplaying();
            });
          };
          return buffer;
        }
        endOfStream() { queueMicrotask(() => lab.audio.onended && lab.audio.onended()); }
      }
      window.MediaSource = Source;
      URL.createObjectURL = () => 'blob:synthetic-stream';
      URL.revokeObjectURL = () => { lab.revoked++; };
      window.Audio = class {
        constructor() { lab.audio = this; }
        play() { return mode === 'PLAY_REJECTED' ? Promise.reject(new Error('blocked')) : Promise.resolve(); }
        pause() {} removeAttribute() {} load() {}
      };
      const originalFetch = window.fetch;
      window.fetch = async (url, options) => {
        if (url !== '/speak') return originalFetch(url, options);
        lab.posts++; lab.accept = options.headers.Accept;
        return new Response(new ReadableStream({
          start(controller) {
            lab.controller = controller;
            controller.enqueue(new TextEncoder().encode('{"audio":"Zmlyc3Q="}\n'));
          },
          cancel() { lab.cancelled++; },
        }), { headers: { 'Content-Type': 'application/x-ndjson' } });
      };
      lab.result = VoiceOut.speak('Синтетичен локален отговор', 'bg').catch(error => error.code);
    }, mode);
    if (mode !== 'PLAY_REJECTED') {
      await expect.poll(() => page.evaluate(() => lab.appends)).toBe(1);
    }
    if (!['APPEND_ERROR', 'PLAY_REJECTED'].includes(mode)) {
      // The source is deliberately still open: first playback precedes the
      // provider's final chunk/acknowledgement, without a sleep/timing guess.
      await expect.poll(() => page.evaluate(() => VoiceOut.lastPlaybackOutcome)).toBe('PLAYBACK_STARTED');
      expect(await page.evaluate(() => VoiceOut._attempt.stream.complete)).toBe(false);
      await page.evaluate(mode => {
        if (mode === 'CANCELLED') { VoiceOut.stop(); return; }
        if (mode === 'ENDED') lab.controller.enqueue(new TextEncoder().encode(
          '{"audio":"c2Vjb25k"}\n{"done":true,"timings":{"tts_headers":10,"tts_first_audio":20,"tts_complete":80}}\n'));
        if (mode === 'PROVIDER_ERROR') lab.controller.enqueue(new TextEncoder().encode('{"error":"tts_unavailable"}\n'));
        lab.controller.close();
      }, mode);
    }
    const result = await page.evaluate(async () => ({ result: await lab.result, posts: lab.posts,
      accept: lab.accept, events: lab.events, playing: VoiceOut.playing, revoked: lab.revoked,
      timings: ApexLiveVoice.timing.snapshot() }));
    const expected = mode === 'ENDED' ? 'PLAYBACK_ENDED' : mode === 'CANCELLED' ? 'PLAYBACK_CANCELLED' :
      mode === 'PROVIDER_ERROR' ? 'tts_unavailable' : 'playback_error';
    expect(result.result).toBe(expected);
    expect(result.posts).toBe(1); expect(result.accept).toBe('application/x-ndjson');
    expect(result.playing).toBe(false); expect(result.revoked).toBe(1);
    expect(result.events.at(-1)).toEqual({ outcome: mode === 'ENDED' ? 'PLAYBACK_ENDED' :
      mode === 'CANCELLED' ? 'PLAYBACK_CANCELLED' : 'PLAYBACK_ERROR' });
    if (mode === 'ENDED') {
      expect(result.events).toEqual([{ outcome: 'PLAYBACK_STARTED' }, { outcome: 'PLAYBACK_ENDED' }]);
      expect(result.timings).toEqual(expect.arrayContaining([
        { stage: 'tts_headers', milliseconds: 10 }, { stage: 'tts_first_audio', milliseconds: 20 },
        { stage: 'tts_complete', milliseconds: 80 },
      ]));
    } else expect(result.events).not.toContainEqual({ outcome: 'PLAYBACK_ENDED' });
    expect(result.timings.every(item => Object.keys(item).sort().join() === 'milliseconds,stage')).toBe(true);
  });
}

test('timings are content-free, bounded and measure transcription after speech stop', async ({ page }) => {
  await mount(page);
  const result = await page.evaluate(async () => {
    let now = 100, transport, turns = 0;
    const controller = new ApexLiveVoice.Controller({
      transportFactory: () => transport = new ApexLiveVoice.MockTransport(),
      owner: () => 'synthetic', language: () => 'bg', onState() {}, onFact() {},
      onTranscript: async () => { turns++; }, cancelAuthority() {}, speak() {}, stopSpeaking() {}, fallback() {},
      clock: () => now,
    });
    await controller.start();
    transport.emit({ type: 'input_audio_buffer.speech_stopped' }); now = 350;
    transport.emit({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'private-id', transcript: 'Здравей' });
    await Promise.resolve();
    const first = ApexLiveVoice.timing.snapshot();
    controller.stop();
    ApexLiveVoice.timing.record('private-prompt', 10);
    ApexLiveVoice.timing.record('tts_complete', Infinity);
    for (let index = 0; index < 40; index++) ApexLiveVoice.timing.record('tts_complete', index);
    return { first, recent: ApexLiveVoice.timing.snapshot(), turns };
  });
  expect(result.first).toEqual([{ stage: 'transcription', milliseconds: 250 }]);
  expect(result.turns).toBe(1); expect(result.recent).toHaveLength(32);
  expect(result.recent[0]).toEqual({ stage: 'tts_complete', milliseconds: 8 });
});

test('validated voice response is timed only after terminal chat completion', async ({ page }) => {
  await mount(page);
  const result = await page.evaluate(async () => {
    const originalFetch = window.fetch;
    window.fetch = async (url, options) => {
      if (url !== '/chat') return originalFetch(url, options);
      return new Response(new ReadableStream({ start(controller) { window.chatStream = controller; } }),
        { headers: { 'Content-Type': 'text/event-stream' } });
    };
    document.getElementById('user-in').value = 'Здравей';
    window.chatFinished = send({ voice: true });
    return ApexLiveVoice.timing.snapshot();
  });
  expect(result).toEqual([]);
  await page.evaluate(() => chatStream.enqueue(new TextEncoder().encode('data: {"t":"Синтетичен отговор"}\n\n')));
  expect(await page.evaluate(() => ApexLiveVoice.timing.snapshot())).toEqual([]);
  await page.evaluate(async () => {
    chatStream.enqueue(new TextEncoder().encode('data: {"done":true}\n\n')); chatStream.close(); await chatFinished;
  });
  const timings = await page.evaluate(() => ApexLiveVoice.timing.snapshot());
  expect(timings).toEqual([{ stage: 'coach_response', milliseconds: expect.any(Number) }]);
});

test('unsupported incremental decoder keeps the original single-request playback path', async ({ page }) => {
  await page.route('**/speak', route => route.fulfill({ contentType: 'audio/mpeg', body: 'synthetic-only' }));
  await mount(page);
  const request = page.waitForRequest('**/speak');
  await page.evaluate(() => {
    window.MediaSource = undefined;
    window.Audio = class { constructor() { window.audio = this; } play() { return Promise.resolve(); } pause() {} };
    window.result = VoiceOut.speak('Synthetic').catch(error => error.code);
  });
  expect((await request).headers().accept).toBe('audio/mpeg');
  await expect.poll(() => page.evaluate(() => !!window.audio)).toBe(true);
  await page.evaluate(() => { audio.onplaying(); audio.onended(); });
  expect(await page.evaluate(() => result)).toBe('PLAYBACK_ENDED');
});

test('native Chromium decodes silent MP3 before synthesis ends; muted output is not an audible-speech claim', async ({ page }) => {
  await mount(page);
  await page.evaluate(() => {
    const OriginalAudio = window.Audio;
    window.Audio = function (...args) { const audio = new OriginalAudio(...args); audio.muted = true; return audio; };
    const originalFetch = window.fetch;
    window.nativeLab = { posts: 0, events: [] };
    VoiceBus.on('playback', event => nativeLab.events.push(event));
    // Valid silent MPEG-1 Layer III frames: no recorded/generated human audio,
    // external fixtures, encoder dependency, credentials or provider call.
    const bytes = new Uint8Array(417 * 40);
    for (let frame = 0; frame < 40; frame++) bytes.set([255, 251, 144, 100], frame * 417);
    nativeLab.frame = JSON.stringify({ audio: btoa(String.fromCharCode(...bytes)) }) + '\n';
    window.fetch = async (url, options) => {
      if (url !== '/speak') return originalFetch(url, options);
      nativeLab.posts++;
      nativeLab.language = JSON.parse(options.body).lang;
      return new Response(new ReadableStream({ start(controller) {
        nativeLab.controller = controller;
        controller.enqueue(new TextEncoder().encode(nativeLab.frame));
      } }), { headers: { 'Content-Type': 'application/x-ndjson' } });
    };
    nativeLab.result = VoiceOut.speak('Локален тест без платена заявка', 'bg').catch(error => error.code);
  });
  await expect.poll(() => page.evaluate(() => VoiceOut.lastPlaybackOutcome)).toBe('PLAYBACK_STARTED');
  expect(await page.evaluate(() => VoiceOut._attempt.stream.complete)).toBe(false);
  await page.evaluate(() => {
    nativeLab.controller.enqueue(new TextEncoder().encode(nativeLab.frame +
      '{"done":true,"timings":{"tts_headers":1,"tts_first_audio":2,"tts_complete":3}}\n'));
    nativeLab.controller.close();
  });
  expect(await page.evaluate(() => nativeLab.result)).toBe('PLAYBACK_ENDED');
  expect(await page.evaluate(() => ({ posts: nativeLab.posts, language: nativeLab.language, events: nativeLab.events })))
    .toEqual({ posts: 1, language: 'bg', events: [{ outcome: 'PLAYBACK_STARTED' }, { outcome: 'PLAYBACK_ENDED' }] });
});

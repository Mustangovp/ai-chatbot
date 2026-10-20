/* Local prototype: Realtime is input transport, never coaching authority.
 * No keys, ephemeral credentials, profile or history are sent by this module.
 * MOCK_PASS is not evidence of microphone quality, latency or model access. */
(function (root) {
  'use strict';

  const terminalErrors = new Set(['tts_quota_exhausted', 'media_quota_exhausted',
    'pilot_limit_reached', 'pilot_expired', 'pilot_disabled', 'forbidden', 'pilot_unavailable']);
  const messages = {
    tts_quota_exhausted: ['Лимитът за гласови отговори в този тест е изчерпан. Продължи с текст.', 'This test has no spoken replies remaining. Continue in text.'],
    media_quota_exhausted: ['Времето за микрофон в този тест е изчерпано. Продължи с текст.', 'This test has no microphone time remaining. Continue in text.'],
    pilot_limit_reached: ['Лимитът на гласовия тест е достигнат. Продължи с текст.', 'The voice test limit has been reached. Continue in text.'],
    pilot_expired: ['Тестовият достъп е приключил. Продължи с текст.', 'Pilot access has expired. Continue in text.'],
    pilot_disabled: ['Гласовият тест е спрян. Продължи с текст.', 'The voice pilot is disabled. Continue in text.'],
    forbidden: ['Нямаш достъп до този гласов тест. Продължи с текст.', 'This voice test is not available to this account. Continue in text.'],
    pilot_unavailable: ['Гласовият тест е спрян или достъпът не може да бъде проверен. Продължи с текст.', 'The voice test is stopped or access cannot be verified. Continue in text.'],
    tts_busy: ['Предишна заявка за звук още не е приключила. Продължи с текст.', 'A previous speech request has not finished. Continue in text.'],
    media_session_active: ['Вече има резервирана гласова сесия. Не е стартирана нова.', 'A voice session is already reserved. No new session was started.'],
    tts_input_unavailable: ['Този отговор не може да бъде прочетен в ограничения тест. Текстът остава наличен.', 'This reply cannot be spoken within the limited test. The text remains available.'],
    tts_unavailable: ['Гласовият отговор не беше получен. Текстът е наличен. Няма автоматичен повторен опит.', 'Audio could not be retrieved. The text is available. There is no automatic retry.'],
    media_unavailable: ['Гласовата връзка не успя. Продължи с текст. Няма автоматичен повторен опит.', 'The voice connection failed. Continue in text. There is no automatic retry.'],
    playback_error: ['Звукът не беше възпроизведен успешно. Текстът остава наличен.', 'Audio playback failed. The text remains available.'],
  };
  function voiceError(code, fallback = 'media_unavailable') {
    const safe = Object.hasOwn(messages, code) ? code : fallback;
    return Object.assign(new Error(safe), { code: safe, terminal: terminalErrors.has(safe) });
  }
  async function responseError(response, fallback) {
    let code;
    try { code = (await response.json()).error; } catch (_) {}
    if ((response.status === 401 || response.status === 403)
        && !['pilot_expired', 'pilot_disabled', 'forbidden'].includes(code)) code = 'forbidden';
    return voiceError(code, fallback);
  }
  async function pilotAllowances(signal) {
    const response = await root.fetch('/api/live-voice/allowances', { credentials: 'same-origin', cache: 'no-store', signal });
    if (!response.ok) throw await responseError(response, 'pilot_unavailable');
    const data = await response.json();
    if (!data || !data.tts || !data.media || !Number.isInteger(data.tts.remaining_requests)
        || data.tts.remaining_requests < 0 || data.tts.remaining_requests > 4
        || !Number.isInteger(data.media.remaining_seconds) || data.media.remaining_seconds < 0
        || typeof data.tts.available !== 'boolean' || typeof data.media.available !== 'boolean') {
      throw voiceError('pilot_unavailable');
    }
    return data;
  }

  // Local, bounded diagnostics only. No transcripts, IDs, audio or wall-clock
  // timestamps. playback_start measures the browser's playing event, not proof
  // that a physical speaker was audible. coach_response includes validation.
  const timingStages = new Set(['transcription', 'coach_response', 'tts_headers',
    'tts_first_audio', 'tts_complete', 'playback_start']);
  const timingRecords = [];
  const timing = Object.freeze({
    record(stage, milliseconds) {
      if (!timingStages.has(stage) || !Number.isFinite(milliseconds) || milliseconds < 0 || milliseconds > 180000) return;
      timingRecords.push(Object.freeze({ stage, milliseconds: Math.round(milliseconds) }));
      if (timingRecords.length > 32) timingRecords.shift();
    },
    snapshot: () => timingRecords.map(item => ({ ...item })),
  });

  class SpeechPlayback {
    static supported() {
      return !!(root.MediaSource && root.MediaSource.isTypeSupported('audio/mpeg'));
    }
    constructor(audio, signal) {
      this.audio = audio; this.signal = signal; this.complete = false;
      this.source = new root.MediaSource();
      this.url = URL.createObjectURL(this.source);
      audio.src = this.url;
    }
    async wait(target, success, action) {
      if (this.signal.aborted) throw voiceError('playback_error');
      await new Promise((resolve, reject) => {
        const cleanup = () => {
          target.removeEventListener(success, done); target.removeEventListener('error', fail);
          this.signal.removeEventListener('abort', fail);
        };
        const done = () => { cleanup(); resolve(); };
        const fail = () => { cleanup(); reject(voiceError('playback_error')); };
        target.addEventListener(success, done, { once: true });
        target.addEventListener('error', fail, { once: true });
        this.signal.addEventListener('abort', fail, { once: true });
        try { if (action) action(); } catch (_) { fail(); }
      });
    }
    async pump(response) {
      if (this.source.readyState !== 'open') await this.wait(this.source, 'sourceopen');
      if (this.signal.aborted) throw voiceError('playback_error');
      const buffer = this.source.addSourceBuffer('audio/mpeg');
      const reader = this.reader = response.body.getReader(), decoder = new TextDecoder();
      let pending = '', bytes = 0, done = false;
      try {
        while (true) {
          const part = await reader.read();
          if (this.signal.aborted) throw voiceError('playback_error');
          pending += decoder.decode(part.value || new Uint8Array(), { stream: !part.done });
          const lines = pending.split('\n'); pending = lines.pop();
          for (const line of lines) {
            if (!line || line.length > 48000 || done) throw voiceError('playback_error');
            const frame = JSON.parse(line);
            if (frame.error) throw voiceError(frame.error, 'tts_unavailable');
            if (frame.done === true) {
              if (!bytes) throw voiceError('playback_error');
              done = true;
              for (const stage of ['tts_headers', 'tts_first_audio', 'tts_complete']) {
                timing.record(stage, frame.timings && frame.timings[stage]);
              }
            } else {
              if (typeof frame.audio !== 'string' || frame.audio.length > 44000) throw voiceError('playback_error');
              const binary = atob(frame.audio), chunk = Uint8Array.from(binary, char => char.charCodeAt(0));
              bytes += chunk.length;
              if (!chunk.length || bytes > 4 * 1024 * 1024) throw voiceError('playback_error');
              // Backpressure: one append at a time, no unbounded audio queue.
              await this.wait(buffer, 'updateend', () => buffer.appendBuffer(chunk));
            }
          }
          if (pending.length > 48000) throw voiceError('playback_error');
          if (part.done) break;
        }
        // A clean HTTP EOF alone is not synthesis/playback completion. Require
        // the server's marker after a fully read, authorized provider response.
        if (!done || pending || this.signal.aborted) throw voiceError('playback_error');
        this.complete = true; this.source.endOfStream();
      } catch (error) {
        throw voiceError(error.code, 'playback_error');
      } finally {
        this.reader = null; await reader.cancel().catch(() => {});
      }
    }
    close() {
      if (this.reader) void this.reader.cancel().catch(() => {});
      this.audio.removeAttribute('src'); this.audio.load(); URL.revokeObjectURL(this.url);
    }
  }

  function transcriptionIssue(event, language) {
    const text = typeof event.transcript === 'string' ? event.transcript.trim() : '';
    if (!text || !/\p{L}|\p{N}/u.test(text)) return 'empty_transcription';
    if (Array.isArray(event.languages) && (!event.languages.length ||
        !event.languages.some(item => item && /^(?:bg|en)(?:-|$)/i.test(item.code)))) return 'uncertain_language';
    // Provider language evidence and script checks are gates, not a claimed accuracy score.
    if (language === 'bg' && [...text].some(char => /\p{L}/u.test(char) && !/[A-Za-z\u0400-\u04ff]/u.test(char))) return 'unexpected_script';
    const probabilities = Array.isArray(event.logprobs)
      ? event.logprobs.map(item => item && item.logprob).filter(Number.isFinite) : [];
    if (probabilities.length && probabilities.reduce((sum, value) => sum + value, 0) / probabilities.length < -1.5) return 'low_confidence';
    if (Number.isFinite(event.recognitionConfidence) && event.recognitionConfidence > 0 && event.recognitionConfidence < 0.5) return 'low_confidence';
    return null;
  }

  class MockTransport {
    constructor() { this.closed = false; this.muted = false; }
    async connect({ language, onEvent, onDisconnect, signal }) {
      this.language = language;
      this.onEvent = onEvent; this.onDisconnect = onDisconnect;
      signal.addEventListener('abort', () => this.close(), { once: true });
    }
    emit(event) { if (!this.closed) this.onEvent(event); }
    disconnect() { if (!this.closed) this.onDisconnect(); }
    mute(value) { this.muted = value; }
    close() { this.closed = true; }
  }

  class RelayTransport {
    constructor({ media = navigator.mediaDevices, Socket = root.WebSocket, preflight = pilotAllowances,
                  Context = root.AudioContext, Worklet = root.AudioWorkletNode } = {}) {
      Object.assign(this, { media, Socket, Context, Worklet, preflight });
      this.closed = false; this.pending = 0; this.muted = false;
    }
    async connect({ language, onEvent, onDisconnect, signal }) {
      if (!this.media || !this.Socket || !this.Context || !this.Worklet) throw new Error('unsupported');
      signal.addEventListener('abort', () => this.close(), { once: true });
      const allowance = await this.preflight(signal);
      if (this.closed || signal.aborted) throw new Error('cancelled');
      if (!allowance.tts.available) throw voiceError(allowance.tts.error, 'pilot_unavailable');
      if (!allowance.media.available) throw voiceError(allowance.media.error, 'pilot_unavailable');
      const stream = await this.media.getUserMedia({ audio: {
        echoCancellation: true, noiseSuppression: true, autoGainControl: true
      } });
      if (this.closed || signal.aborted) {
        stream.getTracks().forEach(track => track.stop()); throw new Error('cancelled');
      }
      this.stream = stream;
      const url = new URL('/api/live-voice/media?lang=' + language, location.href);
      url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = this.socket = new this.Socket(url.href);
      await new Promise((resolve, reject) => {
        this.rejectReady = reject;
        let ready = false, diagnosing = false;
        const denied = () => {
          if (diagnosing || this.closed) return;
          if (ready) { onEvent({ type: 'error', code: 'media_unavailable' }); return; }
          diagnosing = true;
          // A browser cannot read the HTTP body of a rejected WebSocket upgrade.
          // Re-read non-billable status once; never retry the connection itself.
          this.preflight(signal).then(current => {
            const unavailable = !current.tts.available ? current.tts : !current.media.available ? current.media : null;
            reject(voiceError(unavailable && unavailable.error));
          }).catch(reject);
        };
        ws.onerror = denied;
        ws.onclose = () => {
          if (this.closed) return;
          if (!ready) { denied(); return; }
          this.close(); onEvent({ type: 'session.ended' });
        };
        ws.onmessage = message => {
          if (this.closed || typeof message.data !== 'string' || message.data.length > 32768) return;
          let event; try { event = JSON.parse(message.data); } catch (_) { return; }
          if (event.type === 'session.ready') { ready = true; resolve(); return; }
          if (event.type === 'audio.accepted') { this.pending = Math.max(0, this.pending - 1); return; }
          onEvent(event);
        };
      });
      if (this.closed || signal.aborted) throw new Error('cancelled');
      const context = this.context = new this.Context({ sampleRate: 24000, latencyHint: 'interactive' });
      if (Number.isFinite(context.sampleRate) && context.sampleRate < 24000) throw new Error('unsupported_audio_rate');
      await context.audioWorklet.addModule('/static/live_voice_capture.js');
      if (this.closed || signal.aborted) throw new Error('cancelled');
      this.source = context.createMediaStreamSource(stream);
      this.capture = new this.Worklet(context, 'apex-voice-capture');
      this.silent = context.createGain(); this.silent.gain.value = 0;
      this.capture.port.onmessage = message => {
        if (this.closed || this.muted || ws.readyState !== 1) return;
        const frame = message.data;
        if (!(frame instanceof ArrayBuffer) || frame.byteLength !== 4800) return;
        // Eight 100-ms frames cover normal network RTT without unbounded backlog.
        if (this.pending >= 8 || ws.bufferedAmount > 38400) { this.close(); onDisconnect(); return; }
        this.pending++; ws.send(frame);
      };
      this.source.connect(this.capture); this.capture.connect(this.silent); this.silent.connect(context.destination);
      await context.resume();
      if (this.closed || signal.aborted) throw new Error('cancelled');
    }
    mute(value) {
      this.muted = value;
      if (this.stream) this.stream.getAudioTracks().forEach(track => { track.enabled = !value; });
    }
    close() {
      this.closed = true;
      if (this.rejectReady) this.rejectReady(new Error('cancelled'));
      if (this.capture) { this.capture.port.onmessage = null; this.capture.disconnect(); }
      if (this.source) this.source.disconnect();
      if (this.silent) this.silent.disconnect();
      if (this.socket) {
        this.socket.onmessage = this.socket.onerror = this.socket.onclose = null; this.socket.close();
      }
      if (this.context) void this.context.close().catch(() => {});
      if (this.stream) this.stream.getTracks().forEach(track => track.stop());
      this.socket = this.context = this.stream = this.source = this.capture = this.silent = null;
    }
  }

  class Controller {
    constructor({ transportFactory, owner, language, onState, onFact, onTranscript, onUncertain = async () => {},
                  cancelAuthority, speak, stopSpeaking, fallback, onError = () => {}, onEnded = () => {},
                  schedule = (fn, delay) => root.setTimeout(fn, delay),
                  unschedule = id => root.clearTimeout(id),
                  clock = () => root.performance.now(),
                  connectionTimeout = 20000 }) {
      Object.assign(this, { transportFactory, owner, language, onState, onFact, onTranscript, onUncertain,
        cancelAuthority, speakOutput: speak, stopSpeaking, fallback, onError, onEnded, schedule, unschedule, clock, connectionTimeout });
      this.active = false; this.generation = 0; this.turn = 0; this.reconnects = 0;
      this.seen = new Set(); this.state = 'IDLE';
    }
    valid(generation = this.generation) {
      if (this.active && this.owner() !== this.startedOwner) this.stop();
      return this.active && generation === this.generation;
    }
    set(state) { this.state = state; this.onState(state); }
    async start() {
      this.stop(); this.active = true; this.startedOwner = this.owner();
      this.reconnects = 0; this.seen.clear(); this.set('THINKING');
      return this.connect();
    }
    disposeConnection() {
      this.unschedule(this.connectionTimer); this.connectionTimer = null;
      if (this.abort) this.abort.abort();
      if (this.transport) this.transport.close();
      this.transport = null; this.abort = null;
    }
    async connect() {
      const generation = ++this.generation;
      const abort = this.abort = new AbortController();
      const transport = this.transport = this.transportFactory();
      const language = this.connectedLanguage = this.language();
      const expired = new Promise((_, reject) => {
        this.connectionTimer = this.schedule(() => reject(new Error('connection_timeout')), this.connectionTimeout);
        abort.signal.addEventListener('abort', () => reject(new Error('cancelled')), { once: true });
      });
      try {
        await Promise.race([transport.connect({ language, signal: abort.signal,
          onEvent: event => { if (this.valid(generation)) this.event(event); },
          onDisconnect: () => { if (this.valid(generation)) this.disconnected(); }
        }), expired]);
        if (!this.valid(generation)) return false;
        this.unschedule(this.connectionTimer); this.connectionTimer = null;
        this.set('LISTENING'); this.onFact('keystroke'); return true;
      } catch (error) {
        if (!this.valid(generation)) return false;
        this.fail(error); return false;
      }
    }
    event(event) {
      if (!event || typeof event !== 'object') return;
      if (event.type === 'session.ended') { this.stop(); this.onEnded(); return; }
      // An unexpected model response is never rendered, spoken or executed.
      if (typeof event.type === 'string' && event.type.startsWith('response.')) return;
      if (event.type === 'error') { this.fail(voiceError(event.code)); return; }
      if (event.type === 'input_audio_buffer.speech_started') {
        this.transcriptionStart = null;
        if (['SPEAKING', 'THINKING'].includes(this.state)) this.interrupt();
        this.onFact('keystroke');
      }
      if (event.type === 'input_audio_buffer.speech_stopped') this.transcriptionStart = this.clock();
      if (event.type !== 'conversation.item.input_audio_transcription.completed') return;
      const id = event.item_id, text = event.transcript;
      if (typeof id !== 'string' || !id || id.length > 200 || this.seen.has(id)
          || typeof text !== 'string' || !text.trim() || text.length > 4000) return;
      // Bounded identity cache; never replay audio/turns when reconnecting.
      if (this.seen.size >= 128) { this.fail(); return; }
      this.seen.add(id);
      if (this.transcriptionStart != null) timing.record('transcription', this.clock() - this.transcriptionStart);
      this.transcriptionStart = null;
      if (['THINKING', 'SPEAKING'].includes(this.state)) this.interrupt();
      const generation = this.generation, turn = ++this.turn;
      const issue = transcriptionIssue(event, this.language());
      this.set('THINKING');
      Promise.resolve().then(() => {
        if (this.valid(generation) && turn === this.turn) return issue ? this.onUncertain(issue) : this.onTranscript(text.trim());
      }).then(() => {
        if (this.valid(generation) && turn === this.turn && this.state === 'THINKING') return this.listenAfterTurn();
      }).catch(() => { if (this.valid(generation) && turn === this.turn) this.set('ERROR'); });
    }
    async listenAfterTurn() {
      if (this.connectedLanguage !== this.language()) {
        // Reconfigure through the existing server-owned SDP contract, never replay a turn.
        this.disposeConnection(); this.set('THINKING'); await this.connect();
      } else this.set('LISTENING');
    }
    interrupt() {
      ++this.turn; this.stopSpeaking(); this.cancelAuthority();
      this.set('INTERRUPTED'); this.set('LISTENING');
    }
    async say(text, language = this.language()) {
      if (!this.valid()) return;
      this.stopSpeaking();
      const generation = this.generation, turn = ++this.turn;
      this.set('SPEAKING');
      // Existing VoiceOut owns audio and Core speaking pulses. Do not duplicate them.
      try { await this.speakOutput(text, language); }
      catch (error) { if (this.valid(generation) && turn === this.turn) this.fail(error); }
      if (this.valid(generation) && turn === this.turn && this.state === 'SPEAKING') await this.listenAfterTurn();
    }
    disconnected() {
      // Restricted pilot: a new connection could consume another reservation.
      this.fail(voiceError('media_unavailable'));
    }
    fail(error = voiceError('media_unavailable')) {
      this.stop(); this.set('ERROR'); this.onError(voiceError(error.code));
    }
    stop() {
      const wasActive = this.active;
      this.active = false; ++this.generation; ++this.turn;
      this.unschedule(this.retryTimer); this.retryTimer = null;
      this.disposeConnection(); this.stopSpeaking();
      if (wasActive) this.cancelAuthority();
      this.seen.clear(); this.set('IDLE');
      this.transcriptionStart = null;
    }
  }
  root.ApexLiveVoice = Object.freeze({ Controller, RelayTransport, MockTransport, transcriptionIssue,
    voiceError, responseError, pilotAllowances, timing, SpeechPlayback,
    errorMessage: (code, language) => (messages[code] || messages.media_unavailable)[language === 'bg' ? 0 : 1] });
})(window);

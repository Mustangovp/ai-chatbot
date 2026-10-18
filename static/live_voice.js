/* Local prototype: Realtime is input transport, never coaching authority.
 * No keys, ephemeral credentials, profile or history are sent by this module.
 * MOCK_PASS is not evidence of microphone quality, latency or model access. */
(function (root) {
  'use strict';

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
    constructor({ media = navigator.mediaDevices, Socket = root.WebSocket,
                  Context = root.AudioContext, Worklet = root.AudioWorkletNode } = {}) {
      Object.assign(this, { media, Socket, Context, Worklet });
      this.closed = false; this.pending = 0; this.muted = false;
    }
    async connect({ language, onEvent, onDisconnect, signal }) {
      if (!this.media || !this.Socket || !this.Context || !this.Worklet) throw new Error('unsupported');
      signal.addEventListener('abort', () => this.close(), { once: true });
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
        ws.onerror = () => reject(new Error('relay_unavailable'));
        ws.onclose = () => { if (!this.closed) { this.close(); onEvent({ type: 'session.ended' }); } };
        ws.onmessage = message => {
          if (this.closed || typeof message.data !== 'string' || message.data.length > 32768) return;
          let event; try { event = JSON.parse(message.data); } catch (_) { return; }
          if (event.type === 'session.ready') { resolve(); return; }
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
                  cancelAuthority, speak, stopSpeaking, fallback, onEnded = () => {},
                  schedule = (fn, delay) => root.setTimeout(fn, delay),
                  unschedule = id => root.clearTimeout(id),
                  connectionTimeout = 20000 }) {
      Object.assign(this, { transportFactory, owner, language, onState, onFact, onTranscript, onUncertain,
        cancelAuthority, speakOutput: speak, stopSpeaking, fallback, onEnded, schedule, unschedule, connectionTimeout });
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
      } catch (_) {
        if (!this.valid(generation)) return false;
        this.fail(); return false;
      }
    }
    event(event) {
      if (!event || typeof event !== 'object') return;
      if (event.type === 'session.ended') { this.stop(); this.onEnded(); return; }
      // An unexpected model response is never rendered, spoken or executed.
      if (typeof event.type === 'string' && event.type.startsWith('response.')) return;
      if (event.type === 'error') { this.fail(); return; }
      if (event.type === 'input_audio_buffer.speech_started') {
        if (['SPEAKING', 'THINKING'].includes(this.state)) this.interrupt();
        this.onFact('keystroke');
      }
      if (event.type !== 'conversation.item.input_audio_transcription.completed') return;
      const id = event.item_id, text = event.transcript;
      if (typeof id !== 'string' || !id || id.length > 200 || this.seen.has(id)
          || typeof text !== 'string' || !text.trim() || text.length > 4000) return;
      // Bounded identity cache; never replay audio/turns when reconnecting.
      if (this.seen.size >= 128) { this.fail(); return; }
      this.seen.add(id);
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
      catch (_) { if (this.valid(generation) && turn === this.turn) this.set('ERROR'); }
      if (this.valid(generation) && turn === this.turn && this.state === 'SPEAKING') await this.listenAfterTurn();
    }
    disconnected() {
      ++this.generation; ++this.turn; this.stopSpeaking(); this.cancelAuthority();
      this.disposeConnection();
      if (this.reconnects >= 2) { this.fail(); return; }
      const delay = [250, 1000][this.reconnects++];
      this.set('THINKING');
      this.retryTimer = this.schedule(() => { this.retryTimer = null; if (this.valid()) void this.connect(); }, delay);
    }
    fail() {
      this.stop(); this.set('ERROR'); this.fallback();
    }
    stop() {
      const wasActive = this.active;
      this.active = false; ++this.generation; ++this.turn;
      this.unschedule(this.retryTimer); this.retryTimer = null;
      this.disposeConnection(); this.stopSpeaking();
      if (wasActive) this.cancelAuthority();
      this.seen.clear(); this.set('IDLE');
    }
  }
  root.ApexLiveVoice = Object.freeze({ Controller, RelayTransport, MockTransport, transcriptionIssue });
})(window);

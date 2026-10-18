/* 100-ms mono PCM16 frames. Audio is never persisted or played by this worklet. */
class ApexVoiceCapture extends AudioWorkletProcessor {
  constructor() {
    super(); this.frame = new Int16Array(2400); this.index = 0;
    this.phase = 0; this.sum = 0; this.count = 0;
  }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) for (const sample of channel) {
      this.sum += sample; this.count++; this.phase += 24000;
      if (this.phase >= sampleRate) {
        this.phase -= sampleRate;
        const value = Math.max(-1, Math.min(1, this.sum / this.count));
        this.sum = 0; this.count = 0;
        this.frame[this.index++] = Math.round(value * (value < 0 ? 32768 : 32767));
        if (this.index === this.frame.length) {
          this.port.postMessage(this.frame.buffer, [this.frame.buffer]);
          this.frame = new Int16Array(2400); this.index = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor('apex-voice-capture', ApexVoiceCapture);

import { PCMResampler } from "./pcm-resampler.mjs";
class TalynCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.resampler = new PCMResampler(sampleRate);
    this.muted = false;
    this.port.onmessage = (e) => {
      this.muted = !!e.data.muted;
    };
  }
  process(inputs) {
    const samples = inputs[0]?.[0];
    if (samples) {
      const input = this.muted ? new Float32Array(samples.length) : samples;
      let power = 0;
      for (const x of input) power += x * x;
      for (const data of this.resampler.push(input))
        this.port.postMessage(
          { pcm: data, rms: Math.sqrt(power / input.length) },
          [data],
        );
    }
    return true;
  }
}
registerProcessor("talyn-capture", TalynCapture);

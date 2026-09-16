// Stateful linear resampler. Produces mono signed 16-bit little-endian PCM in 100 ms packets.
export class PCMResampler {
  constructor(inputRate, outputRate = 16000, packetSamples = 1600) {
    this.step = inputRate / outputRate;
    this.position = 0;
    this.samples = [];
    this.packet = new Int16Array(packetSamples);
    this.used = 0;
  }
  push(input) {
    this.samples.push(...input);
    const packets = [];
    while (this.position + 1 < this.samples.length) {
      const i = Math.floor(this.position), t = this.position - i;
      const value = Math.max(-1, Math.min(1, this.samples[i] * (1-t) + this.samples[i+1] * t));
      this.packet[this.used++] = Math.round(value < 0 ? value * 32768 : value * 32767);
      if (this.used === this.packet.length) {
        const buffer = new ArrayBuffer(this.packet.length * 2), view = new DataView(buffer);
        for (let n = 0; n < this.packet.length; n++) view.setInt16(n * 2, this.packet[n], true);
        packets.push(buffer); this.used = 0;
      }
      this.position += this.step;
    }
    const consumed = Math.min(Math.floor(this.position), this.samples.length);
    this.samples.splice(0, consumed); this.position -= consumed;
    return packets;
  }
}

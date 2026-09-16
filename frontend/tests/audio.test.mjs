import { test } from "node:test";
import assert from "node:assert/strict";
import { PCMResampler } from "../public/pcm-resampler.mjs";
for (const rate of [44100, 48000, 16000]) {
  test(`PCM preserves a 1 kHz tone and packet boundaries at ${rate} Hz`, () => {
    const resampler = new PCMResampler(rate);
    const packets = [];
    for (let offset = 0; offset < rate + 128; offset += 128) {
      const input = new Float32Array(128);
      for (let i = 0; i < 128; i++)
        input[i] = 0.5 * Math.sin((2 * Math.PI * 1000 * (offset + i)) / rate);
      packets.push(...resampler.push(input));
    }
    assert.equal(packets.length, 10);
    assert.ok(packets.every((p) => p.byteLength === 3200));
    const values = packets.flatMap((p) => {
      const v = new DataView(p);
      return Array.from({ length: 1600 }, (_, i) => v.getInt16(i * 2, true));
    });
    const crossings = values
      .slice(1)
      .filter((x, i) => values[i] <= 0 && x > 0).length;
    assert.ok(Math.abs(crossings - 1000) <= 2);
    assert.ok(Math.max(...values) <= 16384);
  });
}

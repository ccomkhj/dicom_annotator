import { describe, it, expect } from "vitest";
import {
  base64ToUint8,
  uint8ToBase64,
  encodeLabelEnvelope,
  applyLabelEnvelope,
  propagateSlice,
  type MaskEnvelope,
} from "./mask-codec";

describe("base64 round-trip", () => {
  it("encodes and decodes arbitrary bytes", () => {
    const arr = new Uint8Array([0, 1, 2, 254, 255, 0, 128]);
    expect(Array.from(base64ToUint8(uint8ToBase64(arr)))).toEqual(Array.from(arr));
  });
});

describe("encodeLabelEnvelope", () => {
  // dimensions are Cornerstone [cols, rows, depth]; envelope shape is [depth, rows, cols].
  const dims: [number, number, number] = [4, 3, 2]; // cols=4, rows=3, depth=2 -> 24 voxels

  it("uses NIfTI [depth, rows, cols] shape order", () => {
    const scalar = new Uint8Array(24);
    const env = encodeLabelEnvelope(scalar, dims, 1);
    expect(env.shape).toEqual([2, 3, 4]);
    expect(env.dtype).toBe("uint8");
  });

  it("extracts only the requested label as a binary plane", () => {
    const scalar = new Uint8Array(24);
    scalar[5] = 1;
    scalar[6] = 2; // a different label
    scalar[7] = 1;
    const env = encodeLabelEnvelope(scalar, dims, 1);
    const bytes = base64ToUint8(env.data);
    expect(bytes[5]).toBe(1);
    expect(bytes[6]).toBe(0); // label 2 excluded
    expect(bytes[7]).toBe(1);
    expect(bytes.reduce((a, b) => a + b, 0)).toBe(2);
  });
});

describe("applyLabelEnvelope (multi-label load — the P0 data-loss fix)", () => {
  const dims: [number, number, number] = [4, 3, 2];

  function planeFor(scalar: Uint8Array, labelId: number): string {
    return encodeLabelEnvelope(scalar, dims, labelId).data;
  }

  it("does not clear previously-loaded labels", () => {
    // Build a source volume with label 1 at voxel 5 and label 2 at voxel 10.
    const source = new Uint8Array(24);
    source[5] = 1;
    source[10] = 2;
    const env1 = planeFor(source, 1);
    const env2 = planeFor(source, 2);

    // Load both into a fresh buffer, as main.ts does in its label loop.
    const target = new Uint8Array(24);
    applyLabelEnvelope(target, env1, 1);
    applyLabelEnvelope(target, env2, 2); // must NOT wipe label 1

    expect(target[5]).toBe(1);
    expect(target[10]).toBe(2);
  });

  it("full multi-label round-trips through encode -> apply", () => {
    const source = new Uint8Array(24);
    source[0] = 1;
    source[11] = 1;
    source[12] = 2;
    source[23] = 2;

    const envs: Record<number, MaskEnvelope> = {
      1: encodeLabelEnvelope(source, dims, 1),
      2: encodeLabelEnvelope(source, dims, 2),
    };

    const restored = new Uint8Array(24);
    applyLabelEnvelope(restored, envs[1].data, 1);
    applyLabelEnvelope(restored, envs[2].data, 2);

    expect(Array.from(restored)).toEqual(Array.from(source));
  });
});

describe("propagateSlice", () => {
  const sliceSize = 4; // 2x2 slices

  it("is a no-op on the first slice", () => {
    const scalar = new Uint8Array([1, 1, 1, 1, 0, 0, 0, 0]);
    propagateSlice(scalar, sliceSize, 0, 1);
    expect(Array.from(scalar.slice(0, 4))).toEqual([1, 1, 1, 1]);
  });

  it("copies the requested label from the previous slice into the current", () => {
    const scalar = new Uint8Array(12); // 3 slices of 4
    // slice 0 has label 1 at voxel 0 and label 2 at voxel 1
    scalar[0] = 1;
    scalar[1] = 2;
    propagateSlice(scalar, sliceSize, 1, 1);
    expect(scalar[4]).toBe(1); // label 1 copied to slice 1
    expect(scalar[5]).toBe(0); // label 2 NOT copied (different label)
  });

  it("does not erase existing voxels in the destination slice", () => {
    const scalar = new Uint8Array(8);
    scalar[0] = 1;       // src slice voxel 0
    scalar[4 + 3] = 1;   // dst slice already has voxel 3
    propagateSlice(scalar, sliceSize, 1, 1);
    expect(scalar[4]).toBe(1);
    expect(scalar[4 + 3]).toBe(1); // preserved
  });
});

// Pure (Cornerstone-free) encode/decode between the backend MaskEnvelope wire
// format and a flat Cornerstone labelmap scalar buffer. Kept dependency-free so
// it can be unit-tested without a browser/WebGL — this is the only frontend code
// that must agree byte-for-byte with the Python `MaskEnvelope`.

export interface MaskEnvelope {
  shape: [number, number, number]; // [depth, rows, cols]
  dtype: "uint8";
  data: string; // base64
}

export function base64ToUint8(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export function uint8ToBase64(arr: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < arr.length; i++) bin += String.fromCharCode(arr[i]);
  return btoa(bin);
}

/**
 * Build the per-label binary envelope from the shared labelmap buffer.
 * `dimensions` is Cornerstone's [cols, rows, depth] (x, y, z); the envelope
 * shape is [depth, rows, cols] to match NIfTI/numpy on the backend. The flat
 * buffer is copied linearly — both index orders are x-fastest, so the linear
 * copy preserves voxel identity.
 */
export function encodeLabelEnvelope(
  scalar: Uint8Array,
  dimensions: [number, number, number],
  labelId: number,
): MaskEnvelope {
  const [cols, rows, depth] = dimensions;
  const total = depth * rows * cols;
  const out = new Uint8Array(total);
  for (let i = 0; i < total; i++) out[i] = scalar[i] === labelId ? 1 : 0;
  return { shape: [depth, rows, cols], dtype: "uint8", data: uint8ToBase64(out) };
}

/**
 * Write one label's pixels into the shared labelmap buffer. Does NOT clear the
 * buffer first — callers load multiple labels into the same buffer, so clearing
 * here would erase previously-loaded labels (the multi-label data-loss bug).
 */
export function applyLabelEnvelope(scalar: Uint8Array, data: string, labelId: number): void {
  const bytes = base64ToUint8(data);
  const n = Math.min(bytes.length, scalar.length);
  for (let i = 0; i < n; i++) if (bytes[i]) scalar[i] = labelId;
}

/**
 * Copy `labelId` voxels from the previous slice into the current slice (in place).
 * No-op for the first slice. Pure index arithmetic over the flat labelmap buffer.
 */
export function propagateSlice(
  scalar: Uint8Array,
  sliceSize: number,
  currentSliceIdx: number,
  labelId: number,
): void {
  if (currentSliceIdx <= 0) return;
  const src = (currentSliceIdx - 1) * sliceSize;
  const dst = currentSliceIdx * sliceSize;
  for (let i = 0; i < sliceSize; i++) {
    if (scalar[src + i] === labelId) scalar[dst + i] = labelId;
  }
}

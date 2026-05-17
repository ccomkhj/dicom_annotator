import { cache as csCache } from "@cornerstonejs/core";
import { SEG_VOLUME_ID } from "./segmentation";
import { markDirty } from "./dirty";

export function propagateFromPrevious(currentSliceIdx: number, labelId: number): void {
  if (currentSliceIdx <= 0) return;
  const volume = csCache.getVolume(SEG_VOLUME_ID);
  if (!volume) return;
  const [cols, rows] = (volume as any).dimensions as [number, number, number];
  const scalar = (volume as any).scalarData as Uint8Array;
  const sliceSize = rows * cols;
  const srcOffset = (currentSliceIdx - 1) * sliceSize;
  const dstOffset = currentSliceIdx * sliceSize;
  for (let i = 0; i < sliceSize; i++) {
    if (scalar[srcOffset + i] === labelId) scalar[dstOffset + i] = labelId;
  }
  (volume as any).modified?.();
  markDirty();
}

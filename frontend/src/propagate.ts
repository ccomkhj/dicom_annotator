import { cache as csCache } from "@cornerstonejs/core";
import { SEG_VOLUME_ID } from "./segmentation";
import { markDirty } from "./dirty";
import { renderingEngine } from "./cornerstone-init";
import { propagateSlice } from "./mask-codec";

export function propagateFromPrevious(currentSliceIdx: number, labelId: number): void {
  if (currentSliceIdx <= 0) return;
  const volume = csCache.getVolume(SEG_VOLUME_ID);
  if (!volume) return;
  const [cols, rows] = (volume as any).dimensions as [number, number, number];
  propagateSlice((volume as any).scalarData as Uint8Array, rows * cols, currentSliceIdx, labelId);
  (volume as any).modified?.();
  markDirty();
  renderingEngine.render();
}

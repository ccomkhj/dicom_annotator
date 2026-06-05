import { volumeLoader, cache as csCache } from "@cornerstonejs/core";
import * as csTools from "@cornerstonejs/tools";
import { markDirty } from "./dirty";
import { renderingEngine } from "./cornerstone-init";
import { encodeLabelEnvelope, applyLabelEnvelope } from "./mask-codec";

export const TOOL_GROUP_ID = "dicom-annotator-tools";
export const SEG_VOLUME_ID = "dicom-annotator-seg";

function sameDims(a?: number[], b?: number[]): boolean {
  return !!a && !!b && a.length === b.length && a.every((v, i) => v === b[i]);
}

// Best-effort teardown of the current segmentation. Cornerstone v1.77 has
// shifted these method names across point releases, so we try the known
// spellings and swallow failures — a leftover cache entry only matters if the
// subsequent create throws, which surfaces as a load error (not corruption).
// VERIFY IN BROWSER: confirm the seg overlay actually clears on case switch.
async function teardownSegmentation(): Promise<void> {
  const s = csTools.segmentation as any;
  try { await s.removeSegmentationsFromToolGroup?.(TOOL_GROUP_ID); } catch { /* noop */ }
  try { await s.removeSegmentationRepresentations?.(TOOL_GROUP_ID); } catch { /* noop */ }
  try { s.state?.removeSegmentation?.(SEG_VOLUME_ID); } catch { /* noop */ }
  const c = csCache as any;
  try { c.removeVolumeLoadObject?.(SEG_VOLUME_ID); } catch { /* noop */ }
  try { c.removeVolume?.(SEG_VOLUME_ID); } catch { /* noop */ }
}

export async function ensureSegmentationVolume(referenceVolumeId: string): Promise<string> {
  // Use segmentation.state.getSegmentation (v1.77 API) instead of csTools.cache
  const existing = (csTools.segmentation.state as any).getSegmentation?.(SEG_VOLUME_ID);
  const existingVol = csCache.getVolume(SEG_VOLUME_ID) as any;
  const refVol = csCache.getVolume(referenceVolumeId) as any;

  // Reuse only if the existing seg volume shares the new case's voxel grid.
  // Otherwise the labelmap would be the wrong shape for the new reference and
  // PUT would 422 on shape_mismatch — so tear it down and rebuild.
  if (existing && existingVol && refVol && sameDims(existingVol.dimensions, refVol.dimensions)) {
    return SEG_VOLUME_ID;
  }
  if (existing) await teardownSegmentation();

  await (volumeLoader as any).createAndCacheDerivedSegmentationVolume(referenceVolumeId, {
    volumeId: SEG_VOLUME_ID,
  });
  csTools.segmentation.addSegmentations([
    {
      segmentationId: SEG_VOLUME_ID,
      representation: {
        type: csTools.Enums.SegmentationRepresentations.Labelmap,
        data: { volumeId: SEG_VOLUME_ID },
      },
    },
  ]);
  return SEG_VOLUME_ID;
}

export async function bindSegmentationToToolGroup(viewportIds: string[]): Promise<void> {
  // addSegmentationRepresentations is async in v1.77
  await csTools.segmentation.addSegmentationRepresentations(TOOL_GROUP_ID, [
    {
      segmentationId: SEG_VOLUME_ID,
      type: csTools.Enums.SegmentationRepresentations.Labelmap,
    },
  ]);
  void viewportIds;
}

export function setActiveSegmentIndex(labelId: number): void {
  csTools.segmentation.segmentIndex.setActiveSegmentIndex(SEG_VOLUME_ID, labelId);
}

export async function populateFromEnvelope(env: {
  shape: [number, number, number]; dtype: "uint8"; data: string;
}, labelId: number): Promise<void> {
  const volume = csCache.getVolume(SEG_VOLUME_ID);
  if (!volume) throw new Error("segmentation volume not initialized");
  // applyLabelEnvelope does NOT clear — this runs once per label in a loop, and
  // the caller clears the whole volume once before the loop.
  applyLabelEnvelope((volume as any).scalarData as Uint8Array, env.data, labelId);
  (volume as any).modified?.();
  renderingEngine.render();
}

export function extractEnvelope(labelId: number): { shape: [number, number, number]; dtype: "uint8"; data: string } {
  const volume = csCache.getVolume(SEG_VOLUME_ID);
  if (!volume) throw new Error("segmentation volume not initialized");
  return encodeLabelEnvelope(
    (volume as any).scalarData as Uint8Array,
    (volume as any).dimensions as [number, number, number],
    labelId,
  );
}

export function clearSegmentationVolume(): void {
  const volume = csCache.getVolume(SEG_VOLUME_ID);
  if (!volume) return;
  const scalar = (volume as any).scalarData as Uint8Array;
  scalar.fill(0);
  (volume as any).modified?.();
}

export function installDirtyTracker(): void {
  const v = csCache.getVolume(SEG_VOLUME_ID) as any;
  // Guard tied to the volume object: a reused volume is already patched (avoid
  // stacking wrappers per case switch); a recreated volume has no flag and gets
  // a fresh patch.
  if (!v || v.__dirtyTracked) return;
  if (typeof v.modified === "function") {
    const originalModified = v.modified.bind(v);
    v.modified = function () {
      markDirty();
      return originalModified();
    };
    v.__dirtyTracked = true;
  }
}

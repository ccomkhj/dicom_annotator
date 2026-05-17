import { volumeLoader, cache as csCache } from "@cornerstonejs/core";
import * as csTools from "@cornerstonejs/tools";

export const TOOL_GROUP_ID = "dicom-annotator-tools";
export const SEG_VOLUME_ID = "dicom-annotator-seg";

export async function ensureSegmentationVolume(referenceVolumeId: string): Promise<string> {
  // Use segmentation.state.getSegmentation (v1.77 API) instead of csTools.cache
  const existing = (csTools.segmentation.state as any).getSegmentation?.(SEG_VOLUME_ID);
  if (existing) return SEG_VOLUME_ID;

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

function base64ToUint8(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export async function populateFromEnvelope(env: {
  shape: [number, number, number]; dtype: "uint8"; data: string;
}, labelId: number): Promise<void> {
  const volume = csCache.getVolume(SEG_VOLUME_ID);
  if (!volume) throw new Error("segmentation volume not initialized");
  const bytes = base64ToUint8(env.data);
  const [depth, rows, cols] = env.shape;
  const scalar = (volume as any).scalarData as Uint8Array;
  scalar.fill(0);
  for (let z = 0; z < depth; z++) {
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        const src = z * rows * cols + y * cols + x;
        const dst = z * rows * cols + y * cols + x;
        if (bytes[src]) scalar[dst] = labelId;
      }
    }
  }
  (volume as any).modified?.();
}

export function extractEnvelope(labelId: number): { shape: [number, number, number]; dtype: "uint8"; data: string } {
  const volume = csCache.getVolume(SEG_VOLUME_ID);
  if (!volume) throw new Error("segmentation volume not initialized");
  const [cols, rows, depth] = (volume as any).dimensions as [number, number, number];
  const scalar = (volume as any).scalarData as Uint8Array;
  const out = new Uint8Array(depth * rows * cols);
  for (let z = 0; z < depth; z++) {
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        const idx = z * rows * cols + y * cols + x;
        out[idx] = scalar[idx] === labelId ? 1 : 0;
      }
    }
  }
  let bin = "";
  for (let i = 0; i < out.length; i++) bin += String.fromCharCode(out[i]);
  return { shape: [depth, rows, cols], dtype: "uint8", data: btoa(bin) };
}

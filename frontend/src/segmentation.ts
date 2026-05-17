import { volumeLoader } from "@cornerstonejs/core";
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

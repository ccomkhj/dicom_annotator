import { renderingEngine, ViewportType, volumeLoader } from "./cornerstone-init";
import { Enums, setVolumesForViewports } from "@cornerstonejs/core";

interface ManifestResponse {
  slice_urls: string[];
  reference_geometry: {
    shape: [number, number, number];
    spacing: [number, number, number];
    affine: number[][];
  };
}

export async function loadModalityIntoViewport(args: {
  caseId: string;
  modality: string;
  viewportId: string;
  element: HTMLDivElement;
}): Promise<void> {
  const { caseId, modality, viewportId, element } = args;
  const manifestResp = await fetch(`/images/${caseId}/${modality}/manifest.json`);
  const manifest: ManifestResponse = await manifestResp.json();

  const imageIds = manifest.slice_urls.map(
    (u) => `wadouri:${window.location.origin}${u}`
  );
  const volumeId = `cornerstoneStreamingImageVolume:${caseId}:${modality}`;

  renderingEngine.enableElement({
    viewportId,
    type: ViewportType.ORTHOGRAPHIC,
    element,
    defaultOptions: { orientation: Enums.OrientationAxis.AXIAL },
  });

  const volume = await volumeLoader.createAndCacheVolume(volumeId, {
    imageIds,
  });
  // createAndCacheVolume returns Record<string,any>; streaming volumes expose a load() method
  await (volume as unknown as { load: () => Promise<void> }).load();
  await setVolumesForViewports(renderingEngine, [{ volumeId }], [viewportId]);
  renderingEngine.render();
}

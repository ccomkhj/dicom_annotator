import { renderingEngine, ViewportType, volumeLoader } from "./cornerstone-init";
import { Enums, setVolumesForViewports } from "@cornerstonejs/core";
import { synchronizers, SynchronizerManager } from "@cornerstonejs/tools";

export interface LoadCaseArgs {
  caseId: string;
  modalities: { key: string; viewportId: string; element: HTMLDivElement }[];
}

export async function loadCaseIntoViewports(args: LoadCaseArgs): Promise<void> {
  const { caseId, modalities } = args;
  for (const mod of modalities) {
    renderingEngine.enableElement({
      viewportId: mod.viewportId,
      type: ViewportType.ORTHOGRAPHIC,
      element: mod.element,
      defaultOptions: { orientation: Enums.OrientationAxis.AXIAL },
    });
  }

  for (const mod of modalities) {
    const manifestResp = await fetch(`/images/${caseId}/${mod.key}/manifest.json`);
    const manifest = await manifestResp.json();
    const imageIds = manifest.slice_urls.map(
      (u: string) => `wadouri:${window.location.origin}${u}`,
    );
    const volumeId = `cornerstoneStreamingImageVolume:${caseId}:${mod.key}`;
    const volume = await volumeLoader.createAndCacheVolume(volumeId, { imageIds });
    await (volume as unknown as { load: () => Promise<void> }).load();
    await setVolumesForViewports(renderingEngine, [{ volumeId }], [mod.viewportId]);
  }

  // Reuse synchronizers if they already exist (case switching); idempotent .add() is safe.
  let camSync = (SynchronizerManager as any).getSynchronizer("cam-sync");
  if (!camSync) {
    camSync = synchronizers.createCameraPositionSynchronizer("cam-sync");
  }
  let voiSync = (SynchronizerManager as any).getSynchronizer("voi-sync");
  if (!voiSync) {
    voiSync = synchronizers.createVOISynchronizer("voi-sync", { syncInvertState: false, syncColormap: false });
  }
  for (const mod of modalities) {
    try { camSync.add({ renderingEngineId: renderingEngine.id, viewportId: mod.viewportId }); } catch {}
    try { voiSync.add({ renderingEngineId: renderingEngine.id, viewportId: mod.viewportId }); } catch {}
  }

  renderingEngine.render();
}

import { renderingEngine, ViewportType, volumeLoader } from "./cornerstone-init";
import { Enums, setVolumesForViewports, cache as csCache } from "@cornerstonejs/core";
import { synchronizers, SynchronizerManager } from "@cornerstonejs/tools";

export interface LoadCaseArgs {
  caseId: string;
  modalities: { key: string; viewportId: string; element: HTMLDivElement }[];
}

// Image-volume ids loaded for the case currently on screen, so we can purge them
// from the cache after the next case is shown (bounded memory across switches).
let loadedVolumeIds: string[] = [];

export async function loadCaseIntoViewports(args: LoadCaseArgs): Promise<void> {
  const { caseId, modalities } = args;
  for (const mod of modalities) {
    // enableElement throws if the viewport is already enabled (case switch), so
    // only enable a fresh element; existing viewports are reused via setVolumes.
    let alreadyEnabled = false;
    try { alreadyEnabled = !!renderingEngine.getViewport(mod.viewportId); } catch { alreadyEnabled = false; }
    if (!alreadyEnabled) {
      renderingEngine.enableElement({
        viewportId: mod.viewportId,
        type: ViewportType.ORTHOGRAPHIC,
        element: mod.element,
        defaultOptions: { orientation: Enums.OrientationAxis.AXIAL },
      });
    }
  }

  const prevVolumeIds = loadedVolumeIds;
  const newVolumeIds: string[] = [];

  // NOTE: parallel volume loads — peak memory ~= sum(modality sizes). Fine for
  // aligned MRI (~100 MB each). If raw_dicom CTs land here, gate with p-limit(2).
  await Promise.all(modalities.map(async (mod) => {
    const manifestResp = await fetch(`/images/${caseId}/${mod.key}/manifest.json`);
    const manifest = await manifestResp.json();
    const imageIds = manifest.slice_urls.map(
      (u: string) => `wadouri:${window.location.origin}${u}`,
    );
    const volumeId = `cornerstoneStreamingImageVolume:${caseId}:${mod.key}`;
    const volume = await volumeLoader.createAndCacheVolume(volumeId, { imageIds });
    await (volume as unknown as { load: () => Promise<void> }).load();
    await setVolumesForViewports(renderingEngine, [{ volumeId }], [mod.viewportId]);
    newVolumeIds.push(volumeId);
  }));
  loadedVolumeIds = newVolumeIds;

  // Free the previous case's volumes now that the new ones are displayed.
  for (const id of prevVolumeIds) {
    if (newVolumeIds.includes(id)) continue;
    try { (csCache as any).removeVolumeLoadObject?.(id); } catch { /* noop */ }
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

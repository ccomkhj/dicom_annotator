import {
  init as csCoreInit,
  RenderingEngine,
  Enums,
  volumeLoader,
} from "@cornerstonejs/core";
import { init as csToolsInit } from "@cornerstonejs/tools";
import * as dicomImageLoader from "@cornerstonejs/dicom-image-loader";
import dicomParser from "dicom-parser";

let initialized = false;

export async function initCornerstone(): Promise<void> {
  if (initialized) return;
  await csCoreInit();
  await csToolsInit();

  dicomImageLoader.external.cornerstone = await import("@cornerstonejs/core");
  dicomImageLoader.external.dicomParser = dicomParser;
  dicomImageLoader.configure({
    useWebWorkers: false,
    decodeConfig: { convertFloatPixelDataToInt: false },
  });

  initialized = true;
}

export const renderingEngine = new RenderingEngine("dicom-annotator-engine");
export const ViewportType = Enums.ViewportType;
export { volumeLoader };

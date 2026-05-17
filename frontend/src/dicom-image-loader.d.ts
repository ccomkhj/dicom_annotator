declare module "@cornerstonejs/dicom-image-loader" {
  export const external: {
    cornerstone?: unknown;
    dicomParser?: unknown;
  };

  export function configure(options: {
    useWebWorkers?: boolean;
    decodeConfig?: {
      convertFloatPixelDataToInt?: boolean;
    };
    [key: string]: unknown;
  }): void;
}

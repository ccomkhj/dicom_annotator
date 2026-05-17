import { defineConfig } from "vite";
import path from "path";

export default defineConfig({
  resolve: {
    alias: {
      // Stub out @icr/polyseg-wasm to avoid WASM bundling issues.
      // PolySeg segmentation is not needed for the base viewport rendering in Task 9.1.
      "@icr/polyseg-wasm": path.resolve(
        __dirname,
        "src/polyseg-stub.js"
      ),
    },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/images": "http://127.0.0.1:8000",
    },
  },
  optimizeDeps: {
    exclude: ["@cornerstonejs/dicom-image-loader"],
  },
});

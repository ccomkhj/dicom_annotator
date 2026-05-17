import { defineConfig } from "vite";

export default defineConfig({
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

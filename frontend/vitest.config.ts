import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom", // provides window + btoa/atob
    include: ["src/**/*.test.ts"],
  },
});

import { defineConfig } from "vite";
export default defineConfig({
  base: "./",
  build: {
    outDir: new URL("../output/site", import.meta.url).pathname,
    emptyOutDir: true,
  },
});

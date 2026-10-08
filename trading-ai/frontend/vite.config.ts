import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built once into dist/ and served by the local FastAPI server; `npm run dev` proxies to a running backend.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 900 },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
});

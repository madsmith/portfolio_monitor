import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      input: {
        dashboard: resolve(__dirname, "index.html"),
        "control-panel": resolve(__dirname, "control-panel.html"),
      },
    },
  },
  server: {
    host: "127.0.0.1",
    proxy: {
      // Control panel API/SSE — strip /ctl prefix, forward to dev control panel server
      "/ctl": {
        target: "http://localhost:8401",
        rewrite: (path) => path.replace(/^\/ctl/, ""),
      },
      // Dashboard API + WebSocket — forward to main API server
      "/api": { target: "http://localhost:8400", ws: true },
    },
  },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API server runs separately (python -m owstudio serve)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});

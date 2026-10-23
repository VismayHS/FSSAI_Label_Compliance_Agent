/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The client talks to the API at the same origin. In development Vite forwards these paths to the API
// (FSSAI_API_URL, default http://localhost:8000); in Compose, nginx does the same.
const api = process.env.FSSAI_API_URL ?? "http://localhost:8000";
const proxied = ["/v1", "/healthz", "/readyz", "/docs", "/openapi.json"];

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: Object.fromEntries(proxied.map((path) => [path, { target: api, changeOrigin: true }])) },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});

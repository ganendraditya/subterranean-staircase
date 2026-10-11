import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import process from "node:process";
import { defineConfig } from "vite";

const host = process.env.TAURI_DEV_HOST;
const DEV_PORT = 1420;
const HMR_PORT = 1421;
const rootDir = fileURLToPath(new URL(".", import.meta.url));

// https://vite.dev/config/
export default defineConfig(() => ({
  base: "./",
  clearScreen: false,
  server: {
    port: DEV_PORT,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: HMR_PORT,
        }
      : undefined,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },
  build: {
    rollupOptions: {
      input: {
        main: resolve(rootDir, "index.html"),
        overlay: resolve(rootDir, "overlay.html"),
      },
    },
  },
}));

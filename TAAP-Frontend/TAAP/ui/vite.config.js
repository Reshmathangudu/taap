import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const workspaceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, workspaceRoot, "");
  const serviceTarget = env.VITE_TAAP_SERVICE_URL || `http://127.0.0.1:${env.TAAP_SERVICE_PORT || "8787"}`;

  return {
    envDir: workspaceRoot,
    plugins: [react()],
    resolve: {
      alias: {
        "@taap/service-layer": path.resolve(workspaceRoot, "service-layer/src/index.js")
      }
    },
    server: {
      host: "127.0.0.1",
      port: 5174,
      strictPort: true,
      proxy: {
        "/api": {
          target: serviceTarget,
          changeOrigin: true
        },
        "/health": {
          target: serviceTarget,
          changeOrigin: true
        }
      }
    }
  };
});

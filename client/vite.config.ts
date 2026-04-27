import { readFileSync } from "fs";
import path from "path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf-8"));
const rootDir = process.cwd();
const platformComponentPaths = [
  "./src/components/platform/AgentConsole.jsx",
  "./src/components/platform/FlowEngineConsole.jsx",
  "./src/components/platform/ObservabilityDashboard.jsx",
  "./src/components/platform/HealthDashboard.jsx",
  "./src/components/platform/ExecutionConsole.jsx",
  "./src/components/platform/AgentApprovalInbox.jsx",
  "./src/components/platform/AgentRegistry.jsx",
  "./src/components/platform/RippleTraceViewer.jsx",
];

export default defineConfig(({ mode }) => {
  const buildTarget = mode === "app" || mode === "platform" ? mode : "all";

  const input =
    buildTarget === "app"
      ? {
          app: path.resolve(rootDir, "index.html"),
        }
      : buildTarget === "platform"
        ? {
            platform: path.resolve(rootDir, "platform.html"),
          }
        : {
            app: path.resolve(rootDir, "index.html"),
            platform: path.resolve(rootDir, "platform.html"),
          };

  return {
    plugins: [react()],
    define: {
      __APP_VERSION__: JSON.stringify(pkg.version),
    },

    resolve: {
      alias: {
        "@": path.resolve(rootDir, "src"),
      },
    },

    build: {
      sourcemap: mode === "development",
      chunkSizeWarningLimit: 500,
      target: ["chrome90", "firefox88", "safari14", "edge90"],
      outDir: "dist",
      rollupOptions: {
        input,
        output: {
          manualChunks: {
            "vendor-react": ["react", "react-dom", "react-router-dom"],
            "vendor-charts": ["recharts", "d3"],
            "vendor-ui": [
              "@radix-ui/react-slot",
              "@radix-ui/react-tooltip",
              "lucide-react",
              "clsx",
              "class-variance-authority",
              "tailwind-merge",
            ],
            "chunk-platform": platformComponentPaths,
          },
          entryFileNames: (chunkInfo) =>
            chunkInfo.name === "platform"
              ? "platform/assets/[name]-[hash].js"
              : "assets/[name]-[hash].js",
          chunkFileNames: (chunkInfo) => {
            const moduleIds = chunkInfo.moduleIds ?? [];
            const isPlatformChunk = moduleIds.some((moduleId) => {
              const normalizedModuleId = moduleId.replaceAll("\\", "/");
              return normalizedModuleId.includes("/src/platform.tsx") ||
                platformComponentPaths.some((platformPath) =>
                  normalizedModuleId.endsWith(platformPath.replace("./", "/")),
                );
            });

            return isPlatformChunk
              ? "platform/assets/[name]-[hash].js"
              : "assets/[name]-[hash].js";
          },
          assetFileNames: "assets/[name]-[hash][extname]",
        },
      },
    },

    server: {
      proxy: {
        "/api": {
          target: "http://localhost:8000",
          changeOrigin: true,
          rewrite: (routePath) => routePath.replace(/^\/api/, ""),
        },
      },
    },

    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.js"],
      css: false,
      exclude: ["e2e/**", "node_modules/**", "dist/**"],
    },
  };
});

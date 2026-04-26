import { readFileSync } from "fs";
import path from "path";

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf-8"));

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },

  resolve: {
    alias: {
      "@": path.resolve(process.cwd(), "src"),
    },
  },

  build: {
    sourcemap: mode === "development",
    chunkSizeWarningLimit: 500,
    target: ["chrome90", "firefox88", "safari14", "edge90"],
    rollupOptions: {
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
          "chunk-platform": [
            "./src/components/platform/AgentConsole.jsx",
            "./src/components/platform/FlowEngineConsole.jsx",
            "./src/components/platform/ObservabilityDashboard.jsx",
            "./src/components/platform/HealthDashboard.jsx",
            "./src/components/platform/ExecutionConsole.jsx",
            "./src/components/platform/AgentApprovalInbox.jsx",
            "./src/components/platform/AgentRegistry.jsx",
            "./src/components/platform/RippleTraceViewer.jsx",
          ],
        },
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
}));

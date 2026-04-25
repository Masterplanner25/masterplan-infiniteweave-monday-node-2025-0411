import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig(({ mode }) => ({
  plugins: [react()],

  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },

  build: {
    // Production source maps leak source code - disable in prod builds.
    // Use a separate sentry/error-tracking upload step for debugging.
    sourcemap: mode === "development",

    // Warn when any single chunk exceeds 500KB gzipped.
    chunkSizeWarningLimit: 500,

    // Target modern browsers (avoids legacy polyfill bloat).
    // Adjust if you need IE11 or Safari 13 support.
    target: ["chrome90", "firefox88", "safari14", "edge90"],

    rollupOptions: {
      output: {
        manualChunks: {
          // Core React runtime - changes rarely, caches well.
          "vendor-react": ["react", "react-dom", "react-router-dom"],
          // Charting - large, rarely changes.
          "vendor-charts": ["recharts", "d3"],
          // Radix UI primitives - shared across components.
          "vendor-ui": [
            "@radix-ui/react-slot",
            "@radix-ui/react-tooltip",
            "lucide-react",
            "clsx",
            "class-variance-authority",
            "tailwind-merge",
          ],
          // Platform-only operator tooling - only admin users load this.
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

  // Dev server proxy - keeps dev experience clean without CORS config.
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
  },
}));

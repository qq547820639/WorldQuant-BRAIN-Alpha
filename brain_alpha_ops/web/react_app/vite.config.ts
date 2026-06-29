import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";
import { visualizer } from "rollup-plugin-visualizer";

export default defineConfig(({ mode }) => {
  const isAnalyze = mode === "analyze";
  const isProduction = mode === "production" || isAnalyze;

  return {
    plugins: [
      react(),
      isAnalyze &&
        visualizer({
          filename: "dist/stats.html",
          open: false,
          gzipSize: true,
          brotliSize: true,
        }),
    ].filter(Boolean),
    resolve: {
      alias: { "@": path.resolve(__dirname, "src") },
    },
    server: {
      port: 3000,
      hmr: {
        overlay: true,
      },
      proxy: {
        "/api": "http://127.0.0.1:8765",
        "/sse": "http://127.0.0.1:8765",
      },
      watch: {
        usePolling: false,
      },
    },
    optimizeDeps: {
      include: ["react", "react-dom", "react-dom/client", "@tanstack/react-virtual"],
      exclude: [],
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
      sourcemap: !isProduction,
      target: "es2022",
      cssCodeSplit: false,
      cssMinify: "esbuild",
      minify: "esbuild",
      reportCompressedSize: false,
      chunkSizeWarningLimit: 1500,
      modulePreload: false,
      assetsInlineLimit: 16384,
      rollupOptions: {
        treeshake: true,
        output: {
          manualChunks(id) {
            if (!id.includes("node_modules")) return;
            if (id.includes("react-dom") || id.includes("/react/") || id.includes("react/jsx-runtime")) {
              return "react-vendor";
            }
            if (id.includes("@tanstack/")) {
              return "tanstack-vendor";
            }
            return "vendor";
          },
          chunkFileNames: "assets/[name]-[hash].js",
          entryFileNames: "assets/[name]-[hash].js",
          assetFileNames: "assets/[name]-[hash].[ext]",
        },
      },
    },
    esbuild: {
      drop: isProduction ? ["console.debug", "debugger"] : [],
      legalComments: "none",
    },
    test: {
      environment: "jsdom",
      setupFiles: "./tests/setup.ts",
      include: ["tests/**/*.test.{ts,tsx}", "src/**/__tests__/**/*.test.{ts,tsx}"],
      restoreMocks: true,
      clearMocks: true,
    },
  };
});

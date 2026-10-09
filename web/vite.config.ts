import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// 后端地址（与 main.py 的默认端口一致；可用 DSH_API 环境变量覆盖，
// 例如后端跑在 9000：$env:DSH_API="http://127.0.0.1:9000"; pnpm dev）
const API_TARGET = process.env.DSH_API ?? "http://127.0.0.1:8777";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: false,
    // 开发时把 /api 代理到 Python 后端（生产由后端直接托管 dist）
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 1200,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
    // 仅测试环境：d3-drag 在 jsdom 下会抛未捕获异常（合成事件没有 event.view）
    alias: {
      "d3-drag": fileURLToPath(new URL("./src/test/d3-drag-stub.ts", import.meta.url)),
    },
    // @xyflow/* 默认被外部化（不经过 Vite），那样上面的 alias 就拦不到它们 import 的 d3-drag
    server: { deps: { inline: ["@xyflow/react", "@xyflow/system"] } },
  },
});

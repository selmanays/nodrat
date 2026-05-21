import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";
import path from "node:path";

// Vitest config — frontend characterization safety-net bootstrap (PR-7a-0).
//
// Refs:
// - wiki/topics/phase7a-frontend-mini-plan.md — Phase 7a playbook
// - apps/web/src/lib/api.ts — refactor hedefi (2041 LoC / 199 export / 60 caller)
//
// Goal: lock current api.ts pure helper behavior BEFORE any split (PR-7a-1+).
// jsdom env for token storage (localStorage) + apiFetch (global fetch mock).
// React Testing Library NOT installed — component tests deferred.

const dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    exclude: ["node_modules", ".next"],
    testTimeout: 5_000,
  },
});

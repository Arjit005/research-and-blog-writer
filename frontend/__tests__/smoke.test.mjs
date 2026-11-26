import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");

test("globals.css defines dark and light theme tokens", () => {
  const css = fs.readFileSync(path.join(root, "app", "globals.css"), "utf8");
  assert.match(css, /--background:/);
  assert.match(css, /--accent:/);
  assert.match(css, /\[data-theme="light"\]/);
  assert.match(css, /::-webkit-scrollbar/);
});

test("next.config.ts is configured for static export", () => {
  const cfg = fs.readFileSync(path.join(root, "next.config.ts"), "utf8");
  assert.match(cfg, /output:\s*["']export["']/);
});

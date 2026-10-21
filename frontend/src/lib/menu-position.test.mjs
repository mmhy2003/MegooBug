// Run: node --test --experimental-strip-types src/lib/menu-position.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { menuPosition } from "./menu-position.ts";

const viewport = { width: 1280, height: 800 };
const menu = { width: 280, height: 170 };

test("opens below the button, right-aligned, when there is room", () => {
  const anchor = { top: 100, bottom: 132, right: 900 };
  assert.deepEqual(menuPosition(anchor, menu, viewport), { top: 138, left: 620 });
});

test("opens upward near the bottom of the window", () => {
  const anchor = { top: 700, bottom: 732, right: 900 };
  assert.deepEqual(menuPosition(anchor, menu, viewport), { top: 524, left: 620 });
});

test("never runs off the left edge", () => {
  const anchor = { top: 100, bottom: 132, right: 150 };
  assert.equal(menuPosition(anchor, menu, viewport).left, 8);
});

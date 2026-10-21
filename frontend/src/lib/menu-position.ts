// Kept free of imports so it can be unit-tested with plain `node --test`.

const GAP = 6;
const EDGE = 8;

/**
 * Where to put a fixed-position dropdown for a button: right-aligned below
 * it, or above it when it would run past the bottom of the window.
 */
export function menuPosition(
  anchor: { top: number; bottom: number; right: number },
  menu: { width: number; height: number },
  viewport: { width: number; height: number }
): { top: number; left: number } {
  const below = anchor.bottom + GAP;
  const top = below + menu.height > viewport.height - EDGE
    ? Math.max(EDGE, anchor.top - GAP - menu.height)
    : below;
  const left = Math.min(
    Math.max(EDGE, anchor.right - menu.width),
    Math.max(EDGE, viewport.width - menu.width - EDGE)
  );
  return { top, left };
}

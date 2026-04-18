const TAG_PALETTE = Object.freeze([
  "#E11D48",
  "#DB2777",
  "#C026D3",
  "#9333EA",
  "#7C3AED",
  "#6D28D9",
  "#4F46E5",
  "#2563EB",
  "#0284C7",
  "#0891B2",
  "#0F766E",
  "#059669",
  "#16A34A",
  "#65A30D",
  "#4D7C0F",
  "#CA8A04",
  "#D97706",
  "#EA580C",
  "#DC2626",
  "#B91C1C",
  "#F43F5E",
  "#EC4899",
  "#D946EF",
  "#A855F7",
  "#8B5CF6",
  "#6366F1",
  "#3B82F6",
  "#0EA5E9",
  "#06B6D4",
  "#14B8A6",
  "#10B981",
  "#22C55E",
  "#84CC16",
  "#EAB308",
  "#F59E0B",
  "#F97316",
]);

function clampAlpha(alpha) {
  const numeric = Number(alpha);
  if (!Number.isFinite(numeric)) {
    return 1;
  }

  return Math.min(1, Math.max(0, numeric));
}

function rgbForHex(hex) {
  const value = String(hex || "").trim().replace(/^#/, "");
  if (!/^[0-9a-f]{6}$/i.test(value)) {
    return { red: 134, green: 239, blue: 172 };
  }

  return {
    red: Number.parseInt(value.slice(0, 2), 16),
    green: Number.parseInt(value.slice(2, 4), 16),
    blue: Number.parseInt(value.slice(4, 6), 16),
  };
}

function rgbaForHex(hex, alpha) {
  const rgb = rgbForHex(hex);
  return `rgba(${rgb.red}, ${rgb.green}, ${rgb.blue}, ${clampAlpha(alpha)})`;
}

function normalizeTag(value) {
  return String(value || "").trim().toLowerCase();
}

function prefixKeyForTag(tag) {
  const normalized = normalizeTag(tag);
  if (!normalized) {
    return "";
  }

  return normalized.includes(":") ? normalized.split(":", 1)[0] : normalized;
}

function colorForTag(tag) {
  const prefixKey = prefixKeyForTag(tag);
  if (!prefixKey) {
    return TAG_PALETTE[0];
  }

  let hash = 2166136261;
  for (let index = 0; index < prefixKey.length; index += 1) {
    hash ^= prefixKey.charCodeAt(index);
    hash = Math.imul(hash, 16777619) >>> 0;
  }

  hash ^= hash >>> 16;
  hash = Math.imul(hash, 2246822507) >>> 0;
  hash ^= hash >>> 13;

  return TAG_PALETTE[hash % TAG_PALETTE.length];
}

function styleForTag(tag) {
  const color = colorForTag(tag);

  return Object.freeze({
    color,
    background: rgbaForHex(color, 0.14),
    border: rgbaForHex(color, 0.58),
    glow: rgbaForHex(color, 0.2),
  });
}

const PrintHistoryTagColors = Object.freeze({
  palette: TAG_PALETTE,
  normalizeTag,
  prefixKeyForTag,
  colorForTag,
  styleForTag,
  rgbaForHex,
});

window.PrintHistoryTagColors = PrintHistoryTagColors;

export default PrintHistoryTagColors;
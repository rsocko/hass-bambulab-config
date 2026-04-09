const TAG_PALETTE = Object.freeze([
  "#86EFAC",
  "#93C5FD",
  "#F9A8D4",
  "#7DD3FC",
  "#C4B5FD",
  "#FCD34D",
  "#4ADE80",
  "#60A5FA",
  "#EC4899",
  "#38BDF8",
  "#A78BFA",
  "#F59E0B",
  "#FDBA74",
  "#6EE7B7",
  "#FCA5A5",
  "#DDD6FE",
  "#BFDBFE",
  "#FDE68A",
  "#A7F3D0",
  "#67E8F9",
  "#F5D0FE",
  "#FDA4AF",
  "#C7D2FE",
  "#99F6E4",
]);

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

  let hash = 0;
  for (let index = 0; index < prefixKey.length; index += 1) {
    hash = ((hash << 5) - hash + prefixKey.charCodeAt(index)) >>> 0;
  }

  return TAG_PALETTE[hash % TAG_PALETTE.length];
}

const PrintHistoryTagColors = Object.freeze({
  palette: TAG_PALETTE,
  normalizeTag,
  prefixKeyForTag,
  colorForTag,
});

window.PrintHistoryTagColors = PrintHistoryTagColors;

export default PrintHistoryTagColors;
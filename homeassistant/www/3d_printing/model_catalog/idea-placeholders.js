const IDEA_PLACEHOLDER_URLS = [
  "/local/3d_printing/model_catalog/placeholders/idea-01.svg",
  "/local/3d_printing/model_catalog/placeholders/idea-02.svg",
  "/local/3d_printing/model_catalog/placeholders/idea-03.svg",
  "/local/3d_printing/model_catalog/placeholders/idea-04.svg",
  "/local/3d_printing/model_catalog/placeholders/idea-05.svg",
  "/local/3d_printing/model_catalog/placeholders/idea-06.svg",
];

function hashSeed(value) {
  const text = String(value || "idea").trim() || "idea";
  let hash = 5381;
  for (let i = 0; i < text.length; i += 1) {
    hash = ((hash << 5) + hash) + text.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

export function pickIdeaPlaceholderUrl(seed) {
  if (!IDEA_PLACEHOLDER_URLS.length) {
    return "";
  }
  const idx = hashSeed(seed) % IDEA_PLACEHOLDER_URLS.length;
  return IDEA_PLACEHOLDER_URLS[idx];
}

export function hasRenderableMedia(value) {
  return !!String(value || "").trim();
}

export function ideaPlaceholderCandidates() {
  return IDEA_PLACEHOLDER_URLS.slice();
}

/**
 * Lazy-load thumbnail utilities for model catalog cards.
 * 
 * Provides helpers for loading thumbnails on-demand without blocking page render.
 * Used by model-catalog-browser-card.js and model-detail-popup-card.js
 */

/**
 * Configuration for thumbnail lazy-loading
 */
export const THUMBNAIL_LAZY_CONFIG = {
  // Maximum time to wait for thumbnail fetch (ms)
  FETCH_TIMEOUT_MS: 5000,
  // Retry count for failed thumbnail fetches
  RETRY_COUNT: 2,
  // Cache fetched thumbnails in memory to avoid repeat requests
  ENABLE_MEMORY_CACHE: true,
  // Use Intersection Observer for viewport-based lazy loading (optional, high-performance)
  USE_INTERSECTION_OBSERVER: true,
};

// In-memory thumbnail cache (URL -> blob)
const thumbnailCache = new Map();

// Persistent object-URL cache (URL -> object URL string).
// Lets re-renders set <img src> synchronously and avoid the blank/flash gap
// while the observer would otherwise re-fetch (even on memory-cache hits).
const thumbnailObjectUrlCache = new Map();

/**
 * Get a previously resolved object URL for a lazy thumbnail URL, if one
 * has already been fetched and decoded in this session. Returns null if not
 * yet cached.
 *
 * @param {string} thumbnailLazyUrl
 * @returns {string|null}
 */
export function getCachedThumbnailObjectUrl(thumbnailLazyUrl) {
  if (!thumbnailLazyUrl) return null;
  return thumbnailObjectUrlCache.get(thumbnailLazyUrl) || null;
}

/**
 * Fetch a thumbnail image from the lazy-load URL.
 * 
 * @param {string} thumbnailLazyUrl - The /api/models/.../thumbnail endpoint URL
 * @param {object} options - Optional configuration
 * @param {number} options.timeoutMs - Request timeout (default: FETCH_TIMEOUT_MS)
 * @param {number} options.retryCount - Number of retries (default: RETRY_COUNT)
 * @returns {Promise<Blob|null>} Image blob if successful, null if not found/failed
 */
export async function fetchThumbnailImage(thumbnailLazyUrl, options = {}) {
  const timeoutMs = options.timeoutMs ?? THUMBNAIL_LAZY_CONFIG.FETCH_TIMEOUT_MS;
  const retryCount = options.retryCount ?? THUMBNAIL_LAZY_CONFIG.RETRY_COUNT;

  // Check memory cache first
  if (THUMBNAIL_LAZY_CONFIG.ENABLE_MEMORY_CACHE && thumbnailCache.has(thumbnailLazyUrl)) {
    return thumbnailCache.get(thumbnailLazyUrl);
  }

  let lastError;
  for (let attempt = 0; attempt <= retryCount; attempt++) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

      const response = await fetch(thumbnailLazyUrl, {
        method: 'GET',
        signal: controller.signal,
        headers: {
          Accept: 'image/png, image/jpeg',
        },
      });

      clearTimeout(timeoutId);

      // 404 or 415 means no thumbnail available
      if (response.status === 404 || response.status === 415) {
        return null;
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const blob = await response.blob();
      
      // Cache the result
      if (THUMBNAIL_LAZY_CONFIG.ENABLE_MEMORY_CACHE) {
        thumbnailCache.set(thumbnailLazyUrl, blob);
      }

      return blob;
    } catch (error) {
      lastError = error;
      // Continue to next attempt if retries remain
      if (attempt < retryCount) {
        // Exponential backoff: 100ms, 200ms, 400ms, etc.
        await new Promise(resolve => setTimeout(resolve, 100 * Math.pow(2, attempt)));
      }
    }
  }

  console.warn(`Failed to fetch thumbnail after ${retryCount + 1} attempts:`, thumbnailLazyUrl, lastError);
  return null;
}

/**
 * Get a blob URL for display in an <img> element.
 * 
 * @param {Blob} blob - Image blob
 * @returns {string} Object URL suitable for <img src="">
 */
export function getBlobUrl(blob) {
  return blob ? URL.createObjectURL(blob) : null;
}

/**
 * Create an img element with lazy-loaded thumbnail.
 * 
 * @param {string} thumbnailLazyUrl - The /api/models/.../thumbnail endpoint URL
 * @param {object} options - Image element options
 * @param {string} options.alt - Alt text
 * @param {string} options.className - CSS class names
 * @param {object} options.style - Inline styles
 * @returns {Promise<HTMLImageElement|null>} Image element or null if thumbnail not found
 */
export async function createLazyThumbnailImage(thumbnailLazyUrl, options = {}) {
  if (!thumbnailLazyUrl) {
    return null;
  }

  const img = document.createElement('img');
  img.alt = options.alt || 'Model thumbnail';
  if (options.className) img.className = options.className;
  if (options.style) Object.assign(img.style, options.style);

  // Start fetching immediately but don't block
  const blob = await fetchThumbnailImage(thumbnailLazyUrl);
  if (!blob) {
    return null;
  }

  img.src = getBlobUrl(blob);
  return img;
}

/**
 * Setup Intersection Observer-based lazy loading for thumbnails (high-performance).
 * 
 * Usage:
 *   const config = {
 *     imageSelector: 'img[data-thumbnail-lazy-url]',
 *     attrName: 'data-thumbnail-lazy-url',
 *   };
 *   setupThumbnailLazyObserver(config);
 * 
 * @param {object} config - Observer configuration
 * @param {string} config.imageSelector - CSS selector for images
 * @param {string} config.attrName - Attribute name containing thumbnail URL
 * @param {number} config.rootMargin - Margin around viewport (e.g. "50px")
 */
export function setupThumbnailLazyObserver(config = {}) {
  if (!THUMBNAIL_LAZY_CONFIG.USE_INTERSECTION_OBSERVER) {
    return;
  }

  const selector = config.imageSelector || 'img[data-thumbnail-lazy-url]';
  const attrName = config.attrName || 'data-thumbnail-lazy-url';
  const rootMargin = config.rootMargin || '50px';
  const threshold = config.threshold ?? 0;
  const rootElement = config.rootElement || document;
  const observerRoot = config.root ?? null;

  const images = typeof rootElement.querySelectorAll === 'function'
    ? rootElement.querySelectorAll(selector)
    : document.querySelectorAll(selector);
  const observer = new IntersectionObserver(
    async (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;

        const img = entry.target;
        const url = img.getAttribute(attrName);
        if (!url || img.src) {
          continue; // Already loaded
        }

        // Use cached object URL if available to avoid re-creating one per render.
        let objectUrl = thumbnailObjectUrlCache.get(url) || null;
        if (!objectUrl) {
          const blob = await fetchThumbnailImage(url);
          if (blob) {
            objectUrl = getBlobUrl(blob);
            thumbnailObjectUrlCache.set(url, objectUrl);
          }
        }
        if (objectUrl) {
          img.src = objectUrl;
          // Remove the data attribute to prevent re-fetching
          img.removeAttribute(attrName);
        } else {
          // Fetch failed — clear the lazy attribute to stop shimmer animation
          // and mark the image so the card can show a fallback placeholder.
          img.removeAttribute(attrName);
          img.setAttribute('data-thumbnail-failed', 'true');
        }

        // Stop observing after load attempt
        observer.unobserve(img);
      }
    },
    { root: observerRoot, rootMargin, threshold },
  );

  for (const img of images) {
    observer.observe(img);
  }

  return observer;
}

/**
 * Utility: Create a placeholder while thumbnail loads.
 * 
 * @returns {HTMLElement} Placeholder element
 */
export function createThumbnailPlaceholder() {
  const placeholder = document.createElement('div');
  placeholder.className = 'thumbnail-placeholder';
  placeholder.style.cssText = `
    background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    width: 100%;
    height: 100%;
    border-radius: 4px;
  `;
  return placeholder;
}

/**
 * Utility: Add shimmer animation CSS to document.
 */
export function addShimmerAnimation() {
  const styleId = 'thumbnail-shimmer-style';
  if (document.getElementById(styleId)) return;

  const style = document.createElement('style');
  style.id = styleId;
  style.textContent = `
    @keyframes shimmer {
      0% { background-position: 200% 0; }
      100% { background-position: -200% 0; }
    }
  `;
  document.head.appendChild(style);
}

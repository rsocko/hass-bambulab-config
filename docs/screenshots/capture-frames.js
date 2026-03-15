// Rapid frame capture via Playwright — connects to HA dashboard
// Mode 1 (static clip):  node _capture-frames.js <name> <x,y,w,h> [frames] [intervalMs]
// Mode 2 (find by text):  node _capture-frames.js <name> --find "<text1>,<text2>,..." [frames] [intervalMs] [pad]
//   Finds ha-card elements containing the given text, computes bounding box around all matches
// Example: node _capture-frames.js fans --find "Aux,Chamber,Cooling,Bento" 50 100 8
const { chromium } = require('C:/Users/rysock/AppData/Roaming/npm/node_modules/@playwright/mcp/node_modules/playwright');
const path = require('path');
const fs = require('fs');

const args = process.argv.slice(2);
const name = args[0];
if (!name) {
  console.log('Usage: node _capture-frames.js <name> <x,y,w,h> [frames] [intervalMs]');
  console.log('       node _capture-frames.js <name> --find "text1,text2,..." [frames] [intervalMs] [pad]');
  process.exit(1);
}

const findMode = args[1] === '--find';
let clipStr, searchTexts, pad;
let frameCount, intervalMs;

if (findMode) {
  searchTexts = args[2].split(',').map(s => s.trim());
  frameCount = parseInt(args[3] || '50', 10);
  intervalMs = parseInt(args[4] || '100', 10);
  pad = parseInt(args[5] || '8', 10);
} else {
  clipStr = args[1];
  frameCount = parseInt(args[2] || '50', 10);
  intervalMs = parseInt(args[3] || '100', 10);
}

const outDir = path.join(__dirname, '_frames', name);

(async () => {
  fs.mkdirSync(outDir, { recursive: true });

  // Connect to existing MCP-launched Edge browser via CDP
  const cdpPort = process.env.CDP_PORT || '62251';
  const cdpUrl = `http://127.0.0.1:${cdpPort}`;
  console.log(`Connecting to existing browser at ${cdpUrl}...`);
  const browser = await chromium.connectOverCDP(cdpUrl);
  const contexts = browser.contexts();
  if (contexts.length === 0) { console.error('No browser contexts found'); process.exit(1); }
  const pages = contexts[0].pages();
  if (pages.length === 0) { console.error('No pages found'); process.exit(1); }
  
  // Use the first page that has the 3d-printing dashboard, or the first page
  let page = pages.find(p => p.url().includes('3d-printing')) || pages[0];
  console.log(`Using page: ${page.url()}`);
  
  if (!page.url().includes('3d-printing')) {
    await page.goto('http://192.168.1.5:8123/3d-printing/0');
    console.log('Waiting 8s for dashboard to render...');
    await page.waitForTimeout(8000);
  }

  let clip;
  if (findMode) {
    // Find ha-card elements by text via shadow DOM traversal
    clip = await page.evaluate(({ texts, padding }) => {
      function findAll(root, sel, res) {
        res = res || [];
        if (root.querySelectorAll) root.querySelectorAll(sel).forEach(el => res.push(el));
        if (root.shadowRoot) findAll(root.shadowRoot, sel, res);
        if (root.querySelectorAll) root.querySelectorAll('*').forEach(ch => { if (ch.shadowRoot) findAll(ch.shadowRoot, sel, res); });
        return res;
      }
      const cards = findAll(document, 'ha-card');
      const matched = cards.filter(c => {
        const t = (c.innerText || '').toLowerCase();
        return texts.some(s => t.includes(s.toLowerCase()));
      });
      if (matched.length === 0) return null;
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      matched.forEach(c => {
        const r = c.getBoundingClientRect();
        if (r.x < minX) minX = r.x;
        if (r.y < minY) minY = r.y;
        if (r.x + r.width > maxX) maxX = r.x + r.width;
        if (r.y + r.height > maxY) maxY = r.y + r.height;
      });
      return {
        x: Math.round(minX - padding),
        y: Math.round(minY - padding),
        width: Math.round(maxX - minX + 2 * padding),
        height: Math.round(maxY - minY + 2 * padding),
        matchCount: matched.length,
        texts: matched.map(c => (c.innerText || '').substring(0, 60).replace(/\n/g, ' | '))
      };
    }, { texts: searchTexts, padding: pad });

    if (!clip) {
      console.error('No matching cards found for:', searchTexts.join(', '));
      browser.close();
      process.exit(1);
    }
    console.log(`Found ${clip.matchCount} cards:`, clip.texts);
  } else {
    const [cx, cy, cw, ch] = clipStr.split(',').map(Number);
    clip = { x: cx, y: cy, width: cw, height: ch };
  }

  console.log(`Clip: x=${clip.x}, y=${clip.y}, w=${clip.width}, h=${clip.height}`);
  console.log(`Capturing ${frameCount} frames (${intervalMs}ms interval)...`);

  for (let i = 0; i < frameCount; i++) {
    await page.screenshot({ path: path.join(outDir, `frame-${String(i).padStart(3, '0')}.png`), clip });
    if (i < frameCount - 1) await page.waitForTimeout(intervalMs);
    if (i % 10 === 0) process.stdout.write(`\r  ${i}/${frameCount}`);
  }
  console.log(`\nDone! ${frameCount} frames in ${outDir}`);
  browser.close();
})();

// Capture AMS tray popup interaction: tap card → popup opens → capture → dismiss
// Connects to existing MCP browser via CDP
// Usage: node _capture-popup.js [cdpPort]
const { chromium } = require('C:/Users/rysock/AppData/Roaming/npm/node_modules/@playwright/mcp/node_modules/playwright');
const path = require('path');
const fs = require('fs');

const cdpPort = process.argv[2] || process.env.CDP_PORT || '62251';
const outDir = path.join(__dirname, '_frames', 'ams-popup');

(async () => {
  fs.mkdirSync(outDir, { recursive: true });

  console.log(`Connecting to browser at CDP port ${cdpPort}...`);
  const browser = await chromium.connectOverCDP(`http://127.0.0.1:${cdpPort}`);
  const contexts = browser.contexts();
  const pages = contexts[0].pages();
  const page = pages.find(p => p.url().includes('3d-printing')) || pages[0];
  console.log(`Using page: ${page.url()}`);

  // Find AMS tray card (e.g., A1 - Blue PLA) via shadow DOM
  const trayBox = await page.evaluate(() => {
    function findAll(root, sel, res) {
      res = res || [];
      if (root.querySelectorAll) root.querySelectorAll(sel).forEach(el => res.push(el));
      if (root.shadowRoot) findAll(root.shadowRoot, sel, res);
      if (root.querySelectorAll) root.querySelectorAll('*').forEach(ch => { if (ch.shadowRoot) findAll(ch.shadowRoot, sel, res); });
      return res;
    }
    const cards = findAll(document, 'ha-card');
    // Find AMS 1, Tray A1 (Blue PLA)
    const tray = cards.find(c => {
      const t = (c.innerText || '').toLowerCase();
      return t.includes('blue pla') || t.includes('a1') && t.includes('bambu');
    });
    if (!tray) return null;
    const r = tray.getBoundingClientRect();
    return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2), text: (tray.innerText || '').substring(0, 60) };
  });

  if (!trayBox) {
    console.error('Could not find AMS tray card');
    browser.close();
    process.exit(1);
  }
  console.log(`Found tray card: "${trayBox.text}" at (${trayBox.x}, ${trayBox.y})`);

  // Phase 1: Capture 5 frames before click (dashboard state)
  console.log('Capturing pre-click frames...');
  for (let i = 0; i < 5; i++) {
    await page.screenshot({ path: path.join(outDir, `frame-${String(i).padStart(3, '0')}.png`) });
    await page.waitForTimeout(200);
  }

  // Phase 2: Click the tray card
  console.log('Clicking tray card...');
  await page.mouse.click(trayBox.x, trayBox.y);

  // Phase 3: Capture 20 frames as popup appears (~2s)
  console.log('Capturing popup open...');
  for (let i = 5; i < 25; i++) {
    await page.screenshot({ path: path.join(outDir, `frame-${String(i).padStart(3, '0')}.png`) });
    await page.waitForTimeout(100);
  }

  // Phase 4: Hold for 10 frames showing full popup (~1s)
  console.log('Capturing popup displayed...');
  for (let i = 25; i < 35; i++) {
    await page.screenshot({ path: path.join(outDir, `frame-${String(i).padStart(3, '0')}.png`) });
    await page.waitForTimeout(100);
  }

  // Phase 5: Dismiss by pressing Escape
  console.log('Dismissing popup...');
  await page.keyboard.press('Escape');

  // Phase 6: Capture 10 frames as popup closes (~1s)
  for (let i = 35; i < 45; i++) {
    await page.screenshot({ path: path.join(outDir, `frame-${String(i).padStart(3, '0')}.png`) });
    await page.waitForTimeout(100);
  }

  console.log(`Done! 45 frames in ${outDir}`);
  browser.close();
})();

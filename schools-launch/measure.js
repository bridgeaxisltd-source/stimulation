const { chromium } = require('playwright');
const useBrandFonts = require('./fontfix');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 810 } });
  await useBrandFonts(p, require('path').join(__dirname, 'assets'));
  await p.goto('http://localhost:4174/schools', { waitUntil: 'networkidle' });
  await p.evaluate(() => document.fonts.ready);
  console.log(JSON.stringify(await p.evaluate(() => {
    const h = document.querySelector('h1'); const r = h.getBoundingClientRect(); const cs = getComputedStyle(h);
    const page = getComputedStyle(document.querySelector('.schools-page'));
    return { h1: { x: r.left, y: r.top, w: r.width, h: r.height, fontSize: cs.fontSize, lh: cs.lineHeight, ls: cs.letterSpacing, weight: cs.fontWeight, color: cs.color },
      bg: page.backgroundColor,
      cards: [...document.querySelectorAll('.schools-packages__grid > *')].map((c) => [c.offsetWidth, c.offsetHeight]) };
  })));
  await b.close();
})();

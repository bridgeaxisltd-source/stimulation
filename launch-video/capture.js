const { chromium } = require('playwright');
(async () => {
  const out = process.argv[2];
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1, reducedMotion: 'reduce' });
  await p.goto('http://localhost:3123/', { waitUntil: 'networkidle' });
  await p.evaluate(() => document.fonts.ready);
  await p.screenshot({ path: `${out}/hero.png` });
  const ids = await p.evaluate(() => [...document.querySelectorAll('section[id], footer')].map(s => { const r = s.getBoundingClientRect(); return { id: s.id || 'footer', y: r.top + scrollY, h: r.height }; }));
  console.log(JSON.stringify(ids));
  for (const s of ids) {
    await p.evaluate(y => scrollTo(0, y - 84), s.y);
    await p.waitForTimeout(250);
    await p.screenshot({ path: `${out}/sec-${s.id}.png` });
  }
  await p.evaluate(() => scrollTo(0, 0));
  await p.screenshot({ path: `${out}/full.png`, fullPage: true });
  await b.close();
})();

const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const out = process.argv[2];
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, reducedMotion: 'reduce' });
  await p.goto('http://localhost:3123/', { waitUntil: 'networkidle' });
  await p.evaluate(() => document.fonts.ready);
  const targets = {
    explore: '.hero .button--outline',
    start: '.hero .button:not(.button--outline)',
    pc: '.product-copy .button',
    consult: '.contact .button--light',
  };
  const rects = {};
  const services = await p.$$('.service-item');
  const all = Object.entries(targets).map(([k, s]) => [k, s]);
  services.forEach((_, i) => all.push([`svc${i}`, `.service-item:nth-child(${i + 1})`]));
  for (const [k, sel] of all) {
    const el = await p.$(sel);
    await el.scrollIntoViewIfNeeded();
    await p.mouse.move(5, 1075);
    await p.waitForTimeout(450);
    rects[k] = await el.evaluate(e => { const r = e.getBoundingClientRect(); return { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height }; });
    await el.screenshot({ path: `${out}/${k}-normal.png` });
    await el.hover();
    await p.waitForTimeout(500);
    // capture a padded box so the hover lift/shadow/translate is included
    const r = await el.evaluate(e => { const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
    await p.screenshot({ path: `${out}/${k}-hover.png`, clip: { x: r.x - 12, y: r.y - 12, width: r.w + 24, height: r.h + 30 } });
  }
  fs.writeFileSync(`${out}/rects.json`, JSON.stringify(rects, null, 1));
  console.log(JSON.stringify(rects));
  await b.close();
})();

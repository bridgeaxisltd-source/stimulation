// Captures the schools landing (normal build, :4174) and a real click-through of the
// demo app (:4173). Brand fonts are applied, the demo-only notice is hidden, and the
// per-page guided tour is reported as already seen (what the app stores after dismissal).
const { chromium } = require('playwright');
const fs = require('fs');
const useBrandFonts = require('./fontfix');

const out = process.argv[2];
const rects = {};
const box = (r) => ({ x: r.x, y: r.y, w: r.width, h: r.height });

async function newPage(b) {
  const p = await b.newPage({ viewport: { width: 1440, height: 810 }, deviceScaleFactor: 2, reducedMotion: 'reduce' });
  await useBrandFonts(p, require('path').join(__dirname, 'assets'));
  await p.addInitScript(() => {
    const get = Storage.prototype.getItem;
    Storage.prototype.getItem = function (k) {
      return /^bridgeaxis\.(admin|teacher)-tour\./.test(k) ? 'seen' : get.call(this, k);
    };
    document.addEventListener('DOMContentLoaded', () => {
      const s = document.createElement('style');
      s.textContent = '.demo-mode-notice { display: none !important; }';
      document.head.appendChild(s);
    });
  });
  p.on('pageerror', (e) => console.error('PAGE ERROR', e.message));
  return p;
}
async function settle(p) {
  await p.waitForLoadState('networkidle');
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(600);
}
async function hoverCrop(p, el, name) {
  const r = await el.boundingBox();
  await el.hover();
  await p.waitForTimeout(400);
  await p.screenshot({ path: `${out}/${name}-hover.png`, clip: { x: r.x - 10, y: r.y - 10, width: r.width + 20, height: r.height + 20 } });
  await p.mouse.move(2, 805);
  await p.waitForTimeout(300);
  return box(r);
}

(async () => {
  const b = await chromium.launch();

  // ---------- landing ----------
  const L = await newPage(b);
  await L.goto('http://localhost:4174/schools');
  await settle(L);
  await L.screenshot({ path: `${out}/landing-hero.png` });
  const demoLink = L.locator('.schools-hero a', { hasText: 'Explore the demo' });
  rects.demoLink = await hoverCrop(L, demoLink, 'demo-link');
  const cards = L.locator('.schools-packages__grid > *');
  for (let i = 0; i < (await cards.count()); i++) {
    await cards.nth(i).screenshot({ path: `${out}/package-${i}.png` });
  }
  const rollout = L.locator('#rollout > :last-child');
  await rollout.scrollIntoViewIfNeeded();
  await L.waitForTimeout(300);
  await rollout.screenshot({ path: `${out}/rollout.png` });
  const rb = await rollout.boundingBox();
  rects.rollout = box(rb);
  rects.rolloutSteps = (await rollout.evaluate((g) => [...g.children].map((c) => { const r = c.getBoundingClientRect(); return { x: r.left, w: r.width }; })))
    .map((s) => ({ x: s.x - rb.x, w: s.w }));
  const actions = L.locator('.schools-conversation__actions');
  await actions.scrollIntoViewIfNeeded();
  await L.waitForTimeout(300);
  await actions.screenshot({ path: `${out}/conversation-actions.png` });
  const ab = await actions.boundingBox();
  const bookBtn = actions.locator('a.schools-button');
  const bb = await bookBtn.boundingBox();
  rects.bookBtn = { x: bb.x - ab.x, y: bb.y - ab.y, w: bb.width, h: bb.height };
  rects.actions = box(ab);
  await hoverCrop(L, bookBtn, 'book-btn');

  // ---------- app click-through ----------
  const A = await newPage(b);
  await A.goto('http://localhost:4173/school-admin');
  await settle(A);
  const steps = [
    ['home', 'People', 'Admissions'],
    ['admissions', 'Attendance & reports', 'Attendance'],
    ['attendance', 'Teaching', 'Analytics'],
    ['analytics', 'Fees & SMS', 'SMS wallet'],
  ];
  for (const [page, group, link] of steps) {
    await A.screenshot({ path: `${out}/app-${page}.png` });
    // A user scrolls the sidebar to a group that is out of view before clicking it;
    // capture that state too so the click lands on what is actually visible.
    const summary = A.locator('summary', { hasText: group }).first();
    await summary.scrollIntoViewIfNeeded();
    await A.waitForTimeout(300);
    await A.screenshot({ path: `${out}/app-${page}-pre.png` });
    rects[`${page}Group`] = box(await summary.boundingBox());
    await summary.click();
    await A.mouse.move(2, 805);
    await A.waitForTimeout(400);
    await A.screenshot({ path: `${out}/app-${page}-open.png` });
    const nav = summary.locator('xpath=..');
    const a = nav.getByRole('link', { name: link, exact: true }).first();
    rects[`${page}Link`] = await hoverCrop(A, a, `app-${page}-link`);
    await a.click();
    await settle(A);
    console.log(page, '->', A.url());
  }
  await A.screenshot({ path: `${out}/app-sms.png` });

  fs.writeFileSync(`${out}/rects.json`, JSON.stringify(rects, null, 1));
  console.log(JSON.stringify(rects));
  await b.close();
})();

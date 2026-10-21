// Captures BridgeAxis OS as separate UI layers for the v2 reel.
//
//   node capture.js <out-dir>
//
// Needs the landing build on :4174 and the demo build (VITE_STATIC_DEMO=true) on :4173.
// Every component is isolated on a transparent background (ancestor backgrounds and the
// element's own shadow are removed; the video adds its own shadows). Numbers that the
// video counts up are blanked in the PNG, and their text, position and font metrics are
// written to meta.json so the overlay can be set in the same type at the same spot.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const useBrandFonts = require('./fontfix');

const out = path.resolve(process.argv[2]);
const DPR = 3;
const meta = { viewport: { w: 1440, h: 810 }, dpr: DPR, landing: {}, app: {} };

async function newPage(browser) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 810 }, deviceScaleFactor: DPR, reducedMotion: 'reduce' });
  await useBrandFonts(page, path.join(__dirname, 'assets'));
  await page.addInitScript(() => {
    // The app stores this after a user dismisses the first-visit tour.
    const get = Storage.prototype.getItem;
    Storage.prototype.getItem = function (k) {
      return /^bridgeaxis\.(admin|teacher)-tour\./.test(k) ? 'seen' : get.call(this, k);
    };
    document.addEventListener('DOMContentLoaded', () => {
      const s = document.createElement('style');
      s.textContent = `
        .demo-mode-notice { display: none !important; }
        .__iso { background: transparent !important; background-color: transparent !important; background-image: none !important; }
        .__isoself { box-shadow: none !important; }
        .__blank { color: transparent !important; -webkit-text-fill-color: transparent !important; }
        .__hidden { visibility: hidden !important; }`;
      document.head.appendChild(s);
    });
  });
  page.on('pageerror', (e) => console.error('PAGE ERROR', e.message));
  return page;
}

async function settle(page) {
  await page.waitForLoadState('networkidle');
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(500);
}

// Screenshot one element on transparency. `blank` selects numbers to record and hide.
async function capture(page, handle, name, { blank = null, hide = null } = {}) {
  await handle.scrollIntoViewIfNeeded();
  const info = await handle.evaluate((el, { blank, hide }) => {
    let a = el.parentElement;
    while (a) { a.classList.add('__iso'); a = a.parentElement; }
    el.classList.add('__isoself');
    const box = el.getBoundingClientRect();
    const numbers = [];
    if (blank) {
      el.querySelectorAll(blank).forEach((n) => {
        const text = n.textContent.trim();
        if (!/\d/.test(text)) return;
        const r = n.getBoundingClientRect();
        const cs = getComputedStyle(n);
        numbers.push({
          text, x: r.left - box.left, y: r.top - box.top, w: r.width, h: r.height,
          font: { family: cs.fontFamily, size: parseFloat(cs.fontSize), weight: cs.fontWeight,
            spacing: cs.letterSpacing, color: cs.color, lineHeight: cs.lineHeight, align: cs.textAlign },
        });
        n.classList.add('__blank');
      });
    }
    if (hide) el.querySelectorAll(hide).forEach((n) => n.classList.add('__hidden'));
    return { x: box.left + scrollX, y: box.top + scrollY, w: box.width, h: box.height, numbers };
  }, { blank, hide });
  await handle.screenshot({ path: path.join(out, `${name}.png`), omitBackground: true, animations: 'disabled' });
  await handle.evaluate((el) => {
    document.querySelectorAll('.__iso, .__isoself, .__blank, .__hidden')
      .forEach((n) => n.classList.remove('__iso', '__isoself', '__blank', '__hidden'));
  });
  console.log('  ', name, Math.round(info.w) + 'x' + Math.round(info.h), info.numbers.map((n) => n.text).join(' '));
  return { name, ...info };
}

// Real :hover state of an element, isolated the same way.
async function captureHover(page, handle, name) {
  await handle.scrollIntoViewIfNeeded();
  await handle.hover();
  await page.waitForTimeout(450);
  const shot = await capture(page, handle, name);
  await page.mouse.move(2, 805);
  await page.waitForTimeout(300);
  return shot;
}

// Viewport screenshot with selected regions hidden: the "empty" backdrop components land on.
async function backdrop(page, name, hideSelector) {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.evaluate((sel) => document.querySelectorAll(sel).forEach((n) => n.classList.add('__hidden')), hideSelector);
  await page.waitForTimeout(150);
  await page.screenshot({ path: path.join(out, `${name}.png`) });
  await page.evaluate(() => document.querySelectorAll('.__hidden').forEach((n) => n.classList.remove('__hidden')));
  console.log('  ', name);
}

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch();

  // ---------------- landing ----------------
  console.log('landing');
  const L = await newPage(browser);
  await L.goto('http://localhost:4174/schools');
  await settle(L);
  await backdrop(L, 'landing-bg', '.schools-product-preview');
  const preview = L.locator('.schools-product-preview');
  meta.landing.preview = await capture(L, preview, 'landing-preview', { blank: 'strong' });
  const h1 = await L.locator('h1').evaluate((e) => {
    const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
    return { x: r.left, y: r.top, w: r.width, h: r.height, size: parseFloat(cs.fontSize), lineHeight: cs.lineHeight, spacing: cs.letterSpacing };
  });
  meta.landing.h1 = h1;
  const demo = L.locator('.schools-hero a', { hasText: 'Explore the demo' });
  meta.landing.demoLink = await capture(L, demo, 'landing-demo-link');
  meta.landing.demoLinkHover = await captureHover(L, demo, 'landing-demo-link-hover');
  const cards = L.locator('.schools-packages__grid > *');
  meta.landing.packages = [];
  for (let i = 0; i < (await cards.count()); i++) {
    meta.landing.packages.push(await capture(L, cards.nth(i), `package-${i}`));
  }
  const discuss = cards.nth(2).locator('a', { hasText: 'Discuss this package' });
  meta.landing.discuss = await discuss.evaluate((a, card) => {
    const r = a.getBoundingClientRect(), c = card.getBoundingClientRect();
    return { x: r.left - c.left, y: r.top - c.top, w: r.width, h: r.height };
  }, await cards.nth(2).elementHandle());
  meta.landing.discussHover = await captureHover(L, discuss, 'package-2-discuss-hover');
  const steps = L.locator('#rollout > :last-child > *');
  meta.landing.rollout = [];
  for (let i = 0; i < (await steps.count()); i++) {
    meta.landing.rollout.push(await capture(L, steps.nth(i), `rollout-${i}`));
  }
  const convo = L.locator('.schools-conversation__actions > *');
  meta.landing.conversation = [];
  for (let i = 0; i < (await convo.count()); i++) {
    meta.landing.conversation.push(await capture(L, convo.nth(i), `conversation-${i}`));
  }
  const book = convo.nth(0).locator('a.schools-button');
  meta.landing.book = await book.evaluate((a, card) => {
    const r = a.getBoundingClientRect(), c = card.getBoundingClientRect();
    return { x: r.left - c.left, y: r.top - c.top, w: r.width, h: r.height };
  }, await convo.nth(0).elementHandle());
  meta.landing.bookHover = await captureHover(L, book, 'book-hover');

  // ---------------- app ----------------
  const A = await newPage(browser);
  const pages = {
    admissions: {
      components: [
        ['heading', 'header.admissions-page-heading', {}],
        ['tabs', 'nav.admissions-sections', {}],
        ['metric', 'div.admissions-metric', { blank: 'dd', all: true }],
      ],
    },
    attendance: {
      components: [
        ['metric', 'article.workspace-metric', { blank: 'strong', all: true }],
        ['controls', 'section.admin-attendance > section:nth-of-type(1)', {}],
        ['live', 'section.admin-attendance > section:nth-of-type(2)', { hide: 'tbody tr' }],
        ['row', 'section.admin-attendance > section:nth-of-type(2) tbody tr', { all: true }],
      ],
      button: 'section.admin-attendance > section:nth-of-type(1) button',
    },
    analytics: {
      components: [
        ['heading', 'header.analytics-heading', {}],
        ['card', 'a.analytics-card', { blank: '.analytics-card__value', all: true }],
        ['panel', 'section.analytics-panel', {}],
      ],
      hoverCard: 1,
    },
    sms: {
      components: [
        ['heading', 'header.admin-report-view__heading', { blank: '__none__' }],
        ['note', 'p.admin-report-view__loaded-date', {}],
        ['metric', 'div.admin-report-metrics > article', { blank: 'strong', all: true }],
      ],
      button: 'header.admin-report-view__heading button',
    },
  };
  for (const [name, spec] of Object.entries(pages)) {
    console.log(name);
    await A.goto(`http://localhost:4173/school-admin/${name}`);
    await settle(A);
    const m = (meta.app[name] = { components: {} });
    await backdrop(A, `app-${name}-shell`, '.workspace-page-transition');
    m.sidebar = await capture(A, A.locator('aside.admin-workspace__rail'), `app-${name}-sidebar`);
    m.topbar = await capture(A, A.locator('header.admin-workspace__topbar'), `app-${name}-topbar`);
    for (const [key, sel, opt] of spec.components) {
      const loc = A.locator(sel);
      const n = opt.all ? await loc.count() : 1;
      m.components[key] = [];
      for (let i = 0; i < n; i++) {
        m.components[key].push(await capture(A, loc.nth(i), `app-${name}-${key}${opt.all ? '-' + i : ''}`, opt));
      }
    }
    if (spec.button) {
      const btn = A.locator(spec.button).first();
      m.button = await capture(A, btn, `app-${name}-button`);
      m.buttonHover = await captureHover(A, btn, `app-${name}-button-hover`);
    }
    if (spec.hoverCard != null) {
      m.cardHover = await captureHover(A, A.locator('a.analytics-card').nth(spec.hoverCard), `app-${name}-card-${spec.hoverCard}-hover`);
    }
    await A.evaluate(() => window.scrollTo(0, 0));
  }

  // Parent portal sign-in card, for the hook
  console.log('parents');
  await A.goto('http://localhost:4173/parents');
  await settle(A);
  const parentCard = await A.evaluateHandle(() => {
    const f = document.querySelector('form');
    let el = f;
    while (el.parentElement && el.parentElement.getBoundingClientRect().width < 700) el = el.parentElement;
    return el;
  });
  meta.app.parents = { card: await capture(A, parentCard.asElement(), 'app-parents-card') };

  fs.writeFileSync(path.join(out, 'meta.json'), JSON.stringify(meta, null, 1));
  await browser.close();
  console.log('done');
})();

// Serve the intended fonts during capture: Georgia -> Gelasio (metric-compatible), Inter variable.
const fs = require('fs');
const path = require('path');
module.exports = async function useBrandFonts(page, dir) {
  const b64 = (f) => fs.readFileSync(path.join(dir, f)).toString('base64');
  const css = `
    @font-face { font-family: Georgia; font-weight: 400; src: url(data:font/woff2;base64,${b64('gelasio-latin-400-normal.woff2')}) format('woff2'); }
    @font-face { font-family: Georgia; font-weight: 700; src: url(data:font/woff2;base64,${b64('gelasio-latin-700-normal.woff2')}) format('woff2'); }
    @font-face { font-family: Inter; font-weight: 100 900; src: url(data:font/woff2;base64,${b64('inter-latin-wght-normal.woff2')}) format('woff2'); }`;
  await page.addInitScript((c) => {
    document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); s.textContent = c; document.head.appendChild(s); });
  }, css);
};

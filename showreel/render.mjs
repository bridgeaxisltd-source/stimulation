// Renders the reel frame-by-frame in headless Chromium and pipes JPEGs into ffmpeg.
//   node render.mjs                -> out/reel_silent.mp4 (all 900 frames)
//   node render.mjs --stills 2,4.5 -> out/still_2.png, out/still_4.5.png
import { createRequire } from 'module';
import { spawn } from 'child_process';
import { mkdirSync, writeFileSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require('playwright')); } catch { ({ chromium } = require('/opt/node22/lib/node_modules/playwright')); }

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(here, 'out');
mkdirSync(out, { recursive: true });
const FPS = 60, FRAMES = 15 * FPS;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.on('pageerror', e => { console.error('page error:', e); process.exit(1); });
await page.goto('file://' + path.join(here, 'index.html') + '?render=1');
await page.waitForFunction(() => window.reelReady === true);

const stillsArg = process.argv.indexOf('--stills');
if (stillsArg > 0) {
  for (const s of process.argv[stillsArg + 1].split(',')) {
    const b64 = await page.evaluate(f => window.renderPNG(f), Math.round(parseFloat(s) * FPS));
    writeFileSync(path.join(out, `still_${s}.png`), Buffer.from(b64, 'base64'));
  }
} else {
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '15', '-pix_fmt', 'yuv420p', '-r', String(FPS), path.join(out, 'reel_silent.mp4')], { stdio: ['pipe', 'inherit', 'inherit'] });
  const t0 = Date.now();
  for (let f = 0; f < FRAMES; f++) {
    const b64 = await page.evaluate(f => window.renderFrame(f, 4, 0.96), f);
    if (!ff.stdin.write(Buffer.from(b64, 'base64'))) await new Promise(r => ff.stdin.once('drain', r));
    if (f % 60 === 0) process.stdout.write(`frame ${f}/${FRAMES}  ${((Date.now() - t0) / 1000).toFixed(0)}s\n`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
}
await browser.close();

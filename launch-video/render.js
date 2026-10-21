// Usage:
//   node render.js stills 0.5 2.1 ...   -> stills/t-<sec>.png
//   node render.js video out.mp4        -> silent H.264 at TL.fps
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const dir = __dirname;
const TL = JSON.parse(fs.readFileSync(path.join(dir, 'timeline.json'), 'utf8'));
const rects = fs.readFileSync(path.join(dir, 'assets/ui/rects.json'), 'utf8');
const html = fs.readFileSync(path.join(dir, 'video.html'), 'utf8')
  .replace('__TIMELINE__', JSON.stringify(TL))
  .replace('__RECTS__', rects);
fs.writeFileSync(path.join(dir, 'build.html'), html);

(async () => {
  const [mode, ...args] = process.argv.slice(2);
  const browser = await chromium.launch({ args: ['--allow-file-access-from-files'] });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  page.on('pageerror', (e) => console.error('PAGE ERROR', e.message));
  await page.goto('file://' + path.join(dir, 'build.html'));
  await page.evaluate(() => window.ready);

  if (mode === 'stills') {
    fs.mkdirSync(path.join(dir, 'stills'), { recursive: true });
    for (const s of args) {
      await page.evaluate((t) => window.render(t), parseFloat(s));
      await page.screenshot({ path: path.join(dir, 'stills', `t-${s}.png`) });
    }
  } else {
    const out = args[0];
    const frames = Math.round(TL.duration * TL.fps);
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(TL.fps), '-c:v', 'mjpeg', '-i', '-',
      '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-r', String(TL.fps), out], { stdio: ['pipe', 'inherit', 'inherit'] });
    const t0 = Date.now();
    for (let i = 0; i < frames; i++) {
      await page.evaluate((t) => window.render(t), i / TL.fps);
      const buf = await page.screenshot({ type: 'jpeg', quality: 95 });
      if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
      if (i % 60 === 0) console.log(`frame ${i}/${frames} ${((Date.now() - t0) / 1000).toFixed(1)}s`);
    }
    ff.stdin.end();
    await new Promise((r) => ff.on('close', r));
  }
  await browser.close();
})();

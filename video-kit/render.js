// Renders a project's video.html frame by frame (deterministic window.render(t)).
// Usage:
//   node render.js <project-dir> stills 0.5 2.1 ...   -> <project-dir>/stills/t-<sec>.png
//   node render.js <project-dir> video out.mp4        -> silent H.264 at TL.fps
// Frame size comes from timeline.json (width/height, default 1920x1080).
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const dir = path.resolve(process.argv[2]);
const TL = JSON.parse(fs.readFileSync(path.join(dir, 'timeline.json'), 'utf8'));
const W = TL.width || 1920, H = TL.height || 1080;
const rectsPath = path.join(dir, 'assets/ui/rects.json');
const rects = fs.existsSync(rectsPath) ? fs.readFileSync(rectsPath, 'utf8') : '{}';
const metaPath = path.join(dir, 'assets/meta.json');
const meta = fs.existsSync(metaPath) ? fs.readFileSync(metaPath, 'utf8') : '{}';
const html = fs.readFileSync(path.join(dir, 'video.html'), 'utf8')
  .replace('__TIMELINE__', JSON.stringify(TL))
  .replace('__RECTS__', rects)
  .replace('__META__', meta);
fs.writeFileSync(path.join(dir, 'build.html'), html);

(async () => {
  const [mode, ...args] = process.argv.slice(3);
  const browser = await chromium.launch({ args: ['--allow-file-access-from-files'] });
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
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
    // video out.mp4 [fromSec] [toSec]; the range is for quick test renders.
    const out = args[0];
    const first = Math.round(parseFloat(args[1] || 0) * TL.fps);
    const last = Math.round(parseFloat(args[2] || TL.duration) * TL.fps);
    // Motion blur (opt-in via timeline "motionBlur": {samples, shutter}): each output frame is
    // the average of `samples` sub-frames spread over `shutter` of the frame interval (0.5 = 180°).
    // Sub-frames go to ffmpeg in order; tmix averages each run and select keeps one per frame.
    const mb = TL.motionBlur || { samples: 1, shutter: 0 };
    const n = Math.max(1, mb.samples);
    const blend = n > 1 ? ['-vf', `tmix=frames=${n},select='eq(mod(n\\,${n})\\,${n - 1})',setpts=N/(${TL.fps}*TB)`] : [];
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(TL.fps * n), '-c:v', 'mjpeg', '-i', '-',
      ...blend, '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-r', String(TL.fps), out], { stdio: ['pipe', 'inherit', 'inherit'] });
    const t0 = Date.now();
    for (let i = first; i < last; i++) {
      for (let k = 0; k < n; k++) {
        const offset = n > 1 ? (k / (n - 1) - 0.5) * mb.shutter : 0;
        await page.evaluate((t) => window.render(t), Math.max(0, (i + offset) / TL.fps));
        const buf = await page.screenshot({ type: 'jpeg', quality: 95 });
        if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
      }
      if ((i - first) % 60 === 0) console.log(`frame ${i - first}/${last - first} ${((Date.now() - t0) / 1000).toFixed(1)}s`);
    }
    ff.stdin.end();
    await new Promise((r) => ff.on('close', r));
  }
  await browser.close();
})();
